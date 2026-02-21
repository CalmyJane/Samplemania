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

class Sample():
    def __init__(self, path):
        self.path = path
        self.sound = None
        self.failed = False

    def play(self, channel):
        # Lazy loading
        if self.sound is None and not self.failed:
            try:
                self.sound = mixer.Sound(self.path)
            except Exception as e:
                print("Error loading {0}: {1}".format(self.path, e))
                self.failed = True
                return
        
        if self.sound:
            # Playing on a specific channel will automatically stop 
            # whatever was playing on that channel previously.
            channel.play(self.sound)

    def get_name(self):
        return (os.path.splitext(os.path.basename(self.path)))[0]

class Preset:
    # Presets are folders in the sample-directory that contain multiple samples
    def __init__(self, path):
        self.name = os.path.basename(path)
        self.samples = []
        self.page = 0
        
        if os.path.isdir(path):
            # Filter for audio files and sort them
            all_files = os.listdir(path)
            paths = []
            for f in all_files:
                if f.lower().endswith(('.wav', '.ogg')):
                    paths.append(f)
            paths.sort()
            
            for filename in paths:
                self.samples.append(Sample(os.path.join(path, filename)))
        
        # Calculate pages
        if len(self.samples) > 0:
            self.numpages = int(math.ceil(float(len(self.samples)) / 6))
        else:
            self.numpages = 1

    def change_page(self, up):
        if up:
            self.page = (self.page - 1) % self.numpages
        else:
            self.page = (self.page + 1) % self.numpages

    def play_sample(self, index, channel):
            sample_idx = index + self.page * 6
            if sample_idx < len(self.samples):
                # Pass the channel assigned to this button index
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


## MAIN APPLICATION ##
class App:
    def __init__(self):
        """Initialize pygame and the application."""
        pygame.init()
        pygame.mouse.set_visible(False)
        # Using a slightly larger buffer (512) helps prevent stuttering during lazy loading
        mixer.pre_init(22050, -16, 2, 512)
        mixer.init()
        
        # Create 6 dedicated channels for the 6 button slots
        self.channels = [mixer.Channel(i) for i in range(6)]
        
        App.screen = pygame.display.set_mode((640, 480))
        App.bg = Background()
        App.running = True
        self.bgcounter = 0
        self.input = PBInput()
        self.dpad = Dpad((77, 220))
        
        # Set callbacks for hardware inputs
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

        self.fadetime = 50 # time to fadeout sounds in ms

    def update(self):
        # Update is called from PBInput whenever an event happens
        # Stop if start + select is pressed
        if self.input.start and self.input.select:
            self.input.stop()

        self.dpad.set_values(self.input.up, self.input.down, self.input.left, self.input.right)
        
        # Draw GUI
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

        # Initialize Button Row of 6 buttons
        self.buttonrow = ButtonRow((50, 350))

        # Initialize Preset View
        self.presetview = ListView(pos=(220, 220), fontsize=40, spacing=0)

        # Load presets from directory
        paths = os.listdir("/home/pi/RetroPie/files/samples")
        paths.sort()
        self.presets = []
        for prst in paths:
            self.presets.append(os.path.join("/home/pi/RetroPie/files/samples", prst))
        
        self.currpresetnum = 0
        self.presetlabel = Text("Preset1", (100, 150), 60, Color('white'), None)
        self.set_current_preset(0)
        self.lasttime = time.time()

        self.input.update_callback = self.update
        self.input.listen() # Main loop starts here

        pygame.quit()

    def load_preset(self, path):
        self.activepreset = Preset(path)
        self.update_presetview()

    def update_presetview(self):
        self.presetview.set_strings(self.activepreset.get_names())

    def get_current_preset(self):
        return self.presets[self.currpresetnum]

    def set_current_preset(self, index):
        self.currpresetnum = index
        self.load_preset(self.presets[self.currpresetnum])
        self.presetlabel.text = self.activepreset.name
        self.presetlabel.render()

    # Input Callbacks mapped to specific channels
    def on_a(self, pressed):
        self.buttonrow.set_button(5, pressed)
        self.presetview.highlight(5, pressed)
        if pressed:
            self.activepreset.play_sample(5, self.channels[5])

    def on_b(self, pressed):
        self.buttonrow.set_button(3, pressed)
        self.presetview.highlight(4, pressed)
        if pressed:
            self.activepreset.play_sample(4, self.channels[4])

    def on_c(self, pressed):
        self.buttonrow.set_button(1, pressed)
        self.presetview.highlight(3, pressed)
        if pressed:
            self.activepreset.play_sample(3, self.channels[3])

    def on_x(self, pressed):
        self.buttonrow.set_button(4, pressed)
        self.presetview.highlight(2, pressed)
        if pressed:
            self.activepreset.play_sample(2, self.channels[2])

    def on_y(self, pressed):
        self.buttonrow.set_button(2, pressed)
        self.presetview.highlight(1, pressed)
        if pressed:
            self.activepreset.play_sample(1, self.channels[1])

    def on_z(self, pressed):
        self.buttonrow.set_button(0, pressed)
        self.presetview.highlight(0, pressed)
        if pressed:
            self.activepreset.play_sample(0, self.channels[0])

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
        if pressed:
            mixer.fadeout(self.fadetime)

    def on_start(self, pressed):
        pass

    def on_left_shoulder(self, pressed):
        print("left_shoulder")

    def on_right_shoulder(self, pressed):
        print("right shoulder")

    def on_red_buttons(self, pressed):
        # Stop previous samples only if a new button is pressed
        if pressed and not self.input.red_button:
            # Note: This fades out ALL channels. If you want a specific behavior, 
            # you could loop through self.channels and call stop() instead.
            mixer.fadeout(self.fadetime)

# RUN GAME
App().run()







