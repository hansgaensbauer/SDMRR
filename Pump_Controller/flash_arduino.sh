#!/bin/bash
arduino-cli compile --fqbn arduino:avr:nano .
arduino-cli upload -p /dev/ttyUSB1 --fqbn arduino:avr:nano .
