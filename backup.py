#!/usr/bin/env python3

import sys
import os
import codecs
import time
import logging
import coloredlogs
# from sh import echo as rsync, echo as rm, echo as ln
from sh import rsync, rm, ln

logger = logging.getLogger("backup")
coloredlogs.install(logger=logger)
logger.setLevel("DEBUG")


# uuids of partitions for storing snapshots
UUID_LIST = [
    "00000000-0000-0000-0000-000000000000",
]

PATHS = [
    "/etc",
    "/home/alex",
]

# /mount/path/SNAP/ is base path
# /mount/path/SNAP/LAST is latest snapshot
# /mount/path/SNAP/YYYY-MM-DD snapshot with timestamp
SNAP = "snapshots"
LAST = "last"

# rsync options
OPT = "-vvaPh"

if os.getuid() != 0:
    print("you must be root")
    sys.exit(1)

def get_mounts():
    mounts = {}
    with open("/proc/mounts") as f:
        for l in f:
            if l.startswith("/") and " " in l:
                k, v = l.split()[:2]
                mounts[k] = codecs.unicode_escape_decode(v)[0]
    return mounts

def get_base_path(uuid):
    return os.path.join(mounts[os.path.realpath(os.path.join("/dev/disk/by-uuid", uuid))], SNAP)

def make_backup(uuid):
    try:
        path = get_base_path(uuid)
    except KeyError:
        logger.warning("[%s] not mounted", uuid)
        return
    if os.path.exists(path):
        logger.info("[%s] found snapshot dir at '%s'", uuid, path)
    else:
        os.makedirs(path, mode=0o755, exist_ok=True)
        logger.info("[%s] created '%s'", uuid, path)

    last_path = os.path.join(path, LAST)

    date = time.strftime("%Y-%m-%d")
    snapshot_path = os.path.join(path, date)

    i = 1
    while os.path.exists(snapshot_path):
        snapshot_path = os.path.join(path, "%s_%d" % (date, i))
        i += 1

    logger.info("[%s] created '%s'", uuid, snapshot_path)

    for src in PATHS:
        dest = os.path.join(snapshot_path, src.strip("/"))
        os.makedirs(os.path.dirname(dest), mode=0o755, exist_ok=True)
        segment_count = 1 + len([x for x in src.split("/") if x])
        link_dest = os.path.join("../"*segment_count, LAST, src.strip("/"))
        rsync(OPT, src + "/", dest, "--link-dest", link_dest, _out=sys.stdout.buffer)
    rm("-f", last_path, _out=sys.stdout.buffer)
    ln("-s", os.path.relpath(snapshot_path, os.path.dirname(last_path)), last_path, _out=sys.stdout.buffer)


mounts = get_mounts()

for uuid in UUID_LIST:
    make_backup(uuid)
