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

# START: released before this it opens the menu, held longer it switches to
# the play screen until it is released again.
MENU_HOLD_SECONDS = 0.35

# Look of the screen.
# The background lines drift and shimmer. The frames are pre-rendered once at
# startup (640x480 each, so UI_ANIM_FRAMES x ~1.2MB of RAM) and the play
# screen then redraws at UI_ANIM_FPS. Set UI_ANIM_FPS to 0 for a still
# background: no extra memory, and the screen is only drawn after a button
# press again. Turn it off first if playback ever sounds less than solid.
UI_ANIM_FPS = 10
UI_ANIM_FRAMES = 10

# How the six samples are shown: "boxes" (laid out like the buttons) or
# "list" (six wide rows). The menu switches between them while running.
UI_STYLE = "list"

# Seconds the title screen stays up at startup before the play screen. Any
# button skips it; 0 turns it off. It can also be opened from the menu.
SPLASH_SECONDS = 3.0

# Draw the old button and d-pad pictures in the corner. Only useful to see
# whether a button on the device arrives at all.
SHOW_DEBUG_PADS = False

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
