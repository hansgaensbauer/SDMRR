# SDMRR
Software Defined MRR

A USRP Based MRR for use as a flexible and easily modified instrument. Currently, this instrument supports FIDs and CPMG, and it also has the ability to control peristaltic pumps
and pinch valves for sequencing. 

The code for the pump/valve controller is also included in this repository. 

## Setup
Install the 64 bit Raspberry Pi OS with Desktop. Configure the hostname and enable SSH with the right username and password.

``` bash
#Install the PyPy 3.9 Version of Conda Forge: Miniforge3-Linux-aarch64. 
#Use the default install directory, and allow it to initialize the base environment by default.
wget https://github.com/conda-forge/miniforge/releases/latest/download/Mambaforge-pypy3-Linux-aarch64.sh
sudo chmod +x Mambaforge-pypy3-Linux-aarch64.sh
./Mambaforge-pypy3-Linux-aarch64.sh

source ~/.bashrc #this will initialize the base env

mamba update python #update python

mamba create -n radioconda -c conda-forge -c ryanvolz --only-deps radioconda #Install radioconda 

conda activate radioconda

#Blacklist bad drivers
sudo ln -s $CONDA_PREFIX/etc/modprobe.d/rtl-sdr-blacklist.conf /etc/modprobe.d/radioconda-rtl-sdr-blacklist.conf
sudo modprobe -r $(cat $CONDA_PREFIX/etc/modprobe.d/rtl-sdr-blacklist.conf | sed -n -e 's/^blacklist //p')

#Udev rule
sudo ln -s $CONDA_PREFIX/lib/udev/rules.d/rtl-sdr.rules /etc/udev/rules.d/radioconda-rtl-sdr.rules
sudo udevadm control --reload
sudo udevadm trigger

#test the installation (plug in an RTL-SDR)
rtl_test
```
