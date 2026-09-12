"""Pitching one sample into a scale.

pygame can't change the pitch of a playing sound, so every note is a resampled
copy of the sample: playing it back faster raises the pitch, slower lowers it
(like a sampler without time stretching - long notes get shorter).

Resampling a few seconds of audio takes long enough to starve the mixer if it
happens in one go, so it runs in a worker thread in small chunks that yield in
between. The notes of the current scale are prepared as soon as the scale or
the root changes, so a button press finds them ready.
"""

import threading
import time

import numpy as np
from pygame import sndarray

from sampler import graveyard
from stability import log

# (name, semitones of each scale degree). The first entry is the default.
SCALES = [
    ("CHROMATIC", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]),
    ("MAJOR", [0, 2, 4, 5, 7, 9, 11]),
    ("MINOR", [0, 2, 3, 5, 7, 8, 10]),
    ("DORIAN", [0, 2, 3, 5, 7, 9, 10]),
    ("MIXOLYDIAN", [0, 2, 4, 5, 7, 9, 10]),
    ("PENTA MAJOR", [0, 2, 4, 7, 9]),
    ("PENTA MINOR", [0, 3, 5, 7, 10]),
    ("BLUES", [0, 3, 5, 6, 7, 10]),
    ("WHOLE TONE", [0, 2, 4, 6, 8, 10]),
    ("OCTAVE", [0]),            # one degree, so every step is a full octave
]

# A pitched note is a full copy of the sample in RAM (44.1kHz stereo 16bit is
# about 176KB per second), so the cache is bounded by the amount of audio it
# holds rather than by a length limit on the sample. The note just built is
# always kept, even when it is bigger than the whole budget by itself.
MAX_CACHE_SECONDS = 240.0

# A note can only get so long: pitched an octave down a sample is twice as
# long, and the OCTAVE scale reaches five octaves. Past this the copy is cut
# off, so one deep note can't eat all the memory.
MAX_NOTE_SECONDS = 120.0

# Frames per work chunk. Small enough that one chunk holds the GIL for a
# few milliseconds only, so the audio thread keeps its buffers filled.
CHUNK = 40000

# Pitched copies kept per sample (six buttons plus room to move the root)
MAX_CACHED = 24

# Longer samples are not prepared ahead: six copies of a long take would only
# push each other out of the cache again. Their notes are built when pressed.
PREPARE_MAX_SECONDS = 30.0


def step_semitones(intervals, step):
    """Semitone offset of a scale step, counting on past the octave.

    step 0 is the root, 1 the next degree up, -1 the one below.
    """
    octave, index = divmod(step, len(intervals))
    return intervals[index] + 12 * octave


class _Job:
    """Resamples one pitch, a chunk at a time."""

    def __init__(self, semitones, data):
        self.semitones = semitones
        self.data = data
        self.ratio = 2.0 ** (semitones / 12.0)
        frames = max(1, int(len(data) / self.ratio))
        frames = min(frames, int(MAX_NOTE_SECONDS * 44100))
        shape = (frames, data.shape[1]) if data.ndim > 1 else (frames,)
        self.out = np.empty(shape, dtype=np.int16)
        self.pos = 0

    def step(self):
        """Do the next chunk. Returns True when the pitch is finished."""
        end = min(self.pos + CHUNK, len(self.out))
        idx = np.arange(self.pos, end, dtype=np.float32) * self.ratio
        low = idx.astype(np.int32)
        high = np.minimum(low + 1, len(self.data) - 1)
        frac = idx - low
        if self.data.ndim > 1:
            frac = frac[:, None]
        a = self.data[low].astype(np.float32)
        b = self.data[high].astype(np.float32)
        self.out[self.pos:end] = (a + (b - a) * frac).astype(np.int16)
        self.pos = end
        return self.pos >= len(self.out)

    def run(self):
        while not self.step():
            pass
        return sndarray.make_sound(np.ascontiguousarray(self.out))


