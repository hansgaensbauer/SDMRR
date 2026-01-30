#!/home/sdmrr/miniforge-pypy3/envs/radioconda/bin/python3

from SDMRR import *
import matplotlib.pyplot as plt
import numpy as np
from pump import *
import datetime
import RPi.GPIO as GPIO

backup_dir = "Data/Run3_BR1/"

## Initialize the peristaltic pump
print("Running Sample.py")
peri = Pump()
peri.setspeed(1, 55)
peri.setspeed(2, 55)
peri.setdir(1, 'cw')
peri.setdir(2, 'cw')
peri.start(1)
peri.start(2)
time.sleep(0.15)
peri.setspeed(1, 55)
peri.setspeed(2, 55)
peri.setdir(1, 'cw')
peri.setdir(2, 'cw')
peri.start(1)
peri.start(2)

#Set up GPIO for the RF switch
GPIO.setmode(GPIO.BCM)
GPIO.setup(15, GPIO.OUT)
GPIO.setup(14, GPIO.OUT)

def gett2(save = False, amp90 = 0.45, amp180 = 0.9, directory = None):
    
    print("CPMG")
    npulses = 5000
    tr = 500.023e-6
    
    cp = mrr.cpmg_phaseloop(npulses = npulses, amp90 = amp90, cycle_90 = [0], cycle_180 = [1], amp180 = amp180, raw = True) # 
    
    #Get ebr1 amplitudes
    width = 200
    threshold = 1000
    tr_samps = tr*mrr.FS
    t90_samps = int(mrr.caldict['t90'] * mrr.FS)
    mags_abs = np.zeros(npulses)
    mags_r = np.zeros(npulses)

    for i in range(npulses):
        start = int((i+1) * tr_samps - width/2) + t90_samps
        mags_abs[i] = np.average(np.sum(np.abs(cp[:,start:start+width]),axis=0))

    cfig = plt.figure(figsize=(9,5))
    plt.plot(mags_abs[threshold:])
    plt.legend([str(mrr.caldict['f0'])])
    t2 = mrr.get_t2(mags_abs[threshold:], tr=500.2e-6)
    plt.xlabel("T2 = " + str(t2))
    try:
        plt.savefig(directory + "Figures/cpmg" + datetime.datetime.now().isoformat() + ".png")
    except Exception as e:
        print(e)
    plt.close(cfig)
    
    if(save):
        try:
            np.save(directory + datetime.datetime.now().isoformat() + '.npy', cp, allow_pickle=True)
        except Exception as e:
            np.save(backup_dir + datetime.datetime.now().isoformat() + '.npy', cp, allow_pickle=True)
            print(e)
        # np.save("/media/sdmrr/XDrive/Data/" + datetime.datetime.now().isoformat() + '.npy', cp, allow_pickle=True)
    print("T2: %0.2f" %  (t2))
    return t2

try:
    print(datetime.datetime.now().isoformat())
    ## Initialize the MRR
    mrr = SDMRR(nocal=True)
    time.sleep(0.1) #space out serial commands?
    
    t2data_br1 = np.load('t2data_br1.npy', allow_pickle=True)
    t2times_br1 = np.load('t2times_br1.npy', allow_pickle=True)
    t2data_br2 = np.load('t2data_br2.npy', allow_pickle=True)
    t2times_br2 = np.load('t2times_br2.npy', allow_pickle=True)

    #run first CPMG
    peri.stop(1)
    time.sleep(2) #changed from 2
    GPIO.output(15, GPIO.LOW)
    GPIO.output(14, GPIO.HIGH)
    t = datetime.datetime.now()
    mrr.cal(t90 = 0.00006, f0=22050900.0)
    mrr.RX_GAIN = 50
    t2 = gett2(save=True, amp90 = 0.31, amp180 = 0.62, directory = "/media/sdmrr/XDrive2/Run3_BR1/")

    if(t2 < 3):
        br1fig = plt.figure(figsize=(12,5))
        t2times_br1 = np.append(t2times_br1, t)
        t2data_br1 = np.append(t2data_br1, t2)

        plt.plot(t2times_br1, t2data_br1)
        # plt.plot(t2data_br1[7500:])
        # plt.ylim([1,1.75])
        plt.title("BR1 Culture T2")
        plt.ylabel("T2 (s)")
        plt.xlabel("Timestamp")
        plt.savefig('BR1_T2.png')

        plt.close(br1fig)

        np.save('t2data_br1.npy', t2data_br1, allow_pickle=True)
        np.save('t2times_br1.npy', t2times_br1, allow_pickle=True)
        
    else:
        print("CPMG Failed, likely bad calibration")
        
    peri.start(1)
