import os

# Root of the app (this file lives in lib/), graphics are loaded from graphics/
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAPHICS_DIR = os.path.join(APP_DIR, "graphics")

# Log file - errors, slow frames, hangs and restarts end up here
LOG_PATH = os.path.join(APP_DIR, "samplemania.log")

# Seconds the main loop may stall before the app is killed and restarted.
# The loop normally comes round at least every IDLE_WAIT seconds.
WATCHDOG_SECONDS = 8.0
IDLE_WAIT = 0.5

# Runtime files. /dev/shm is RAM: no SD card writes, gone after a reboot.
RUN_DIR = "/dev/shm" if os.path.isdir("/dev/shm") else APP_DIR
# Current preset and page, so an app restarted by the launcher comes back there
STATE_PATH = os.path.join(RUN_DIR, "samplemania.state")
# Created when the user quits on purpose - the launcher then never restarts
QUIT_MARKER = os.path.join(RUN_DIR, "samplemania.quit")

# Sample library. Every subfolder in here shows up as a preset.
SAMPLE_DIR = "/home/pi/RetroPie/files/samples"

# Recordings land here as a normal preset. Untouched originals go to .raw,
# so every edit can be redone from the source.
RECORDINGS_NAME = "Recordings"
RECORDINGS_DIR = os.path.join(SAMPLE_DIR, RECORDINGS_NAME)
RAW_DIR = os.path.join(RECORDINGS_DIR, ".raw")

# Recording format - matches the existing library (16bit mono wav)
SAMPLERATE = 44100
CHANNELS = 1
MAX_RECORD_SECONDS = 300

# Loudness. USB mics usually come in far too quiet for a sampler, so takes are
# peak normalised on save. The untouched original stays in .raw either way.
# RECORD_GAIN is applied before normalising - only needed if the mic is so
# quiet that the trim detector misses the take entirely.
RECORD_GAIN = 1.0            # linear, 1.0 = off, 4.0 = +12dB
NORMALIZE = True
TARGET_PEAK_DBFS = -3.0      # leaves headroom so stacked samples don't clip
MAX_GAIN_DB = 30.0           # cap, so a near silent take isn't turned into hiss

# Input device for recording.
# None  = autodetect (first usb input that isn't the onboard soundcard)
# int   = sounddevice device index
# str   = substring of the device name, e.g. "Q2U"
INPUT_DEVICE = None


def asset(name):
    """Absolute path to a png/asset in the graphics folder."""
    return os.path.join(GRAPHICS_DIR, name)


def ensure_dirs():
    for d in (RECORDINGS_DIR, RAW_DIR):
        if not os.path.isdir(d):
            os.makedirs(d)
