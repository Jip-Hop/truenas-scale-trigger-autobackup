# Trigger zfs-autobackup when attaching backup disk

Automatically trigger [`zfs-autobackup`](https://github.com/psy0rz/zfs_autobackup) when an (external) backup disk is attached using the `udev-trigger-zfs-autobackup` daemon. Useful to store encrypted backups offline, on disks you can easily swap and store offsite. Works with USB, eSATA and disks in hotswap trays.

Specifically made for and tested on [TrueNAS SCALE](https://www.truenas.com/truenas-scale/), but made in a generic way so it should work on other hosts too. Please report if you try it on another host, like Proxmox or Ubuntu.

Monitors udev events to detect when new disks are attached. If the attached disk has a ZFS pool on it, and the zpool name matches one of the names set in the [config](./config_template.yaml) file, then it will be used as a backup disk. All datasets where the ZFS property `autobackup` matches the zpool name of the backup disk will be automatically backed up using `zfs-autobackup`.

## Usage
```
Usage: trigger.sh [-h] [-v] [--install] [--force-install] [--update-dependencies] [--start] [--stop] [--check-monitor] [--test]

Daemon to trigger zfs-autobackup when attaching backup disk.

1. Manually create (encrypted) ZFS pool(s) on removable disk(s).
2. Manually edit config to specify the names of your backup pool(s), the zfs-autobackup parameters and the encryption passphrase.
3. Manually schedule 'trigger.sh --start' to run at system startup.
   On TrueNAS SCALE: System Settings -> Advanced -> Init/Shutdown Scripts -> Add
    Description: trigger-zfs-autobackup;
    Type: Script;
    Script: '/path/to/trigger.sh --start';
    When: Post Init 
   -> Save
4. Manually insert backup disk whenever you want to make a backup.
5. Automatic backup is triggered and sends email on completion.

Available options:

-h, --help                       Print this help and exit
-v, --verbose                    Print script debug info
-i, --install [HEAD,tag,hash]    Install script and dependencies
-f, --force-install              Force the installation of dependencies by deleting the venv.
-u, --update-dependencies        Update dependencies only
-s, --start /path/to/config.yaml Start the udev monitor with your config.yaml file
-p, --stop                       Stop the udev monitor
-m, --check-monitor              Check if the udev monitor is running
-t, --test /path/to/config.yaml  Test the zfs-autobackup with the given monitor. Disk must be already imported.
```

## Security

For security reasons, ensure only `root` can modify and read the `udev-trigger-zfs-autobackup` files. The scripts will be automatically executed with `root` privileges, so you don't want anyone to modify what they do or see your passwords/passphrases.

## Setup

### Prepare backup disk

If `udev-trigger-zfs-autobackup` is already installed, then temporarily disable the trigger by executing `trigger.sh --stop`.

Execute the following commands to prepare a backup disk to use with `udev-trigger-zfs-autobackup`. Please read the commands (and comments!) carefully before executing them. You have to change several values.

```bash
# Carefully determine which disk to format as backup disk!
# All data on it will be lost permanently!
DISK=/dev/disk/by-id/usb-SanDisk_Ultra_Fit_XXXXXXXXXXXXXXXXXXXX-0:0
# Decide on a name for your backup pool
POOL=offsite1

wipefs -a $DISK
sgdisk --zap-all $DISK
sgdisk --new=1:0:0 --typecode=1:BF00 $DISK

# Use failmode=continue to prevent system from hanging on unclean device disconnect
# If you don't want to use encryption, then remove the encryption and keylocation options
zpool create \
    -O encryption=aes-256-gcm \
    -O keylocation=prompt -O keyformat=passphrase \
    -O acltype=posixacl \
    -O compression=zstd \
    -O atime=off \
    -O aclmode=discard \
    -O aclinherit=passthrough \
    -o failmode=continue \
    -R /mnt \
    $POOL $DISK

# If using encryption, you'll be asked to type your passphrase two times. Don't forget to manually edit the config file and put the passphrase in there when installing udev-trigger-zfs-autobackup

# Export the pool and manually disconnect the disk
zpool export $POOL

# Manually set autobackup:offsite1 on the datasets you want to backup (exchange offsite1 for the value chosen voor POOL above)
```

Don't forget to re-enable the backups by executing `trigger.sh --start` in case you had installed `udev-trigger-zfs-autobackup` before.

### Install udev-trigger-zfs-autobackup

Download the trigger.sh file on the system you want to backup into a directory that will survive updates of TrueNAS Scale.
```bash
# Create a folder where you want to install the script
mkdir udev-trigger-zfs-autobackup
cd udev-trigger-zfs-autobackup

# Download trigger.sh
curl -LJO https://raw.githubusercontent.com/ghan1t/udev-trigger-zfs-autobackup/main/trigger.sh

# make trigger.sh executable
chmod +x trigger.sh

# Run install to download this repository, create a Python virtual environment and download dependencies to it.
./trigger.sh --install

# You can optionally specify which version of this script to download in case main is broken:
./trigger.sh --install <tag>  # download a specific tag
./trigger.sh --install <sha1> # download a specific commit hash
./trigger.sh --install HEAD   # download HEAD of the main branch
```
This will install the dependencies locally using a Python virtual environment. The installation makes no modifications to the system outside of its installation directory. This is to ensure `udev-trigger-zfs-autobackup` will survive updates of TrueNAS SCALE (as long as you store it on one of your data pools, and not on the disks where the TrueNAS base system is installed).

### Update udev-trigger-zfs-autobackup
Run the following commands 
```bash
# Disable any running udev monitor
./trigger.sh --stop

# Update the script and its dependencies
./trigger.sh --install

# Restart the udev monitor
./trigger.sh --start /path/to/your/config.yaml
```

If the update of PyYAML fails, you can try the following:
1. Force update PyYAML
```bash
# cd into your script directory
cd /path/to/your/udev-trigger-directory

# enter venv
. venv/bin/activate

# install PyYAML
pip install --ignore-installed PyYAML

# leave venv
deactivate
```

2. Delete venv with -f, --force-install 
```bash
# install fresh
./trigger.sh --force-install
```

### Edit config

You need to edit the config file. Make a copy of [config_template](./config_template.yaml) file and put it somewhere outside of your script directory to prevent it from being overwritten during updates. Specify the names of your backup pools and their zfs-autobackup parameters and encryption passphrase. Each backup pool can only have one configuration.

If you modify the config you need to restart the script it with `trigger.sh --stop` and then `trigger.sh --start /path/to/your/config.yaml`.

### Schedule udev-trigger-zfs-autobackup

The [trigger.sh](./trigger.sh) script needs to run on system startup. You need to manually this, for example using `cron` or `systemd`. On TrueNAS SCALE you can schedule the script via the web interface:
System Settings -> Advanced -> Init/Shutdown Scripts -> Add
  Description: trigger-zfs-autobackup;
  Type: Script;
  Script: `/path/to/trigger.sh --start /path/to/your/config.yaml`;
  When: Post Init 
-> Save

### Choose data sources

Add the `autobackup` property to the datasets you want to backup automatically to a backup pool. For example, to automatically backup the dataset `data` to backup pool `offsite1` run: `zfs set autobackup:offsite1=true data`. You can exclude descending datasets. For example excluding `ix-applications` would work like this: `zfs set autobackup:offsite1=false data/ix-applications`.

## Trigger backup

Connect your backup disk to trigger the automatic backup. You'll hear a beep confirming the start of the backup and you'll receive an email with the summary of the backup job. Once the backup is finished, you'll hear a beep every 3 seconds until you disconnect the disk.

Note: udev is not instantaneous and it might take a few seconds to recognise that you connected or disconnected a disk.

### Manual trigger

If your backup somehow failed and you want to try again without unplugging the disk, you can do the following:

1. Export pool
```bash
zpool export PoolName
```

2. Restart Script
```bash
./trigger.sh --stop
./trigger.sh --start /path/to/your/config.yaml
```

3. Figure out your disks device name (e.g. 'sdg')
```bash
ls -l /dev/disk/by-label
```

4. Trigger disk addition
```bash
udevadm trigger --action=add --name-match=<device name>
```

## Disable automatic backup

To (temporarily) disable executing automatic backups, execute `trigger.sh --stop`.

## Snapshots / versioning

A ZFS snapshot will be made before each backup. Snapshots will be kept according to the default schedule from the [zfs-autobackup Thinner](https://github.com/psy0rz/zfs_autobackup/wiki/Thinner).

```
[Source] Keep the last 10 snapshots.
[Source] Keep every 1 day, delete after 1 week.
[Source] Keep every 1 week, delete after 1 month.
[Source] Keep every 1 month, delete after 1 year.
```

I recommend to create a separate cronjob on the host, to frequently take snapshots (not just when you plugin your backup disk). These snapshots will then also be transferred to the backup disk once you connect it. Your backup will contain more snapshots and you'll have more 'versions' to recover from.

The command to schedule via cron could look something like this: `cd /path/to/udev-trigger-zfs-autobackup && . venv/bin/activate && zfs-autobackup offsite1`. Don't forget to change the path and replace `offsite1` with the `autobackup` ZFS property you added to your source datasets. Then schedule it to run hourly.

## Recovery

[Temporarily disable automatic backups](#disable-automatic-backup) then connect your backup disk. Manually import the pool (offsite1 in this example) with `zpool import offsite1 -R /mnt`. Unlock the pool with `zfs load-key offsite1` and enter the passphrase from your [config](./config) file. [Recursively mount the pool](https://serverfault.com/a/542662) and descendant datasets with `zfs list -rH -o name offsite1 | xargs -L 1 zfs mount`. You can now cd into it with `cd /mnt/offsite1` and list the contents. Snapshots are found in a `.zfs` subdirectory inside each dataset. E.g. `/mnt/offsite1/.zfs/snapshot`. You could also call `zfs mount -a` to mount the pool and descending datasets, but it will mount all available ZFS file systems (not just the ones on your backup disk) so it may have side effects. [There's currently no `zfs` command to recursively mount a specific dataset](https://github.com/openzfs/zfs/issues/2901).

Note: This tool uses zfs commands to import and decrypt pools. You will not see them on the TrueNAS GUI.

## Further reading

I recommend reading the [zfs-autobackup documentation](https://github.com/psy0rz/zfs_autobackup) if you want to use `udev-trigger-zfs-autobackup`.