#     time.sleep(0.1)
    
#     #Try another parameter set
#     time.sleep(5)
#     peri.stop(1)
    
#     time.sleep(0.1)

#     t = datetime.datetime.now()
#     mrr.RX_GAIN = 60
#     t2 = gett2(save=True, amp90 = 0.31, amp180 = 0.62, directory = "/media/sdmrr/XDrive2/Run3_BR1_Alt/")
#     mrr.RX_GAIN = 50
#     t2data_br1_alt = np.load('t2data_br1_alt.npy', allow_pickle=True)
#     t2times_br1_alt = np.load('t2times_br1_alt.npy', allow_pickle=True)

#     if(t2 < 3):
#         br1figalt = plt.figure(figsize=(12,5))
#         t2times_br1_alt = np.append(t2times_br1_alt, t)
#         t2data_br1_alt = np.append(t2data_br1_alt, t2)

#         plt.plot(t2times_br1_alt, t2data_br1_alt)
#         plt.title("BR1 Culture T2 (Alt)")
#         plt.ylabel("T2 (s)")
#         plt.xlabel("Timestamp")
#         plt.savefig('BR1_T2_Alt.png')

#         plt.close(br1figalt)

#         np.save('t2data_br1_alt.npy', t2data_br1_alt, allow_pickle=True)
#         np.save('t2times_br1_alt.npy', t2times_br1_alt, allow_pickle=True)
        
#     else:
#         print("CPMG Failed, likely bad calibration")

    # peri.start(1)
    #run second CPMG
    time.sleep(1)
    peri.stop(2)
    time.sleep(2)
    GPIO.output(14, GPIO.LOW)
    GPIO.output(15, GPIO.HIGH)
    mrr.cal(t90 = 0.00006, f0=22055500.0)
    t = datetime.datetime.now()
    t2 = gett2(save=True, amp90 = 0.275, amp180 = 0.55, directory = "/media/sdmrr/XDrive2/Run3_BR2/")

    if(t2 < 3):
        br2fig = plt.figure(figsize=(12,5))
        t2times_br2 = np.append(t2times_br2, t)
        t2data_br2 = np.append(t2data_br2, t2)

        plt.plot(t2times_br2, t2data_br2)
        plt.title("BR2 Culture T2")
        plt.ylabel("T2 (s)")
        plt.xlabel("Timestamp")
        plt.savefig('BR2_T2.png')

        plt.close(br2fig)

        np.save('t2data_br2.npy', t2data_br2, allow_pickle=True)
        np.save('t2times_br2.npy', t2times_br2, allow_pickle=True)
        
    else:
        print("CPMG Failed, likely bad calibration")
    # peri.setspeed(2, 55)
    # peri.setdir(2, 'cw')
    peri.start(2)
    
    
except Exception as e:
    print(e)
    # peri.setdir(1, 'cw')
    # peri.setdir(2, 'cw')
    peri.start(1) #turn the pump back on!
    time.sleep(0.1)
    peri.start(2) #turn the pump back on!
    peri = None
    
finally:
    if (peri != None):
        peri.setdir(1, 'cw')
        peri.setdir(2, 'cw')
        peri.start(1) #turn the pump back on!
        peri.start(2) #turn the pump back on!
        peri.setspeed(1, 55)
        peri.setspeed(2, 55)
        peri = None