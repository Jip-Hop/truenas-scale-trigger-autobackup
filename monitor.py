#!/usr/bin/env python3

# To be called by trigger.sh
import os
from subprocess import check_call
import pyudev

import subprocess
import configparser
import argparse
from config_reader import read_validate_config
import threading
import time
import queue
import sys
from log_util import Logging
from backup import decrypt_and_backup, import_decrypt_backup_export

# Shared resources
added_devices = queue.Queue()
removed_devices = queue.Queue()
finished_devices = set()  # Using a set for finished devices
finished_devices_lock = threading.Lock()  # Lock for accessing the finished_devices set

# Event to indicate there are devices to process
backup_event = threading.Event()
observer = None
pools_lookup = None
config = None
logger = None

def main(config_file: str, test: bool):
    global config, logger
    config = read_validate_config(config_file)

    # Set up logging based on configuration
    logger = Logging(config.logging)

    logger.log(f"started monitor.py with config:\n{config}")
    if test:
        for device_label, pool_config in config.pools.items():
            if is_device_connected(device_label):
                beep_pattern("1111001010", 0.2, 0.1)
                logger.log(f"Starting manual backup on Pool {device_label}...")
                decrypt_and_backup(device_label, pool_config, config, logger)
    else:
        start_udev_monitoring()
        start_waiting_for_udev_trigger()        

def start_udev_monitoring():
    logger.log('Using pyudev version: {0}'.format(pyudev.__version__))
    monitor = pyudev.Monitor.from_netlink(pyudev.Context())
    monitor.filter_by('block')
    global observer
    observer = pyudev.MonitorObserver(monitor, device_event)
    observer.start()

# Callback for device events
def device_event(action, device):
    fs_type = device.get('ID_FS_TYPE')
    fs_label = device.get('ID_FS_LABEL')
    fs_uuid = device.get('ID_FS_UUID')
    # print(f"Event {action} for {fs_label} action {device.action} uuid {fs_uuid}")
    if fs_type == "zfs_member" and fs_label and fs_label in config.pools:
        beep()
        if action == "add":
            added_devices.put(fs_label)
            logger.log(f"udev observed add of pool {fs_label}")
            backup_event.set()
        elif action == "remove":
            logger.log(f"udev observed remove of pool {fs_label}")
            with finished_devices_lock:
                finished_devices.discard(fs_label)  # Remove from finished devices set if it's removed
            backup_event.set()

def start_waiting_for_udev_trigger():
    # Main processing logic
    try:
        while True:
            backup_event.wait()  # Wait for an event
            # Check for added devices first
            while not added_devices.empty():
                beep_pattern("101111001010", 0.2, 0.1)
                device_label = added_devices.get()
                logger.log(f"Pool {device_label} has been added to queue. Starting backup...")
                import_decrypt_backup_export(device_label, config, logger)
                with finished_devices_lock:
                    finished_devices.add(device_label)  # Add to finished devices set
            
            # Reset the event in case this was the last added device being processed
            if added_devices.empty():
                backup_event.clear()
     
            # If there are finished devices and no more added devices, begin beeping
            # Continuously beep for finished devices if they are still connected
            while True:
                with finished_devices_lock:
                    if not finished_devices:
                        break  # Exit the loop if finished_devices is empty
                    for device_label in list(finished_devices):  # Iterate over a copy
                        if not is_device_connected(device_label):
                            finished_devices.discard(device_label)
                beep()
                time.sleep(3)  # Delay between each check

    except KeyboardInterrupt:
        logger.log("Received KeyboardInterrupt...")
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")
    finally:
        logger.log("Stopping PYUDEV and Shutting down...")
        observer.stop()  # Stop observer
        sys.exit(0)

def is_device_connected(device_label):
    # Path where disk labels are linked
    disk_by_label_path = '/dev/disk/by-label/'

    # Check if a symbolic link exists for this label
    return os.path.islink(os.path.join(disk_by_label_path, device_label))

def beep():
    open('/dev/tty5','w').write('\a')

def beep_pattern(pattern, sleep_duration, beep_duration):
    for digit in pattern:
        if digit == '1':
            beep()
            time.sleep(beep_duration)
        elif digit == '0':
            time.sleep(sleep_duration)
        else:
            print("Invalid character in binary string")

if __name__ == "__main__":
     # Set up command-line argument parsing
    parser = argparse.ArgumentParser(description="Process a YAML config file.")
    parser.add_argument('config_file', type=str, help='Path to the YAML config file to be processed')
    parser.add_argument("--test", help="test the zfs-backup with the given YAML config file", action="store_true")

    # Parse command-line arguments
    args = parser.parse_args()

    main(args.config_file, args.test)