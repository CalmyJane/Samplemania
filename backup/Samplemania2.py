import os
import pygame
import math
from pygame import draw
from pygame import mixer
from pygame import sprite
from pygame.locals import *
import PiBoyUI
from PiBoyUI import *
import PiBoyInput
from PiBoyInput import PBInput
import time
from pygame.mixer import Sound
import threading
import gc

# -----------------------------
# Audio setup: low-latency mix
# -----------------------------
# IMPORTANT: pre_init must happen before pygame.init()
mixer.pre_init(22050, -16, 2, 64)  # smaller buffer => lower latency (adjust if crackles)
pygame.init()
pygame.mouse.set_visible(False)
mixer.init()


class Sample:
    def __init__(self, path):
        self.path = path
        self.sound = None
        self.channel = None

    def load(self):
        # Load/Decode into memory
        if self.sound is None:
            self.sound = mixer.Sound(self.path)

    def unload(self):
        # Stop and drop references so GC can reclaim memory
        try:
            if self.channel is not None and self.channel.get_busy():
                self.channel.stop()
        except Exception:
            pass
        self.channel = None
        self.sound = None  # dropping this reference is enough; GC will free it

    def play(self):
        if self.sound is not None:
            self.channel = self.sound.play()

    def stop(self):
        if self.channel is not None:
            try:
                self.channel.stop()
            except Exception:
                pass

    def get_name(self):
        return (os.path.splitext(os.path.basename(self.path)))[0]


class Preset:
    # Presets are folders in the sample-directory that contain multiple samples
    def __init__(self, path):
        self.name = os.path.basename(path)
        self.samples = []
        self.page = 0
        self._loader_thread = None
        self._cancel_loading = False
        self._loaded_count = 0

        paths = os.listdir(path)
        paths.sort()
        for filename in paths:
            full = os.path.join(path, filename)
            # Skip non-files
            if not os.path.isfile(full):
                continue
            self.samples.append(Sample(full))
        self.numpages = int(math.ceil(float(len(self.samples)) / 6.0))

    def change_page(self, up):
        if self.numpages == 0:
            return
        if up:
            self.page = (self.page - 1) % self.numpages
        else:
            self.page = (self.page + 1) % self.numpages

    def play_sample(self, index):
        idx = index + self.page * 6
        if 0 <= idx < len(self.samples):
            smp = self.samples[idx]
            if smp.sound is not None:
                smp.play()
            else:
                # Not loaded yet; ignore play to stay responsive
                pass

    def get_names(self):
        names = []
        for i in range(6):
            idx = i + self.page * 6
            if idx < len(self.samples):
                base = self.samples[idx].get_name()
                # Show a tiny hint if not loaded yet
                if self.samples[idx].sound is None:
                    names.append(base + " (…)")
                else:
                    names.append(base)
            else:
                names.append("<EMPTY>")
        return names

    def stop_all(self):
        for s in self.samples:
            s.stop()

    def async_load(self):
        # Start background loading; can be canceled via unload()
        if self._loader_thread is not None and self._loader_thread.is_alive():
            return

        self._cancel_loading = False

        def _loader():
            for s in self.samples:
                if self._cancel_loading:
                    break
                try:
                    s.load()
                    self._loaded_count += 1
                except Exception as e:
                    print(f"[Preset {self.name}] Failed to load {s.path}: {e}")
            # Optionally: gc after finishing to keep heap tidy if we canceled early
            if self._cancel_loading:
                gc.collect()

        self._loader_thread = threading.Thread(target=_loader, daemon=True)
        self._loader_thread.start()

    def unload(self):
        # Signal loader to stop; free sounds for this preset
        self._cancel_loading = True
        self.stop_all()
        for s in self.samples:
            s.unload()
        # Don't hard-join; thread exits naturally soon
        self._loader_thread = None
        self._loaded_count = 0
        gc.collect()


