import numpy as np
import uhd
from uhd import libpyuhd as lib
from threading import Thread
import time
import scipy.signal as sg
import scipy.optimize as opt
import json

#For suppressing printing
import sys
import os

# from IPython.utils import io

class SDMRR:
    
    FS = 1e6
    NS = 10000
    DEAD_TIME = 40e-6
    RX_GAIN = 50
    TUNE_SHIFT = 50000
    RX_SHIFT = 0
    ZBUFF_TIME = 40e-6
    
    RX_DATA = np.empty(NS, dtype=np.complex64)
    
    def __init__(self, nocal = False):
        with HiddenPrints():
            self.radio = uhd.usrp.MultiUSRP("type=b200")
        self.radio.set_gpio_attr('FP0', 'CTRL', 0x000, 0xFFF) #pin 1 on ATR
        self.radio.set_gpio_attr('FP0', 'DDR', 0xFFF, 0xFFF) # all outputs
        self.radio.set_gpio_attr("FP0", "OUT", 0x002, 0xFFF); #pin 2 ON
        
        #Defaults
        self.caldict = {
            "f0": 22000000.000000, 
            "t90": 0.0003
            }
        
        if(os.path.isfile('cal.json')):
            print("Loading Calibration Data")
            with open('cal.json', 'r') as cal:
                self.caldict = json.load(cal)

            print("Last Calibration: " + (time.asctime(time.localtime(self.caldict["lastcal"]))))
            if not nocal:
                self.check_cal()

    def onepulse(self, freq = None, t90 = None, gain = 50, filt = True, start_time = 0.2, amp = 1):

        if freq is None:
            freq = self.caldict["f0"]
        if t90 is None:
            t90 = self.caldict["t90"]

        #Sequencing variables
        tx_start_time = start_time - self.ZBUFF_TIME
        sw_on_time = start_time - 2e-6
        sw_off_time = start_time + self.DEAD_TIME + t90 
        rx_start_time = start_time - 100e-6

        #Set up the streamer before we start receiving, as this setup causes the radio to stop RX
        tx_st_args = lib.usrp.stream_args("fc32", "sc16")
        tx_st_args.channels = [0]
        global tx_streamer
        try: tx_streamer
        except NameError:
            tx_streamer = self.radio.get_tx_stream(tx_st_args)
        else:
            if tx_streamer is None:
                tx_streamer = self.radio.get_tx_stream(tx_st_args)

        #Set up TX stream metadata (includes timing)
        tx_metadata = lib.types.tx_metadata()
        tx_metadata.time_spec = lib.types.time_spec(tx_start_time)
        tx_metadata.start_of_burst = True
        tx_metadata.end_of_burst = True
        tx_metadata.has_time_spec = True

        self.radio.set_tx_rate(self.FS, 0)
        self.radio.set_tx_freq(lib.types.tune_request(freq + 120e6 + self.TUNE_SHIFT), 0)
        self.radio.set_tx_gain(gain, 0)

        # Set up the stream and receive buffer
        rx_st_args = uhd.usrp.StreamArgs("fc32", "sc16")
        rx_st_args.channels = [1]

        global rx_streamer
        try: rx_streamer
        except NameError:
            rx_streamer = self.radio.get_rx_stream(rx_st_args)
        else:
            if rx_streamer is None:
                rx_streamer = self.radio.get_rx_stream(rx_st_args)
                
        #Set up RX
        self.radio.set_rx_rate(self.FS, 1)
        self.radio.set_rx_freq(uhd.libpyuhd.types.tune_request(freq + 120e6 + self.TUNE_SHIFT), 1)
        self.radio.set_rx_gain(self.RX_GAIN, 1)

        recv_buffer = np.zeros((1,1000), dtype=np.complex64)
        rx_metadata = uhd.types.RXMetadata()

        # Setup stream command
        stream_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.num_done)
        stream_cmd.num_samps = self.NS
        stream_cmd.stream_now = False
        stream_cmd.time_spec = lib.types.time_spec(rx_start_time)

        #Create the pulse
        t = np.arange(0, t90, 1/self.FS)
        waveform_proto = amp*np.complex64(np.concatenate((np.zeros(int(self.ZBUFF_TIME * self.FS)), np.exp(-self.TUNE_SHIFT*np.pi*2j*t))))

        self.radio.set_time_now(lib.types.time_spec(0.0))

        #Send the tx command
        with HiddenPrints():
            samples = tx_streamer.send(waveform_proto, tx_metadata)

        self.radio.clear_command_time();
        self.radio.set_command_time(lib.types.time_spec(sw_on_time));
        self.radio.set_gpio_attr("FP0", "OUT", 0x000, 0xFFF); #pin 2 OFF
        self.radio.clear_command_time();

        self.radio.clear_command_time();
        self.radio.set_command_time(lib.types.time_spec(sw_off_time));
        self.radio.set_gpio_attr('FP0', 'OUT', 0x002, 0xFFF) #pin 2 ON
        self.radio.clear_command_time();


        rx_streamer.issue_stream_cmd(stream_cmd)

        #Receive Samples.  recv() will return zeros, then our samples, then more zeros, letting us know it's done
        waiting_to_start = True # keep track of where we are in the cycle (see above comment)
        nsamps = 0
        i = 0
        while nsamps != 0 or waiting_to_start:
            nsamps = rx_streamer.recv(recv_buffer, rx_metadata)
            if nsamps and waiting_to_start:
                waiting_to_start = False
            if nsamps:
                self.RX_DATA[i:i+nsamps] = recv_buffer[0,0:nsamps]
            i += nsamps


        # tx_streamer = None
        # rx_streamer = None

        #Process the data
        t = np.arange(self.NS)/self.FS
        exp = np.exp(self.TUNE_SHIFT*np.pi*2*1j*t)
        data = self.RX_DATA*exp
        
        eshift = -np.angle(np.average(data[350:500]))   #phase properly
        data = data*np.exp(1j*eshift)

        if filt:
            b, a = sg.butter(3, 0.004)
            zi = sg.lfilter_zi(b, a)
            z, _ = sg.lfilter(b, a, data, zi=zi*data[0])
            return z
        else:
            return data
        
    def pulseecho(self, f0 = None, t90 = None, gain=70, tr=3e-3, p90p = 0, amp90 = 1, amp180 = None):
        if f0 is None:
            f0 = self.caldict["f0"]
        if t90 is None:
            t90 = self.caldict["t90"]

        t180 = t90
        if amp180 is None:
            t180 = 2*t90
            amp180 = 1

        self.radio.set_gpio_attr('FP0', 'OUT', 0x002, 0xFFF) #pin 2 ON

        ############################## Internal Helpers ##########################
        def _pulse(start_time, firstpulse, phase):

            #Sequencing variables
            tx_start_time = start_time - self.ZBUFF_TIME
            sw_on_time = start_time - 5e-6
            sw_off_time = start_time + self.DEAD_TIME + (t90 if firstpulse else t180)
            tx_metadata.time_spec = lib.types.time_spec(tx_start_time)

            #Send the tx command
            with HiddenPrints():
                samples = tx_streamer.send((t90_proto if firstpulse else t180_protos[phase]), tx_metadata)

            self.radio.clear_command_time();
            self.radio.set_command_time(lib.types.time_spec(sw_on_time));
            self.radio.set_gpio_attr("FP0", "OUT", 0x003, 0xFFF); #pin 1 ON (keep pin 2 on)
            self.radio.clear_command_time();

            self.radio.clear_command_time();
            self.radio.set_command_time(lib.types.time_spec(sw_off_time));
            self.radio.set_gpio_attr('FP0', 'OUT', 0x002, 0xFFF) #pin 1 OFF
            self.radio.clear_command_time();

        def _rx():
            recv_buffer = np.zeros((1,500000), dtype=np.complex64)
            #Receive Samples.  recv() will return zeros, then our samples, then more zeros, letting us know it's done
            waiting_to_start = True # keep track of where we are in the cycle (see above comment)
            nsamps = 0
            i = 0
            while nsamps != 0 or waiting_to_start:
                nsamps = rx_streamer.recv(recv_buffer, uhd.types.RXMetadata())
                if nsamps and waiting_to_start:
                    waiting_to_start = False
                    i = 0
                if nsamps:
                    # print(nsamps)
                    # for j in range(49):
                    #     start = int((j+1) * 10000 - 100)
                    #     bigbuff[0,j*200:(j+1)*200] = recv_buffer[0,start:start+200]
                    bigbuff[0, i:i+nsamps] = recv_buffer[0,0:nsamps]
                i += nsamps


        exp_len = int((2 * tr + t90)*self.FS) #the number of samples for the full experiment
        #global bigbuff
        bigbuff = np.zeros((1, exp_len), dtype=np.complex64)

        #Set up the streamer before we start receiving, as this setup causes the radio to stop RX
        tx_st_args = lib.usrp.stream_args("fc32", "sc16")
        tx_st_args.channels = [0]
        tx_streamer = self.radio.get_tx_stream(tx_st_args)

        #Set up TX stream metadata (includes timing)
        tx_metadata = lib.types.tx_metadata()
        tx_metadata.start_of_burst = True
        tx_metadata.end_of_burst = True
        tx_metadata.has_time_spec = True

        self.radio.set_tx_rate(self.FS, 0)
        self.radio.set_tx_freq(lib.types.tune_request(f0 + 120e6 + self.TUNE_SHIFT), 0)
        self.radio.set_tx_gain(gain, 0)

        #Set up RX
        self.radio.set_rx_rate(self.FS, 1)
        self.radio.set_rx_freq(uhd.libpyuhd.types.tune_request(f0 + 120e6 + self.TUNE_SHIFT), 1)
        self.radio.set_rx_gain(self.RX_GAIN, 1)

        # Set up the stream and receive buffer
        rx_st_args = uhd.usrp.StreamArgs("fc32", "sc16")
        rx_st_args.channels = [1]
        #global rx_streamer
        rx_streamer = self.radio.get_rx_stream(rx_st_args)

        # Setup stream command
        stream_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.num_done)
        stream_cmd.num_samps = exp_len
        stream_cmd.stream_now = False

        #Create the pulses    
        zero_buff = np.zeros(int(self.ZBUFF_TIME * self.FS))
        t90_base = amp90*np.exp(-self.TUNE_SHIFT*np.pi*2j*np.arange(0, t90, 1/self.FS))
        t180_base = amp180*np.exp(-self.TUNE_SHIFT*np.pi*2j*np.arange(0, t180, 1/self.FS))

        t90_proto = np.complex64(np.concatenate((zero_buff, t90_base*1j**p90p)))
        t180_protos = ([np.complex64(np.concatenate((zero_buff, t180_base*1j**i))) for i in range(4)])

        #Reset time to 0
        self.radio.set_time_now(lib.types.time_spec(0.0))
        stream_cmd.time_spec = lib.types.time_spec(0.1)
        rx_thread = Thread(target=_rx, args=())

        #Reset time to 0
        self.radio.set_time_now(lib.types.time_spec(0.0))   

        rx_streamer.issue_stream_cmd(stream_cmd)
        rx_thread.start() 

        _pulse(0.1, firstpulse=True, phase=0)
        _pulse(0.1 + tr/2, firstpulse=False, phase=1)

        rx_thread.join()

        tx_streamer = None
        rx_streamer = None


        ########################## Post Processing ##########################
        b, a = sg.butter(3, 20000, fs=self.FS)
        zi = sg.lfilter_zi(b, a)

        t = np.arange(len(bigbuff[0]))/self.FS
        exp = np.exp(self.TUNE_SHIFT*np.pi*2*1j*t)
        z, _ = sg.lfilter(b, a, bigbuff[0]*exp, zi=zi*bigbuff[0,0])

        eshift = -np.angle(np.average(z[177:197]))   #phase properly
        return bigbuff[0]*exp*np.exp(1j*eshift)
        
    def ncpmg(self, f0 = None, t90 = None, gain=70, tr=3e-3, npulses = 100, cycle=[0,0,1,3], width=1000, p90p = 0, amp90 = 1, amp180 = None):
        if f0 is None:
            f0 = self.caldict["f0"]
        if t90 is None:
            t90 = self.caldict["t90"]
            
        t180 = t90
        if amp180 is None:
            t180 = 2*t90
            amp180 = 1
            
        self.radio.set_gpio_attr('FP0', 'OUT', 0x002, 0xFFF) #pin 2 ON
            

        ############################## Internal Helpers ##########################
        def _pulse(start_time, firstpulse, phase):

            #Sequencing variables
            tx_start_time = start_time - self.ZBUFF_TIME
            sw_on_time = start_time - 2e-6
            sw_off_time = start_time + self.DEAD_TIME + (t90 if firstpulse else t180)
            tx_metadata.time_spec = lib.types.time_spec(tx_start_time)

            #Send the tx command
            with HiddenPrints():
                samples = tx_streamer.send((t90_proto if firstpulse else t180_protos[phase]), tx_metadata)

            if firstpulse:
                self.radio.clear_command_time();
                self.radio.set_command_time(lib.types.time_spec(sw_on_time));
                self.radio.set_gpio_attr("FP0", "OUT", 0x000, 0xFFF); #pin 2 OFF
                self.radio.clear_command_time();

