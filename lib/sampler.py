import math
import os

from pygame import mixer


class Sample():
    def __init__(self, path):
        self.path = path
        self.sound = None
        self.failed = False

    def load(self):
        """Synchronous load for a single file."""
        if self.sound is None and not self.failed:
            try:
                self.sound = mixer.Sound(self.path)
            except Exception as e:
                print("Error loading {0}: {1}".format(self.path, e))
                self.failed = True

    def play(self, channel):
        if self.sound:
            channel.play(self.sound)
        else:
            # Fallback for thread-safety: load if not ready
            self.load()
            if self.sound:
                channel.play(self.sound)

    def get_name(self):
        return (os.path.splitext(os.path.basename(self.path)))[0]


class Preset:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.samples = []
        self.page = 0

        if os.path.isdir(path):
            all_files = [f for f in os.listdir(path)
                         if f.lower().endswith(('.wav', '.ogg')) and not f.startswith('.')]
            all_files.sort()
            for filename in all_files:
                self.samples.append(Sample(os.path.join(path, filename)))

        self.numpages = max(1, int(math.ceil(float(len(self.samples)) / 6)))

    def load_all(self):
        """Triggers the load for every sample in this preset."""
        for s in self.samples:
            s.load()

    def change_page(self, up):
        if up:
            self.page = (self.page - 1) % self.numpages
        else:
            self.page = (self.page + 1) % self.numpages

    def play_sample(self, index, channel):
        sample_idx = index + self.page * 6
        if sample_idx < len(self.samples):
            self.samples[sample_idx].play(channel)

    def get_names(self):
        names = []
        for i in range(6):
            sample_idx = i + self.page * 6
            if sample_idx < len(self.samples):
                names.append(self.samples[sample_idx].get_name())
            else:
                names.append("<EMPTY>")
        return names
