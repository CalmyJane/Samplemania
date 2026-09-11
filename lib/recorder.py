"""USB microphone capture.

Uses sounddevice (PortAudio) rather than shelling out to arecord, because the
audio callback hands us the raw blocks - that's what makes a live level meter
possible while recording.
"""

import time

import numpy as np

import config

# sounddevice is imported on first use, not at startup: importing it
# initialises PortAudio, which the playback side of the app has no business
# depending on. See _load_sounddevice().
sd = None
SD_ERROR = None
_sd_tried = False

INT16_MAX = 32768.0
CLIP_LEVEL = 32700

# Onboard / virtual devices we never want to pick automatically
_EXCLUDE = ('bcm2835', 'vc4', 'hdmi', 'dummy', 'monitor', 'loopback', 'null')


def _load_sounddevice():
    global sd, SD_ERROR, _sd_tried
    if not _sd_tried:
        _sd_tried = True
        try:
            import sounddevice
            sd = sounddevice
        except Exception as e:  # ImportError, or PortAudio missing
            SD_ERROR = str(e)
    return sd


def available():
    return _load_sounddevice() is not None


def find_input_device(preferred=None):
    """Resolve a device to (index, name). preferred may be an index, a name
    substring, or None for autodetect. Returns (None, reason) on failure."""
    if _load_sounddevice() is None:
        return None, "sounddevice not installed"

    try:
        devices = sd.query_devices()
    except Exception as e:
        return None, "no audio devices: {0}".format(e)

    inputs = [(i, d) for i, d in enumerate(devices) if d['max_input_channels'] >= 1]
    if not inputs:
        return None, "no input devices found"

    if isinstance(preferred, int):
        for i, d in inputs:
            if i == preferred:
                return i, d['name']
        return None, "device index {0} has no input".format(preferred)

    if isinstance(preferred, str):
        needle = preferred.lower()
        for i, d in inputs:
            if needle in d['name'].lower():
                return i, d['name']
        return None, "no input device matching '{0}'".format(preferred)

    # Autodetect: first input that isn't the onboard soundcard
    for i, d in inputs:
        name = d['name'].lower()
        if not any(x in name for x in _EXCLUDE):
            return i, d['name']

    # Nothing but onboard - take it anyway rather than failing
    return inputs[0][0], inputs[0][1]['name']


class Recorder:
    """Records to RAM, hands back an int16 numpy array on stop.

    5 minutes of 44.1k mono is ~26MB, well within the Pi's budget, so there is
    no need to stream to disk while recording.
    """

    def __init__(self, samplerate=None, channels=None, device=None,
                 max_seconds=None, blocksize=1024):
        self.samplerate = samplerate or config.SAMPLERATE
        self.channels = channels or config.CHANNELS
        self.blocksize = blocksize
        self.max_frames = int(self.samplerate * (max_seconds or config.MAX_RECORD_SECONDS))

        self.device_index, self.device_name = find_input_device(
            device if device is not None else config.INPUT_DEVICE)
        self.error = None if self.device_index is not None else self.device_name

        self.recording = False
        self.peak = 0.0        # 0..1, last block
        self.rms = 0.0         # 0..1, last block
        self.clipped = False
        self.overruns = 0

        self._stream = None
        self._blocks = []
        self._frames = 0
        self._started_at = 0.0

    ## STATE ##

    @property
    def duration(self):
        if self._frames == 0:
            return 0.0
        return self._frames / float(self.samplerate)

    @property
    def full(self):
        return self._frames >= self.max_frames

    ## CAPTURE ##

    def _callback(self, indata, frames, time_info, status):
        if status:
            self.overruns += 1
        if self._frames >= self.max_frames:
            raise sd.CallbackStop()

        block = indata.copy()
        self._blocks.append(block)
        self._frames += frames

        as_int = np.abs(block.astype(np.int32))
        if as_int.size:
            peak = int(as_int.max())
            self.peak = peak / INT16_MAX
            self.rms = float(np.sqrt(np.mean(np.square(block.astype(np.float32))))) / INT16_MAX
            if peak >= CLIP_LEVEL:
                self.clipped = True

    def start(self):
        """Begin recording. Returns True on success, False (with .error set)
        if the device could not be opened."""
        if self.recording:
            return True
        if sd is None:
            self.error = "sounddevice not installed"
            return False
        if self.device_index is None:
            return False

        self._blocks = []
        self._frames = 0
        self.peak = 0.0
        self.rms = 0.0
        self.clipped = False
        self.overruns = 0

        try:
            self._stream = sd.InputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                dtype='int16',
                blocksize=self.blocksize,
                device=self.device_index,
                callback=self._callback)
            self._stream.start()
        except Exception as e:
            self.error = str(e)
            self._stream = None
            return False

        self.error = None
        self.recording = True
        self._started_at = time.time()
        return True

    def stop(self):
        """Stop and return the captured int16 array (flat for mono), or None
        if nothing was captured."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                print("Error closing input stream: {0}".format(e))
            self._stream = None

        self.recording = False
        self.peak = 0.0
        self.rms = 0.0

        if not self._blocks:
            return None

        data = np.concatenate(self._blocks, axis=0)
        self._blocks = []
        if self.channels == 1:
            data = data.reshape(-1)
        return data

    def abort(self):
        """Stop and throw the take away."""
        self.stop()
        self._frames = 0