#             self.radio.clear_command_time();
#             self.radio.set_command_time(lib.types.time_spec(sw_off_time));
#             self.radio.set_gpio_attr('FP0', 'OUT', 0x002, 0xFFF) #pin 2 ON
#             self.radio.clear_command_time();

        def _rx():
            recv_buffer = np.zeros((1,500000), dtype=np.complex64)
            #Receive Samples.  recv() will return zeros, then our samples, then more zeros, letting us know it's done
            waiting_to_start = True # keep track of where we are in the cycle (see above comment)
            nsamps = 0
            i = 0
            while nsamps != 0 or waiting_to_start:
                nsamps = rx_streamer.recv(recv_buffer, uhd.types.RXMetadata())
                if nsamps and waiting_to_start:
                    waiting_to_start = False
                    i = 0
                if nsamps:
                    # print(nsamps)
                    # for j in range(49):
                    #     start = int((j+1) * 10000 - 100)
                    #     bigbuff[0,j*200:(j+1)*200] = recv_buffer[0,start:start+200]
                    bigbuff[0, i:i+nsamps] = recv_buffer[0,0:nsamps]
                i += nsamps


        exp_len = int(((npulses + 1) * tr + t90)*self.FS) #the number of samples for the full experiment
        #global bigbuff
        bigbuff = np.zeros((1, exp_len), dtype=np.complex64)

        #Set up the streamer before we start receiving, as this setup causes the radio to stop RX
        tx_st_args = lib.usrp.stream_args("fc32", "sc16")
        tx_st_args.channels = [0]
        tx_streamer = self.radio.get_tx_stream(tx_st_args)

        #Set up TX stream metadata (includes timing)
        tx_metadata = lib.types.tx_metadata()
        tx_metadata.start_of_burst = True
        tx_metadata.end_of_burst = True
        tx_metadata.has_time_spec = True

        self.radio.set_tx_rate(self.FS, 0)
        self.radio.set_tx_freq(lib.types.tune_request(f0 + 120e6 + self.TUNE_SHIFT), 0)
        self.radio.set_tx_gain(gain, 0)

        #Set up RX
        self.radio.set_rx_rate(self.FS, 1)
        self.radio.set_rx_freq(uhd.libpyuhd.types.tune_request(f0 + 120e6 + self.TUNE_SHIFT), 1)
        self.radio.set_rx_gain(self.RX_GAIN, 1)

        # Set up the stream and receive buffer
        rx_st_args = uhd.usrp.StreamArgs("fc32", "sc16")
        rx_st_args.channels = [1]
        #global rx_streamer
        rx_streamer = self.radio.get_rx_stream(rx_st_args)

        # Setup stream command
        stream_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.num_done)
        stream_cmd.num_samps = exp_len
        stream_cmd.stream_now = False

        #Create the pulses    
        zero_buff = np.zeros(int(self.ZBUFF_TIME * self.FS))
        t90_base = amp90*np.exp(-self.TUNE_SHIFT*np.pi*2j*np.arange(0, t90, 1/self.FS))
        t180_base = amp180*np.exp(-self.TUNE_SHIFT*np.pi*2j*np.arange(0, t180, 1/self.FS))

        t90_proto = np.complex64(np.concatenate((zero_buff, t90_base*1j**p90p)))
        t180_protos = ([np.complex64(np.concatenate((zero_buff, t180_base*1j**i))) for i in range(4)])

        #Reset time to 0
        self.radio.set_time_now(lib.types.time_spec(0.0))
        stream_cmd.time_spec = lib.types.time_spec(0.1)
        rx_thread = Thread(target=_rx, args=())

        #Reset time to 0
        self.radio.set_time_now(lib.types.time_spec(0.0))   

        rx_streamer.issue_stream_cmd(stream_cmd)
        rx_thread.start() 

        _pulse(0.1, firstpulse=True, phase=0)
        for i in range(npulses):
            _pulse(0.1 + tr*i + tr/2, firstpulse=False, phase=cycle[i%4])
            #cpmg_data[i] = self.RX_DATA

        rx_thread.join()
        self.radio.set_gpio_attr('FP0', 'OUT', 0x002, 0xFFF) #pin 2 ON

        tx_streamer = None
        rx_streamer = None


        ########################## Post Processing ##########################
        b, a = sg.butter(3, 20000, fs=self.FS) #Used to be 10000
        zi = sg.lfilter_zi(b, a)

        t = np.arange(len(bigbuff[0]))/self.FS
        exp = np.exp(self.TUNE_SHIFT*np.pi*2*1j*t)
        z, _ = sg.lfilter(b, a, bigbuff[0]*exp, zi=zi*bigbuff[0,0])

        eshift = -np.angle(np.average(z[60:80]))   #phase properly for 500us TE
        return z*np.exp(1j*eshift)

    def cpmg_phaseloop(self, f0 = None, t90 = None, gain=70, tr=500.02e-6, npulses = 100, cycle_90 = [0,2,0,2], cycle_180 = [1,1,3,3], amp90 = 0.45, amp180 = 0.9, raw=False):

        if f0 is None:
            f0 = self.caldict["f0"]
        if t90 is None:
            t90 = self.caldict["t90"]

        cpdatas = np.zeros((len(cycle_90), int(((npulses + 1) * tr + t90)*self.FS)), dtype=np.complex64)
        cpdata = np.zeros(int(((npulses + 1) * tr + t90)*self.FS), dtype=np.complex64)
        for i in range(len(cycle_90)):
            cpdata = self.ncpmg(gain = 70, tr=tr, npulses=npulses, cycle=[cycle_180[i] for j in range(4)], 
                                width=4, p90p = cycle_90[i], amp90=amp90, amp180=amp180)
            cpdatas[i] = cpdata
            print(i)
            if(i != len(cycle_90)): time.sleep(3)
        
        if raw:
            return cpdatas
        else:
            #get echo magnitudes
            width = 200
            tr_samps = tr*self.FS
            t90_samps = int(t90 * self.FS)
            mags_abs = np.zeros(npulses)
            mags_r = np.zeros(npulses)
            
            for i in range(npulses):
                start = int((i+1) * tr_samps - width/2) + t90_samps
                mags_abs[i] = np.max(np.abs(np.sum(cpdatas[:,start:start+width],axis=0)))
                #mags_r[i] = np.max(np.real(cpdatas[start:start+width]))

            return mags_abs
        
    def find_f0(self, t90 = None, gain = 70, freq = None, debug=False):
        if freq is None:
            freq = self.caldict["f0"]
        if t90 is None:
            t90 = self.caldict["t90"]

        echo = self.pulseecho(gain=70, amp90=0.45, amp180=0.9)[4000:8000]
        efft = np.fft.fft(echo)

        ftfreqs = np.fft.fftfreq(4000, self.FS)
        maxfreq = ftfreqs[np.argmax(np.fft.fftshift(np.abs(efft)))-2000]
        f0 = freq + maxfreq

        if(debug):
            print(f0)

        return f0
    
    def find_t90(self, f0 = None, gain = 70, debug = False):
        if f0 is None:
            f0 = self.caldict["f0"]

        if debug:
            print("Calibrating t90")

        def _weight(fid):
            return np.max(np.abs(fid[fidstart_idx:fidstart_idx+3000]))

        t90s = np.arange(5e-6, 100e-6, 5e-6)
        scores = np.zeros(len(t90s))
        for i in range(len(t90s)):
            fidstart_idx = int((self.DEAD_TIME + t90s[i] + 100e-6)*self.FS) + 500 #extra 500 for lowpass filter
            if debug:
                print("Testing %fs" % (t90s[i]))
            fid = self.onepulse(f0, t90s[i], gain)
            scores[i] = _weight(fid)
            if debug:
                print(scores[i])
            time.sleep(4)
        return np.stack((t90s, scores), axis=1)
    
    def get_t2(self, cpdata, tr=None):
        def _decay(x, a, b, c):
            return a * np.exp(-b * x)+c
        
        if tr is None:
            popt, pcov = opt.curve_fit(_decay, cpdata[:,0], cpdata[:,1])
        else:
            popt, pcov = opt.curve_fit(_decay, np.arange(len(cpdata))*tr, cpdata)
            
        return 1/popt[1]
    
    def cal(self, f0=None, t90=None, debug=False):
        if f0 is None and t90 is None:
            self.caldict["f0"] = self.find_f0()
            tfids = self.find_t90(debug=debug)
            self.caldict["t90"] = tfids[np.argmax(tfids[:,1]),0]
            self.caldict["lastcal"] = time.time()
        else:
            if f0 is not None and t90 is not None:
                self.caldict["t90"] = t90
                self.caldict["f0"] = f0
            elif f0 is not None:
                self.caldict["f0"] = f0
                tfids = self.find_t90()
                self.caldict["t90"] = tfids[np.argmax(tfids[:,1]),0]
                self.caldict["lastcal"] = time.time()
            elif t90 is not None:
                self.caldict["t90"] = t90
                self.caldict["f0"] = self.find_f0()
        
        json_object = json.dumps(self.caldict, indent=4)
        with open("cal.json", "w") as cal:
            cal.write(json_object)
            
    
    def check_cal(self, debug = False):
        if(time.time() - self.caldict["lastcal"] > 5*60): #longer than 5 minutes since last cal
            if debug:
                print("Calibration out of date, running calibration")
            self.cal()
            return False
        return True
            
class HiddenPrints:
    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout



