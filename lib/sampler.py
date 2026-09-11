"""Samples, presets and their background loading.

Two rules keep playback stable here:

* One loader thread for the whole app. It always works on the preset that is
  on screen right now, current page first, and drops a preset the moment you
  navigate away - flicking through presets never piles up threads, memory or
  SD card reads.

* Sounds are never freed while the mixer is playing. When a sample ends,
  pygame's audio thread needs the GIL; freeing a Sound needs SDL's audio lock.
  If both happen at the same moment the app deadlocks for good (older pygame
  versions don't release the GIL there). Unused sounds wait in the Graveyard
  until the mixer is idle and are freed from the main loop then.
"""

import math
import os
import threading

from pygame import mixer

from stability import log

SAMPLES_PER_PAGE = 6

_state_lock = threading.Lock()      # guards Sample.sound / Sample.retired


class Graveyard:
    """Holds Sounds that are no longer needed until they can be freed safely."""

    # Free anyway past this much audio (seconds) - only reached when presets
    # are flicked through while something plays for minutes without a gap.
    MAX_SECONDS = 600.0

    def __init__(self):
        self._sounds = []
        self._seconds = 0.0
        self._idle_checks = 0
        self._lock = threading.Lock()

    def add(self, sound):
        with self._lock:
            self._sounds.append(sound)
            try:
                self._seconds += sound.get_length()
            except Exception:
                pass

    def collect(self):
        """Call once per main loop iteration, from the main thread only."""
        if not self._sounds:
            return
        if mixer.get_busy() and self._seconds < self.MAX_SECONDS:
            self._idle_checks = 0
            return
        # Idle on two iterations in a row: the main loop has waited on input
        # in between (GIL released), so any end-of-sample callback that was
        # still running has finished.
        self._idle_checks += 1
        if self._idle_checks < 2 and self._seconds < self.MAX_SECONDS:
            return
        if self._seconds >= self.MAX_SECONDS:
            log.warning("graveyard full (%.0fs of audio), freeing while busy", self._seconds)
        with self._lock:
            sounds, self._sounds = self._sounds, []
            self._seconds = 0.0
        self._idle_checks = 0
        del sounds


graveyard = Graveyard()


class Sample():
    def __init__(self, path):
        self.path = path
        self.sound = None
        self.failed = False
        self.retired = False

    def load(self):
        """Load the file into RAM. Safe to call from any thread, and from two
        at once - the loser's copy goes to the graveyard."""
        if self.sound is not None or self.failed or self.retired:
            return
        try:
            sound = mixer.Sound(self.path)
        except Exception as e:
            log.error("Error loading %s: %s", self.path, e)
            self.failed = True
            return
        with _state_lock:
            if self.retired or self.sound is not None:
                graveyard.add(sound)
            else:
                self.sound = sound

    def play(self, channel):
        sound = self.sound
        if sound is None:
            # Pressed before the loader got here: load now (blocks briefly)
            self.load()
            sound = self.sound
        if sound is not None:
            channel.play(sound)

    def get_name(self):
        return (os.path.splitext(os.path.basename(self.path)))[0]


class Preset:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.samples = []
        self.page = 0

        if os.path.isdir(path):
            try:
                all_files = [f for f in os.listdir(path)
                             if f.lower().endswith(('.wav', '.ogg')) and not f.startswith('.')]
            except OSError as e:
                log.error("Could not list preset %s: %s", path, e)
                all_files = []
            all_files.sort()
            for filename in all_files:
                self.samples.append(Sample(os.path.join(path, filename)))

        self.numpages = max(1, int(math.ceil(float(len(self.samples)) / SAMPLES_PER_PAGE)))

    def next_unloaded(self):
        """The next sample the loader should load - current page first."""
        start = self.page * SAMPLES_PER_PAGE
        order = self.samples[start:start + SAMPLES_PER_PAGE] + self.samples
        for s in order:
            if s.sound is None and not s.failed and not s.retired:
                return s
        return None

    def close(self):
        """Leave the preset: stop loading it and hand its sounds to the graveyard."""
        with _state_lock:
            for s in self.samples:
                s.retired = True
                if s.sound is not None:
                    graveyard.add(s.sound)
                    s.sound = None

    def change_page(self, up):
        if up:
            self.page = (self.page - 1) % self.numpages
        else:
            self.page = (self.page + 1) % self.numpages

    def play_sample(self, index, channel):
        """Play the sample on button `index` of the current page and return
        it, so the app can remember what was played last (pitch mode)."""
        sample_idx = index + self.page * SAMPLES_PER_PAGE
        if sample_idx < len(self.samples):
            sample = self.samples[sample_idx]
            sample.play(channel)
            return sample
        return None

    def get_names(self):
        names = []
        for i in range(SAMPLES_PER_PAGE):
            sample_idx = i + self.page * SAMPLES_PER_PAGE
            if sample_idx < len(self.samples):
                names.append(self.samples[sample_idx].get_name())
            else:
                names.append("<EMPTY>")
        return names


class Loader(threading.Thread):
    """Background loader. load(preset) retargets it; it loads one sample at
    a time and re-checks the target in between."""

    def __init__(self):
        threading.Thread.__init__(self, name="sample-loader")
        self.daemon = True
        self._cond = threading.Condition()
        self._preset = None

    def load(self, preset):
        with self._cond:
            self._preset = preset
            self._cond.notify()

    def stop(self, timeout=2.0):
        """Stop after the sample being loaded right now (for quitting)."""
        with self._cond:
            self._stopping = True
            self._preset = None
            self._cond.notify()
        if self.is_alive():
            self.join(timeout)

    _stopping = False

    def run(self):
        while True:
            with self._cond:
                while self._preset is None and not self._stopping:
                    self._cond.wait()
                if self._stopping:
                    return
                preset = self._preset
            try:
                sample = preset.next_unloaded()
                if sample is None:
                    with self._cond:
                        if self._preset is preset:
                            self._preset = None     # done, sleep until retargeted
                    continue
                sample.load()
            except Exception:
                log.exception("loader error in %s", preset.path)
                with self._cond:
                    if self._preset is preset:
                        self._preset = None
