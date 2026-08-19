# Native compat layer for the InfinityX dockerctl stack

The InfinityX stack ran Docker in a Debian chroot at `/data/debian`. On the
KameOS Docker kernel it runs natively on bionic out of `/data/local/tmp/nd`.

Everything above the chroot boundary — `dockerctl` and the ~20 service scripts
beside it — talks to it through exactly four functions plus the daemon
lifecycle:

    mount_chroot  umount_chroot  in_chroot  in_chroot_exec
    daemon_start  daemon_stop

So only `mount.sh` and `daemon.sh` are replaced. `lib.sh`, `net.sh`, `ui.sh`
and the rest are restored from the backup unchanged.

## Restore

```bash
tar xzf backups/dump-20260804-022700/adb-docker.tgz -C /tmp/r
adb push /tmp/r/docker /data/adb/          # the whole old stack
adb push scripts/device/native-compat/mount.sh  /data/adb/docker/mount.sh
adb push scripts/device/native-compat/daemon.sh /data/adb/docker/daemon.sh
adb shell su -c 'chmod 755 /data/adb/docker/*'
adb shell su -c '/data/adb/docker/dockerctl start'
```

Volumes come from `docker-volumes.tgz`, restored into `$ND/data`.

## Deliberately not restored

`docker-enabler` (the Magisk module) was built against InfinityX's kernel and
the chroot path. Its boot hook is replaced by `service.d-native-docker.sh`.

## Traps carried over from the old stack

These are generic to running sshd from a container on Android, and each was hit
for real:

* **A container that owns sshd's cgroup kills sshd when removed.** `docker rm -f`
  on it drops your session mid-script, so the command that would have recreated
  it never runs. Do that over adb, never over SSH.
* **Any repair script that restarts sshd cannot be run over SSH.** If the
  restart is step 2 of 5, steps 3-5 never execute and you cannot see that they
  did not.
* **A tripped battery guard is sticky.** Repair scripts that do not clear the
  trip flag bring the stack back with the guard permanently disarmed.