## MAIN APPLICATION ##
class App:
    def __init__(self):
        """Initialize pygame and the application."""
        App.screen = pygame.display.set_mode((640, 480))
        App.bg = Background()
        App.running = True
        self.bgcounter = 0
        self.input = PBInput()
        self.dpad = Dpad((77, 220))
        self.input.set_callback('A', self.on_a)
        self.input.set_callback('B', self.on_b)
        self.input.set_callback('C', self.on_c)
        self.input.set_callback('X', self.on_x)
        self.input.set_callback('Y', self.on_y)
        self.input.set_callback('Z', self.on_z)
        self.input.set_callback('left', self.on_left)
        self.input.set_callback('right', self.on_right)
        self.input.set_callback('up', self.on_up)
        self.input.set_callback('down', self.on_down)
        self.input.set_callback('left_shoulder', self.on_left_shoulder)
        self.input.set_callback('right_shoulder', self.on_right_shoulder)
        self.input.set_callback('red_buttons', self.on_red_buttons)
        self.input.set_callback('select', self.on_select)
        self.input.set_callback('start', self.on_start)

        self.fadetime = 50  # time to fadeout sounds in ms

    def update(self):
        # update is called from PBInput whenever an event happens, e.g. to redraw the screen or check for exit
        # stop if start+select is pressed
        if self.input.start and self.input.select:
            self.input.stop()

        self.dpad.set_values(self.input.up, self.input.down, self.input.left, self.input.right)
        # draw GUI
        App.bg.draw(App.screen)
        self.dpad.draw(App.screen)
        self.presetview.draw(App.screen)
        self.buttonrow.draw(App.screen)
        self.presetlabel.draw(App.screen)
        pygame.display.update()

    def run(self):
        """Print Console Header"""
        print("<------------------------------------->")
        print("")
        print("                               ____________________ ")
        print("                              |  ________________  |")
        print("                              | |   ____   ____  | |")
        print("                              | |  |    | |    | | |")
        print("                              | |  |____| |____| | |")
        print("                              | |  __            | |")
        print("                              | | |  |_________  | |")
        print("                              | | |____________| | |")
        print("                              | |________________| |")
        print("                              |____________________|")
        print("")
        print("<------------------------------------->")
        print("")
        print(" ______  _______  __      __   __  __   __        __  _______  __    _  _______ ")
        print("|      ||   _   ||  |    |  |_|  ||  | |  |      |  ||   _   ||  |  | ||       |")
        print("|    __||  | |  ||  |    |       ||  |_|  |      |  ||  | |  ||   |_| ||    ___|")
        print("|   |   |  |_|  ||  |    |       ||       |      |  ||  |_|  ||       ||   |___ ")
        print("|   |   |       ||  |___ |       ||_     _|   ___|  ||       ||  _    ||    ___|")
        print("|   |__ |   _   ||      || ||_|| |  |   |    |      ||   _   || | |   ||   |___ ")
        print("|______||__| |__||______||_|   |_|  |___|    |______||__| |__||_|  |__||_______|")
        print("")
        print("<------------------------------------->")
        print("Copyright Calmy Jane 2022")
        print("<------------------------------------->")

        # initialize Button Row of 6 buttons
        self.buttonrow = ButtonRow((50, 350))

        # initialize Preset View
        self.presetview = ListView(pos=(220, 220), fontsize=40, spacing=0)

        # load preset list
        base = "/home/pi/RetroPie/files/samples"
        paths = [os.path.join(base, p) for p in sorted(os.listdir(base))]
        self.presets = [p for p in paths if os.path.isdir(p)]
        self.currpresetnum = 0
        self.presetlabel = Text("Preset1", (100, 150), 60, Color('white'), None)

        # set first preset (async load)
        self.set_current_preset(0)
        self.lasttime = time.time()

        self.input.update_callback = self.update
        self.input.listen()  # main loop, listen for input events here

        pygame.quit()

    def load_preset(self, path):
        self.activepreset = Preset(path)
        self.update_presetview()
        print(f"[App] Loading preset '{self.activepreset.name}' asynchronously…")
        self.activepreset.async_load()

    def update_presetview(self):
        self.presetview.set_strings(self.activepreset.get_names())

    def get_current_preset(self):
        return self.presets[self.currpresetnum]

    def set_current_preset(self, index):
        # Unload previous to avoid accumulating memory when browsing quickly
        if hasattr(self, 'activepreset') and self.activepreset is not None:
            print(f"[App] Unloading preset '{self.activepreset.name}'")
            self.activepreset.unload()

        self.currpresetnum = index % len(self.presets)
        self.load_preset(self.presets[self.currpresetnum])
        self.presetlabel.text = self.activepreset.name
        self.presetlabel.render()
        # Refresh the view right away to show names/“(…)” while loading
        self.update()

    # Input Callbacks
    def on_a(self, pressed):
        self.buttonrow.set_button(5, pressed)
        self.presetview.highlight(5, pressed)
        if pressed:
            self.activepreset.play_sample(5)

    def on_b(self, pressed):
        self.buttonrow.set_button(3, pressed)
        self.presetview.highlight(4, pressed)
        if pressed:
            self.activepreset.play_sample(4)

    def on_c(self, pressed):
        self.buttonrow.set_button(1, pressed)
        self.presetview.highlight(3, pressed)
        if pressed:
            self.activepreset.play_sample(3)

    def on_x(self, pressed):
        self.buttonrow.set_button(4, pressed)
        self.presetview.highlight(2, pressed)
        if pressed:
            self.activepreset.play_sample(2)

    def on_y(self, pressed):
        self.buttonrow.set_button(2, pressed)
        self.presetview.highlight(1, pressed)
        if pressed:
            self.activepreset.play_sample(1)

    def on_z(self, pressed):
        self.buttonrow.set_button(0, pressed)
        self.presetview.highlight(0, pressed)
        if pressed:
            self.activepreset.play_sample(0)

    def on_left(self, pressed):
        if pressed:
            self.set_current_preset((self.currpresetnum - 1) % len(self.presets))

    def on_right(self, pressed):
        if pressed:
            self.set_current_preset((self.currpresetnum + 1) % len(self.presets))

    def on_up(self, pressed):
        if pressed:
            self.activepreset.change_page(True)
            self.update_presetview()

    def on_down(self, pressed):
        if pressed:
            self.activepreset.change_page(False)
            self.update_presetview()

    def on_select(self, pressed):
        mixer.fadeout(self.fadetime)

    def on_start(self, pressed):
        pass

    def on_left_shoulder(self, pressed):
        print("left_shoulder")

    def on_right_shoulder(self, pressed):
        print("right shoulder")

    def on_red_buttons(self, pressed):
        # called if any red button (sample) is pressed
        # stop previous samples
        if pressed and not self.input.red_button:
            mixer.fadeout(self.fadetime)


# RUN GAME
if __name__ == "__main__":
    App().run()
