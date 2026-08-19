# Native compat layer for the InfinityX dockerctl stack

The InfinityX stack ran Docker in a Debian chroot at `/data/debian`. On the
KameOS Docker kernel it runs natively on bionic out of `/data/local/tmp/nd`.

Everything above the chroot boundary — `dockerctl`, `sshd.sh`, `relay.sh`,
`pumpd.sh`, `doctor.sh`, `trek.sh`, `fixall`, ~20 files — talks to it through
exactly four functions plus the daemon lifecycle:

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

* **The sshd-keeper container owns sshd's cgroup.** `docker rm -f sshd-keeper`
  kills sshd instantly — never over SSH; use adb or Portainer.
* **`fixall` cannot be run over SSH**: `ssh lan on` restarts sshd at step 2 of
  5, dropping your own connection before the container steps run.
* **`fixall` never clears `$STATE/battery.tripped`**, and `pwr_tick` returns
  early while it exists, so the battery guard comes back disarmed.
