import os
import sys
import threading
import time

# Helper modules live in lib/ so this is the only .py EmulationStation lists.
# No __pycache__ in lib/ either, the folder gets copied to the PiBoy by hand.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import pygame
from pygame import mixer
from pygame.locals import *

import config
import PiBoyUI
from PiBoyUI import *
import PiBoyInput
from PiBoyInput import PBInput
from sampler import Sample, Preset
from modes import PlayMode, RecordMode


## MAIN APPLICATION ##
class App:
    def __init__(self):
        """Initialize pygame and the application."""
        # 1. Sound pre-init first
        pygame.mixer.pre_init(44100, -16, 2, 512)

        # 2. Full pygame init (Initializes Video, Audio, and Font)
        pygame.init()

        # 3. SET DISPLAY MODE BEFORE TOUCHING MOUSE
        # This is the critical step for sudo/python3 compatibility
        App.screen = pygame.display.set_mode((640, 480))

        # 4. Now hide the mouse
        pygame.mouse.set_visible(False)

        # Create 6 dedicated channels
        self.channels = [mixer.Channel(i) for i in range(6)]

        App.bg = Background()
        App.running = True
        self.bgcounter = 0
        self.input = PBInput()
        self.dpad = Dpad((77, 220))

        # Every button is routed to whichever mode is active
        for name in ('A', 'B', 'C', 'X', 'Y', 'Z', 'left', 'right', 'up', 'down',
                     'left_shoulder', 'right_shoulder', 'red_buttons', 'select', 'start'):
            self.input.set_callback(name, self._dispatch(name.lower()))

        self.fadetime = 0
        self.mode = None

    def _dispatch(self, name):
        handler = 'on_' + name
        def callback(pressed):
            getattr(self.mode, handler)(pressed)
        return callback

    ## MODES ##

    def set_mode(self, mode):
        if self.mode is mode:
            return
        if self.mode is not None:
            self.mode.exit()
        self.mode = mode
        self.mode.enter()

    def draw(self):
        self.mode.draw(App.screen)
        pygame.display.flip()

    def run(self):
        """Print Console Header"""
        print("<------------------------------------->")
        print("")
        print("                                ____________________ ")
        print("                               |  ________________  |")
        print("                               | |  ____   ____  | |")
        print("                               | | |    | |    | | |")
        print("                               | | |____| |____| | |")
        print("                               | |  __            | |")
        print("                               | | |_________  | |")
        print("                               | | |____________| | |")
        print("                               | |________________| |")
        print("                               |____________________|")
        print("")
        print("<------------------------------------->")
        print("")
        print(" ______  _______  __      __   __  __   __        __  _______  __     _  _______ ")
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

        config.ensure_dirs()

        # Initialize Button Row of 6 buttons
        self.buttonrow = ButtonRow((50, 350))

        # Initialize Preset View
        self.presetview = ListView(pos=(220, 220), fontsize=40, spacing=0)

        self.presetlabel = Text("Preset1", (100, 150), 60, Color('white'), None)

        self.scan_presets()
        self.currpresetnum = 0
        self.set_current_preset(0)
        self.lasttime = time.time()

        self.playmode = PlayMode(self)
        self.recordmode = RecordMode(self)
        self.set_mode(self.playmode)

        self.main_loop()

        pygame.quit()

    def main_loop(self):
        """Blocks on the controller fd instead of polling, so playback stays as
        responsive as the old event loop. Modes that animate (the recorder's
        level meter) set a frame_timeout and get woken up regularly as well."""
        while App.running:
            self.draw()

            if self.input.wait(self.mode.frame_timeout):
                self.input.update()      # drains events, fires mode callbacks

            if self.input.start and self.input.select:
                App.running = False

            self.mode.tick()

        if self.mode is not None:
            self.mode.exit()

    ## PRESETS ##

    def scan_presets(self):
        """List preset folders. Called again after recording so a new take
        shows up without restarting the app."""
        self.presets = []
        if os.path.isdir(config.SAMPLE_DIR):
            for name in sorted(os.listdir(config.SAMPLE_DIR)):
                if name.startswith('.'):
                    continue
                path = os.path.join(config.SAMPLE_DIR, name)
                if os.path.isdir(path):
                    self.presets.append(path)

        if not self.presets:
            print("No presets found in {0}".format(config.SAMPLE_DIR))
            self.presets = [config.RECORDINGS_DIR]

    def refresh_presets(self):
        """Rescan the library, keeping the current preset selected by name."""
        current = self.presets[self.currpresetnum] if self.presets else None
        self.scan_presets()
        index = self.presets.index(current) if current in self.presets else 0
        self.set_current_preset(index)

    def load_preset(self, path):
        # Create the preset object (this is fast, it just lists files)
        self.activepreset = Preset(path)
        self.update_presetview()

        # Start a background thread to load the actual audio data into RAM
        # This prevents the UI from freezing during SD card read
        load_thread = threading.Thread(target=self.activepreset.load_all)
        load_thread.daemon = True # Thread closes if app closes
        load_thread.start()

    def update_presetview(self):
        self.presetview.set_strings(self.activepreset.get_names())

    def get_current_preset(self):
        return self.presets[self.currpresetnum]

    def set_current_preset(self, index):
        self.currpresetnum = index
        self.load_preset(self.presets[self.currpresetnum])
        self.presetlabel.text = self.activepreset.name
        self.presetlabel.render()


# RUN GAME
if __name__ == "__main__":
    App().run()
