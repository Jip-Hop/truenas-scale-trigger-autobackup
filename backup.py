import io
import sys
from contextlib import redirect_stdout, redirect_stderr
from zfs_autobackup.ZfsAutobackup import *
from typing import Optional
from log_util import Logging
from mail_util import mail, mail_error, mail_exception
from config_reader import AppConfig, PoolConfig
import subprocess
import traceback

# Backup function
def import_decrypt_backup_export(device_label, config: AppConfig, logger: Logging):
    pool_config = config.pools.get(device_label, None)
    if pool_config is None:
        mail(f"Plugged in disk {device_label} that is not matching any configuration. You can unplug it again safely.",
             config.smtp, logger)
    else:
        mail(f"Plugged in disk {device_label} that is matching configuration:\n"+
             f"{pool_config}\n\n" + 
              "Starting the backup now. You will receive an email once the backup has completed and you can safely unplug the disk.",
             config.smtp, logger)

        try:
            logger.log(f"Importing pool {device_label}")
            result = import_pool(device_label, logger)
            if result.returncode != 0:
                mail_error(f"Failed to import pool. Backup not yet run.\n\nError:\n{result.stderr}", config.smtp, logger)
                return

            backup_successful, captured_output, captured_error = decrypt_and_backup(device_label, pool_config, config, logger)
            if not backup_successful:
                return
            
            logger.log(f"Exporting {device_label}")
            result = export_pool(device_label, logger)
            if result.returncode != 0:
                mail_error(f"Failed to export pool.\n\nError:\n{result.stderr}", config.smtp, logger)
                return

            if config.smtp is None:
                logger.log(f"Backup finished. You can safely unplug the disk {device_label} now.")
            elif config.smtp.send_autobackup_output:
                mail(f"Backup finished. You can safely unplug the disk {device_label} now.\n\nZFS-Autobackup output:\n{captured_output}", config.smtp, logger)
            else:
                mail(f"Backup finished. You can safely unplug the disk {device_label} now.", config.smtp, logger)

        except Exception as e:
            mail_error(f"An unexpected error occurred. Backup may have failed. Please investigate.\n\nError:\n{e}\n{traceback.format_exc()}", config.smtp, logger)
        
def decrypt_and_backup(device_label, pool_config: PoolConfig, config: AppConfig, logger: Logging) -> bool | str | str:
    if pool_config is None:
        mail(f"Plugged in disk {device_label} that is not matching any configuration. You can unplug it again safely.",
             config.smtp, logger)
        return False, None, None
    else:
        try:
            if pool_config.passphrase is not None and pool_config.passphrase:
                logger.log(f"Decrypting pool {device_label}")
                result = decrypt_pool(device_label, pool_config.passphrase, logger)
                if result.returncode != 0:
                    mail_error(f"Failed to decrypt pool. Backup not yet run.\n\nError:\n{result.stderr}", config.smtp, logger)
                    return False, None, None
        
            logger.log(f"Starting ZFS-Autobackup for pool {device_label} with parameters:\nzfs-autobackup " + " ".join(pool_config.autobackup_parameters))
            captured_output, captured_error = run_zfs_autobackup(pool_config.autobackup_parameters, logger)
           
            if does_capture_contain_errors(captured_output, False, config, logger) or does_capture_contain_errors(captured_error, True, config, logger):
                return False, None, None
                
            logger.log(f"Setting pool {device_label} to read-only")
            result = set_pool_readonly(device_label, logger)
            if result.returncode != 0:
                mail_error(f"Failed to set pool readonly. Disk will not be exported automatically.\n\nError:\n{result.stderr}\n\nBackup was successful:\n{captured_output}\n\n{captured_error}", config.smtp, logger)
                return False, None, None
            return True, captured_output, captured_error
        except Exception as e:
            mail_exception(f"An unexpected error occurred. Backup may have failed. Please investigate.\n\nError:\n{e}\n\nBackup output:\n{captured_output}\n\n{captured_error}", config.smtp, logger)
            return False, None, None

def run_zfs_autobackup(args, logger: Logging) -> str | str:
    """
    Runs the ZfsAutobackup CLI with given arguments and captures its stdout output.

    :param args: List of command-line arguments to pass to ZfsAutobackup CLI.
    :return: The captured stdout output as a string.
    """
    # Backup the original sys.argv
    original_argv = sys.argv

    # Capture both standard output and standard error
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
        try:
            # Set sys.argv to the CLI tool's expected input
            sys.argv = ['zfs-autobackup'] + args
            # Call the CLI function
            cli()
        except SystemExit as e:
            # Handle the sys.exit call; could log or re-raise if needed
            pass
        finally:
            # Restore the original sys.argv
            sys.argv = original_argv

    # Return the captured output
    return stdout_capture.getvalue(), stderr_capture.getvalue()

def import_pool(pool: str, logger: Logging) -> subprocess.CompletedProcess:
    return run_command(logger, ["zpool", "import", pool, "-N"])

def export_pool(pool: str, logger: Logging) -> subprocess.CompletedProcess:
    return run_command(logger, ["zpool", "export", pool])

def decrypt_pool(pool: str, passphrase: str, logger: Logging) -> subprocess.CompletedProcess:
    run_command(logger, ["zfs", "load-key", pool], input_data=passphrase)

def set_pool_readonly(pool: str, logger: Logging) -> subprocess.CompletedProcess:
    return run_command(logger, ["zfs", "set", "readonly=on", pool])

def run_command(logger: Logging, command, input_data=None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, input=input_data, text=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        logger.error(f"An error occurred: {e}")
        return subprocess.CompletedProcess(e.cmd, e.returncode, stdout=e.output, stderr=e.stderr)

def does_capture_contain_errors(capture: str, stderr: bool, config: AppConfig, logger: Logging) -> bool:
    # Assuming run_zfs_autobackup returns a string, check if it indicates an error
    if "error" in capture.lower() or (stderr and capture):
        if config.smtp is None:
            logger.log(f"ZFS autobackup error! Disk will not be exported automatically.")
        elif config.smtp.send_autobackup_output:
            mail_error(f"ZFS autobackup error! Disk will not be exported automatically:\n\n{capture}", config.smtp, logger)
        else:
            mail_error(f"ZFS autobackup error! Disk will not be exported automatically. Check logs for details.", config.smtp, logger)
        return True
    elif capture:
        logger.log(capture)
        return False