#!/usr/bin/env python3

# To be called by trigger.sh

# TODO: Translation: https://lokalise.com/blog/beginners-guide-to-python-i18n/

from os.path import abspath
from os.path import islink
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
from mail_util import send_email


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

def main(config_file: str):
    global config, logger
    config = read_validate_config(config_file)

    # Set up logging based on configuration
    logger = Logging(config.logging)

    logger.log('started monitor.py')

    # Use the returned data sets
    logger.log("General Configuration:")
    logger.log(config)

    logger.log("\nPools Lookup Table:")
    for pool_name, pool_conf in config.pools.items():
        logger.log(f"{pool_name}: {pool_conf}")

    start_udev_monitoring()
    start_waiting_for_udev_trigger()

def start_udev_monitoring():
    logger.log('Using pyudev version: {0}'.format(pyudev.__version__))
    monitor = pyudev.Monitor.from_netlink(pyudev.Context())
    monitor.filter_by('block')
    global observer
    observer = pyudev.MonitorObserver(monitor, device_event)
    observer.start()

    # for device in iter(monitor.poll, None):
    #     logger.error('device %s event, action: %s, id: %s, label: %s', device, device.action, device.get('ID_FS_TYPE'), device.get('ID_FS_LABEL'))
    #     if device.action == "add" and device.get('ID_FS_TYPE') == "zfs_member":
    #         current_label = device.get('ID_FS_LABEL')
    #         logger.error('label: %s', current_label)
    #         try:
    #             check_call([backup_script, current_label])
    #         except Exception as e:
    #             print(e)

# Callback for device events
def device_event(action, device):
    fs_type = device.get('ID_FS_TYPE')
    fs_label = device.get('ID_FS_LABEL')
    fs_uuid = device.get('ID_FS_UUID')
    print(f"Event {action} for {fs_label} action {device.action} uuid {fs_uuid}")
    if fs_type == "zfs_member" and fs_label and fs_label in config.pools:
        beep()
        if action == "add":
            added_devices.put(fs_label)
            print(f"added: {added_devices}")
            backup_event.set()
        elif action == "remove":
            # removed_devices.put(fs_label)
            with finished_devices_lock:
                finished_devices.discard(fs_label)  # Remove from finished devices set if it's removed
            print(f"removed: {finished_devices}")
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
                print(f"added_devices: {added_devices}")
                mail(f"Plugged in disk {device_label} that is matching configuration:\n"+
                f"    {config.pools.get(device_label, None)}\n" + 
                "    Starting backup! You will receive an email once the backup has compled and you can safely unplug the disk.")
                backup(device_label)
                with finished_devices_lock:
                    finished_devices.add(device_label)  # Add to finished devices set
                # added_devices.task_done()
            
            # Reset the event in case this was the last added device being processed
            if added_devices.empty():
                backup_event.clear()

            # # If there are removed devices and no more added devices, begin beeping
            # if added_devices.empty() and not removed_devices.empty():
            #     # Beep for each removed device, but check for new added devices
            #     while not removed_devices.empty():
            #         if not added_devices.empty():  # If new added device, stop beeping and process it
            #             break  # Break out of the removed devices loop to handle added device
            #         device_label = removed_devices.get()
            #         logger.log(f"Removed: {device_label}")
            #         # removed_devices.task_done()
            #         beep()
            #         time.sleep(3)  # Beep every 3 seconds if removed devices list isn't empty
            
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

            # In case we broke out of beep because of an added device, make sure to clear the event
            # so it doesn't immediately trigger another backup loop without an actual event.
            # if not added_devices.empty():
                # backup_event.clear()

    except KeyboardInterrupt:
        logger.log("Received KeyboardInterrupt...")
    except Exception as e:
        logger.log(f"An unexpected error occurred: {e}")
    finally:
        logger.log("Stopping PYUDEV and Shutting down...")
        observer.stop()  # Stop observer
        sys.exit(0)

# Backup function
def backup(device_label):
    logger.log(f"Backing up {device_label}...")
    time.sleep(10)
    mail(f"Backup finished. You can safely unplug the disk {device_label} now")



def mail(message: str):
    logger.log(message)
    send_email("ZFS-Autobackup with UDEV Trigger", message, config.smtp, logger)
    # for recepient in config.smtp:
    #     send_linux_mail("ZFS-Autobackup with UDEV Trigger", message, recepient)

# def send_linux_mail(subject: str, body: str, recepient: str):
#     # body_str_encoded_to_byte = body.encode()
#     # return_stat = subprocess.run([f"mail", f"-s {Subject}", f"{Recepient}"], input=body_str_encoded_to_byte)
#     return_stat = subprocess.run(
#         ["mail", "-s", subject, recepient],
#         input= body.encode('utf-8'),
#         capture_output=True,  # to capture output for success/error diagnosis
#         check=True  # to raise an exception if the command fails
#     )
#     if return_stat.returncode == 0:
#         logger.log(return_stat)
#     else:
#         logger.error(return_stat)

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

    # Parse command-line arguments
    args = parser.parse_args()

    main(args.config_file)