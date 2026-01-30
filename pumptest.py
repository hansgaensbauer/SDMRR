from pump import *
import time

## Initialize the peristaltic pump
peri = Pump(output = True)
time.sleep(0.1)
peri.setdir('ccw')
time.sleep(0.1)
peri.start()
time.sleep(10)
peri.setdir('cw')
peri.getalarm()
time.sleep(0.1)
peri.start()