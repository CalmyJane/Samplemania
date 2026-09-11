"""Logging and hang detection.

Samplemania is used live, so a problem has to leave a trace instead of a
silent freeze: everything noteworthy goes to a small rotating log file next
to the app, and a watchdog kills the app if the main loop stops coming round
(the launcher in Samplemania.py then restarts it).
"""

import faulthandler
import logging
import logging.handlers
import os
import sys

import config

log = logging.getLogger("samplemania")

_log_file = None


def setup_logging():
    """Log to config.LOG_PATH (rotated, so the SD card never fills up) and
    to the console."""
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    try:
        handler = logging.handlers.RotatingFileHandler(
            config.LOG_PATH, maxBytes=512 * 1024, backupCount=1)
        handler.setFormatter(fmt)
        log.addHandler(handler)
    except (IOError, OSError) as e:
        print("Could not open log file {0}: {1}".format(config.LOG_PATH, e))

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    log.addHandler(console)


def log_system_info():
    """Versions and memory at startup - needed to make sense of any report."""
    import pygame
    from pygame import mixer
    log.info("python %s", sys.version.split()[0])
    log.info("pygame %s, SDL %s, mixer %s", pygame.version.ver,
             ".".join(str(v) for v in pygame.get_sdl_version()), mixer.get_init())
    try:
        with open("/proc/device-tree/model") as f:
            log.info("device %s", f.read().strip("\x00\n"))
    except (IOError, OSError):
        pass
    log.info("memory %s", memory_info())


def memory_info():
    """'rss 80MB, available 600MB' from /proc, or '?' where that isn't there."""
    rss = available = "?"
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    rss = "{0}MB".format(int(line.split()[1]) // 1024)
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    available = "{0}MB".format(int(line.split()[1]) // 1024)
    except (IOError, OSError, ValueError):
        pass
    return "rss {0}, available {1}".format(rss, available)


class Watchdog:
    """Kills the process if the main loop stops calling feed().

    Built on faulthandler, whose timer runs in C without needing the GIL. So
    it still fires when the app is deadlocked inside pygame/SDL, which a
    Python thread could not. Before exiting it writes the stack of every
    thread to the log, which shows exactly where it hung.
    """

    def __init__(self, seconds):
        self.seconds = seconds
        self.file = None
        try:
            self.file = open(config.LOG_PATH, "a")
        except (IOError, OSError):
            pass

    def feed(self, seconds=None):
        """Restart the countdown. Pass seconds for a known long operation."""
        if self.file is None:
            return
        faulthandler.dump_traceback_later(seconds or self.seconds, exit=True,
                                          file=self.file)

    def stop(self):
        if self.file is not None:
            faulthandler.cancel_dump_traceback_later()
