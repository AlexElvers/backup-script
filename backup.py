#!/usr/bin/env python3

import sys
import os
import codecs
import time
import logging
import yaml
import coloredlogs
from sh import rsync, wget

logger = logging.getLogger("backup")
coloredlogs.install(logger=logger)
logger.setLevel("DEBUG")


class Backup:
    def load_config(self, file="config.yaml"):
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
        self.UUID_LIST = config.get("drives", [])
        self.PATHS = config.get("paths", [])
        self.EXCLUDES = config.get("excludes", [])

        # /mount/path/SNAP/ is base path
        # /mount/path/SNAP/LAST is latest snapshot
        # /mount/path/SNAP/YYYY-MM-DD snapshot with timestamp
        self.SNAP = config.get("base-dir", "snapshots")
        self.LAST = config.get("last-dir", "last")

        # rsync options
        self.OPT = "-vvaPh"

        self.EXCLUDES_URL = "https://raw.githubusercontent.com/rubo77/rsync-homedir-excludes/master/rsync-homedir-excludes.txt"
        self.EXCLUDES_FILE = "excludes.txt"

        self.DIR_MODE = int("0o755", 8)

    def download_excludes(self):
        wget("-O", self.EXCLUDES_FILE, self.EXCLUDES_URL)
        with open(self.EXCLUDES_FILE, "a") as f:
            f.write("\n\n#config.yaml:\n" + "\n".join(self.EXCLUDES) + "\n")

    def get_mounts(self):
        mounts = {}
        with open("/proc/mounts") as f:
            for l in f:
                if l.startswith("/") and " " in l:
                    k, v = l.split()[:2]
                    mounts[k] = codecs.unicode_escape_decode(v)[0]
        return mounts

    def get_snapshot_drives(self, uuids=None):
        if not uuids:
            uuids = self.UUID_LIST
        mounts = self.get_mounts()
        drives = []
        for uuid in uuids:
            dev = os.path.realpath(os.path.join("/dev/disk/by-uuid", uuid))
            try:
                snapshot_path = os.path.join(mounts[dev], self.SNAP)
            except KeyError:
                drives.append((uuid, None))
                continue
            drives.append((uuid, (dev, snapshot_path)))
        return drives

    def create_all_snapshots(self, uuids=None):
        drives = self.get_snapshot_drives(uuids)
        for drive in drives:
            if drive[1]:
                self.create_snapshot(drive)
            else:
                logger.warning("[%s] not mounted", drive[0])

    def create_snapshot(self, drive):
        uuid, (dev, path) = drive
        if os.path.exists(path):
            logger.info("[%s] found snapshot dir at '%s'", uuid, path)
        else:
            os.makedirs(path, mode=self.DIR_MODE, exist_ok=True)
            logger.info("[%s] created '%s'", uuid, path)

        last_path = os.path.join(path, self.LAST)
        snapshot_path = self.get_snapshot_path(path)

        for src in self.PATHS:
            dest = os.path.join(snapshot_path, src.strip("/"))
            os.makedirs(os.path.dirname(dest), mode=self.DIR_MODE, exist_ok=True)
            segment_count = 1 + len([x for x in src.split("/") if x])
            link_dest = os.path.join("../"*segment_count, self.LAST, src.strip("/"))
            self.rsync(src, dest, link_dest)

        self.recreate_symlink(snapshot_path, last_path)

        os.sync()

    def rsync(self, src, dest, link_dest):
        rsync(
            self.OPT, src + "/", dest,
            link_dest=link_dest,
            exclude_from=self.EXCLUDES_FILE,
            _out=sys.stdout.buffer
        )

    def recreate_symlink(self, snapshot_path, last_path):
        try:
            os.remove("-f", last_path, _out=sys.stdout.buffer)
        except OSError:
            pass
        os.symlink(os.path.relpath(snapshot_path, os.path.dirname(last_path)), last_path)

    def get_snapshot_path(self, path):
        date = time.strftime("%Y-%m-%d")
        snapshot_path = os.path.join(path, date)

        i = 1
        while os.path.exists(snapshot_path):
            snapshot_path = os.path.join(path, "%s_%d" % (date, i))
            i += 1

        return snapshot_path


if __name__ == "__main__":
    if os.getuid() != 0:
        print("you must be root")
        sys.exit(1)

    backup = Backup()
    backup.load_config()
    backup.download_excludes()
    backup.create_all_snapshots()