class PitchEngine:
    """Holds one source sample and its pitched copies."""

    def __init__(self):
        self.source = None          # the original Sound
        self.name = ""
        self.source_seconds = 0.0
        self._data = None           # numpy copy of the source
        self._cache = {}            # semitones -> Sound, oldest use first
        self._cached_seconds = 0.0
        self._lock = threading.Lock()
        self._wanted = []           # semitones still to prepare, in order
        self._cond = threading.Condition()
        self._worker = None
        self._stopping = False

    ## SOURCE ##

    def set_source(self, sound, name=""):
        """Point the engine at a new sample. Pitched copies of the old one are
        handed to the graveyard (never freed while the mixer plays)."""
        if sound is self.source:
            return
        with self._cond:
            self._wanted = []
        with self._lock:
            for pitched in self._cache.values():
                graveyard.add(pitched)
            self._cache = {}
            self._cached_seconds = 0.0
            self.source = sound
            self.name = name
            self._data = None
            self.source_seconds = 0.0
            if sound is not None:
                try:
                    data = sndarray.array(sound)
                except Exception as e:
                    log.error("cannot read sample for pitching: %s", e)
                    self.source = None
                    return
                self._data = data
                self.source_seconds = sound.get_length()

    @property
    def ready(self):
        return self._data is not None

    ## NOTES ##

    def want(self, semitones):
        """Ask the worker to prepare these pitches (in this order)."""
        if not self.ready:
            return
        if self.source_seconds > PREPARE_MAX_SECONDS:
            # Nothing to gain: they would evict each other while being built
            log.info("%s is %.0fs long - pitching it note by note when pressed",
                     self.name, self.source_seconds)
            return
        with self._lock:
            todo = [s for s in semitones if s not in self._cache and s != 0]
        if not todo:
            return
        with self._cond:
            self._wanted = todo
            self._cond.notify()
        if self._worker is None:
            self._worker = threading.Thread(target=self._work, name="pitch-worker")
            self._worker.daemon = True
            self._worker.start()

    def get(self, semitones):
        """The Sound for this pitch, building it here if it isn't ready yet."""
        if not self.ready:
            return None
        if semitones == 0:
            return self.source
        with self._lock:
            sound = self._cache.get(semitones)
            data = self._data
            if sound is not None:
                # keep it fresh: the oldest note is the first one dropped
                del self._cache[semitones]
                self._cache[semitones] = sound
        if sound is not None:
            return sound

        started = time.time()
        sound = _Job(semitones, data).run()
        took = time.time() - started
        if took > 0.05:
            log.warning("pitch %+d built in %.0fms on the main thread", semitones, took * 1000)
        self._store(semitones, sound)
        return sound

    def play(self, semitones, channel):
        sound = self.get(semitones)
        if sound is not None:
            channel.play(sound)

    def _store(self, semitones, sound):
        with self._lock:
            if semitones in self._cache:        # built twice, keep the first
                graveyard.add(sound)
                return
            self._cache[semitones] = sound
            self._cached_seconds += sound.get_length()
            # Drop the notes used longest ago until the budget fits again. The
            # one just built always stays, however long the sample is.
            while len(self._cache) > 1 and (self._cached_seconds > MAX_CACHE_SECONDS
                                            or len(self._cache) > MAX_CACHED):
                oldest = next(iter(self._cache))
                dropped = self._cache.pop(oldest)
                self._cached_seconds -= dropped.get_length()
                graveyard.add(dropped)

    ## WORKER ##

    def _work(self):
        while True:
            with self._cond:
                while not self._wanted and not self._stopping:
                    self._cond.wait()
                if self._stopping:
                    return
                semitones = self._wanted[0]
                data = self._data
            try:
                with self._lock:
                    done = semitones in self._cache
                if not done and data is not None:
                    job = _Job(semitones, data)
                    while not job.step():
                        # let the audio thread and the main loop have the GIL
                        time.sleep(0.001)
                        with self._cond:
                            if self._stopping or semitones not in self._wanted:
                                job = None
                                break
                    if job is not None:
                        self._store(semitones, sndarray.make_sound(
                            np.ascontiguousarray(job.out)))
            except Exception:
                log.exception("could not build pitch %+d", semitones)
            with self._cond:
                if semitones in self._wanted:
                    self._wanted.remove(semitones)

    def stop(self, timeout=2.0):
        with self._cond:
            self._stopping = True
            self._wanted = []
            self._cond.notify()
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout)
