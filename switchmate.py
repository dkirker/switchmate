#! /usr/bin/env python

"""switchmate.py

A python-based command line utility for controlling Switchmate switches

Usage:
	./switchmate.py scan
	./switchmate.py status [<mac_address>]
	./switchmate.py <mac_address> auth
	./switchmate.py <mac_address> switch [on | off]
	./switchmate.py -h | --help
"""

from __future__ import print_function
import struct
import sys
import ctypes

from docopt import docopt
from bluepy.btle import Scanner, DefaultDelegate, Peripheral, ADDR_TYPE_RANDOM
from binascii import hexlify, unhexlify

SWITCHMATE_SERVICE = 'abd0f555eb40e7b2ac49ddeb83d32ba2'
# SWITCHMATE_SERVICE = '23d1bcea5f782315deef121223150000'
NOTIFY_VALUE = struct.pack('<BB', 0x01, 0x00)

AUTH_NOTIFY_HANDLE = 0x0017
AUTH_HANDLE = 0x0016
AUTH_INIT_VALUE = struct.pack('<BBBBBB', 0x00, 0x00, 0x00, 0x00, 0x01, 0x00)

#STATE_HANDLE = 0x000e
#STATE_NOTIFY_HANDLE = 0x000f

BATTERY_HANDLE = 0x0010
CLOCK_HANDLE = 0x001f
ORIENTATION_HANDLE = 0x002e
STATE_HANDLE = 0x002b
STATE_NOTIFY_HANDLE = 0x002c
TOGGLE_STATE_HANDLE = 0x0030
TOGGLE_RESET_HANDLE = 0x0029
TIMER1_STATE_HANDLE = 0x0021
TIMER2_STATE_HANDLE = 0x0023
MOTION_TIMER_STATE_HANDLE = 0x0032

# Some notes (edited) from https://community.home-assistant.io/t/switchmate-switch-covers/17851/28
#
# 0010 = Battery level. appears to be 100%. Will know more as my batteries die. :slight_smile:
# 001f (a22b0010) = system clock of some sort
# 002e (a22b0080) = "Reverse" inverted bit: 00 for normal orientation, 01 for inverted. Will toggle switch to match the current on/off state with respect to orientation.
# 002c = status notify
# 002b (a22b0070, read/notify only) = status bit: 00 for off, 01 for on
# 0030 (a22b0090) = state set: 0x00 = off, 0x01 = on
# 0029 (assb0060) = toggle / reset?: when read, value is always 00, but when 01 is written to it, switch toggles and BT connection to device is immediately dropped
# 0021 (a22b0020) = state of Timer 1. This is a 1-byte word for enabled/disabled, and a 5-byte word and encodes the time / day settings from the app.
# 0023 (a22b0030) = state of Timer 2. Same as above.
# 0032 (a22b00d0) = state of Motion Detection timer. Same as above.

def c_mul(a, b):
	'''
	Multiplication function with overflow
	'''
	return ctypes.c_int64((long(a) * b) &0xffffffffffffffff).value

def sign(data, key):
	'''
	Variant of the Fowler-Noll-Vo (FNV) hash function
	'''
	blob = data + key
	x = ord(blob[0]) << 7
	for c in blob:
		x1 = c_mul(1000003, x)
		x = x1 ^ ord(c) ^ len(blob)

	# once we have the hash, we append the data
	shifted_hash = (x & 0xffffffff) << 16
	shifted_data_0 = ord(data[0]) << 48
	shifted_data_1 = ord(data[1]) << 56
	packed = struct.pack('<Q', shifted_hash | shifted_data_0 | shifted_data_1)[2:]
	return packed

class NotificationDelegate(DefaultDelegate):
	def __init__(self):
		DefaultDelegate.__init__(self)

	def handleNotification(self, handle, data):
		print('')
		succeeded = True
		if handle == AUTH_HANDLE:
			print('Auth key is {}'.format(hexlify(data[3:]).upper()))
		else:
			if ord(data[-1]) == 0:
				print('Switched!')
			else:
				print('Switching failed!')
				succeeded = False
		device.disconnect()
		sys.exit(0 if succeeded else 1)

class ScanDelegate(DefaultDelegate):
	def __init__(self, mac_address):
		DefaultDelegate.__init__(self)
		self.mac_address = mac_address
		self.seen = []

	def handleDiscovery(self, dev, isNewDev, isNewData):
		if self.mac_address != None and self.mac_address != dev.addr:
			return

		if dev.addr in self.seen:
			return
		self.seen.append(dev.addr)

		AD_TYPE_UUID = 0x07
		AD_TYPE_SERVICE_DATA = 0x16
		if dev.getValueText(AD_TYPE_UUID) == SWITCHMATE_SERVICE:
			device = Peripheral(dev.addr, ADDR_TYPE_RANDOM)
			data = device.readCharacteristic(STATE_HANDLE) # dev.getValueText(AD_TYPE_SERVICE_DATA)
			# the bit at 0x0100 signifies if the switch is off or on
			print(dev.addr + ' ' + hexlify(data)) # ("off", "on")[(int(data, 16) >> 8) & 1])
			scanData = dev.getScanData()
			print('Scan data: ' + str(scanData))
			characteristics = device.getCharacteristics()
			print('Characteristics: ')
			for character in characteristics:
				print('   ' + hex(character.getHandle()) + ': ' + character.propertiesToString())
			if self.mac_address != None:
				sys.exit()

def status(mac_address):
	print('Looking for switchmate status...')
	sys.stdout.flush()

	scanner = Scanner().withDelegate(ScanDelegate(mac_address))

	scanner.clear()
	scanner.start()
	scanner.process(20)
	scanner.stop()

def scan():
	print('Scanning...')
	sys.stdout.flush()

	scanner = Scanner()
	devices = scanner.scan(10.0)

	SERVICES_AD_TYPE = 7

	switchmates = []
	for dev in devices:
		for (adtype, desc, value) in dev.getScanData():
			is_switchmate = adtype == SERVICES_AD_TYPE and value == SWITCHMATE_SERVICE
			if is_switchmate and dev not in switchmates:
				switchmates.append(dev)

	if len(switchmates):
		print('Found Switchmates:')
		for switchmate in switchmates:
			print(switchmate.addr)
	else:
		print('No Switchmate devices found');

if __name__ == '__main__':
	arguments = docopt(__doc__)

	if arguments['scan']:
		scan()
		sys.exit()

	if arguments['status']:
		status(arguments['<mac_address>'])
		sys.exit()

	device = Peripheral(arguments['<mac_address>'], ADDR_TYPE_RANDOM)

	notifications = NotificationDelegate()
	device.setDelegate(notifications)

	if arguments['switch']:
		# auth_key = unhexlify(arguments['<auth_key>'])
		device.writeCharacteristic(STATE_NOTIFY_HANDLE, NOTIFY_VALUE, True)
		if arguments['on']:
			val = '\x01'
		else:
			val = '\x00'
		device.writeCharacteristic(TOGGLE_STATE_HANDLE, val ) # sign('\x01' + val, auth_key))
	else:
		device.writeCharacteristic(AUTH_NOTIFY_HANDLE, NOTIFY_VALUE, True)
		device.writeCharacteristic(AUTH_HANDLE, AUTH_INIT_VALUE, True)
		print('Press button on Switchmate to get auth key')

	print('Waiting for response', end='')
	while True:
		device.waitForNotifications(1.0)
		print('.', end='')
		sys.stdout.flush()
