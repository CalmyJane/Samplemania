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
        self.path=path
        self.sound = mixer.Sound(self.path)

    def play(self):
        #pygame.mixer.Sound.play(self.sound)
        self.sound.play()

    def get_name(self):
        return(os.path.splitext(os.path.basename(self.path)))[0]

class Preset:
    #Presets are folders in the sample-directory that contain multiple samples
    def __init__(self, path):
        self.name = os.path.basename(path)
        self.samples = []
        self.page = 0
        paths = os.listdir(path)
        paths.sort()
        for filename in paths:
            self.samples.append(Sample(os.path.join(path, filename)))
        self.numpages = int(math.ceil(float(len(self.samples)) / 6))

    def change_page(self, up):
        if up:
            self.page = (self.page - 1) % self.numpages
        else:
            self.page = (self.page + 1) % self.numpages

    def play_sample(self, index):
        if index + self.page * 6 < len(self.samples):
            self.samples[index + self.page * 6].play()

    def get_names(self):
        names = []
        for i in range(6):
            if i + self.page * 6 < len(self.samples):
                names.append(self.samples[i + self.page * 6].get_name())
            else:
                names.append("<EMPTY>")
        return names


## MAIN APPLICATION ##
class App:
    def __init__(self):
        """Initialize pygame and the application."""
        pygame.init()
        pygame.mouse.set_visible(False)
        mixer.pre_init(22050,-16, 2, 128)
        mixer.init()
        App.screen = pygame.display.set_mode((640, 480))
        App.bg = Background()
        App.running = True
        self.bgcounter = 0
        self.input = PBInput()
        self.dpad = Dpad((77,220))
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

        self.fadetime = 50 #time to fadeout sounds in ms

    def update(self):
        #update is called from PBInput whenever an event happens, e.g. to redraw the screen or check for exit
        #stop if start+select is pressed
        if self.input.start and self.input.select:
            self.input.stop()

        self.dpad.set_values(self.input.up, self.input.down, self.input.left, self.input.right)
        #draw GUI
        App.bg.draw(App.screen)
        self.dpad.draw(App.screen)
        self.presetview.draw(App.screen)
        self.buttonrow.draw(App.screen)
        self.presetlabel.draw(App.screen)
        pygame.display.update()
        #currtime = time.time()
        #print(currtime-self.lasttime)
        #self.lasttime = currtime

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

        #initialize Button Row of 6 buttons
        self.buttonrow = ButtonRow((50, 350))

        #initialize Preset View
        self.presetview = ListView(pos=(220, 220), fontsize=40, spacing=0)

        #load preset and fill presetview
        paths = os.listdir("/home/pi/RetroPie/files/samples")
        paths.sort()
        self.presets = paths
        for i, prst in enumerate(self.presets):
            prst = os.path.join("/home/pi/RetroPie/files/samples", prst)
            self.presets[i]=prst
        self.currpresetnum = 0
        self.presetlabel = Text("Preset1", (100, 150), 60, Color('white'), None)
        self.set_current_preset(0)
        self.lasttime = time.time()

        self.input.update_callback = self.update
        self.input.listen() #main loop, listen for input events here

        #while App.running:
        #    #udpate input (poll buttons)
        #    self.input.update()
        #    #stop if start+select is pressed
        #    if self.input.start and self.input.select:
        #        App.running = False

        #    self.dpad.set_values(self.input.up, self.input.down, self.input.left, self.input.right)
        #    #draw GUI
        #    #App.bg.draw(App.screen)
        #    #self.dpad.draw(App.screen)
        #    #self.presetview.draw(App.screen)
        #    #self.buttonrow.draw(App.screen)
        #    #self.presetlabel.draw(App.screen)
        #    #pygame.display.update()
        #    currtime = time.time()
        #    print(currtime-self.lasttime)
        #    self.lasttime = currtime

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

    #Input Callbacks
    def on_a(self, pressed):
        self.buttonrow.set_button(5, pressed)
        self.presetview.highlight(5, pressed)
        if pressed:
            self.activepreset.play_sample(5)
        #print("Input A - pressed:" + str(pressed))
    def on_b(self, pressed):
        self.buttonrow.set_button(3, pressed)
        self.presetview.highlight(4, pressed)
        if pressed:
            self.activepreset.play_sample(4)
        #print("Input B - pressed:" + str(pressed))
    def on_c(self, pressed):
        self.buttonrow.set_button(1, pressed)
        self.presetview.highlight(3, pressed)
        if pressed:
            self.activepreset.play_sample(3)
        #print("Input C - pressed:" + str(pressed))
    def on_x(self, pressed):
        self.buttonrow.set_button(4, pressed)
        self.presetview.highlight(2, pressed)
        if pressed:
            self.activepreset.play_sample(2)
        #print("Input X - pressed:" + str(pressed))
    def on_y(self, pressed):
        self.buttonrow.set_button(2, pressed)
        self.presetview.highlight(1, pressed)
        if pressed:
            self.activepreset.play_sample(1)
        #print("Input Y - pressed:" + str(pressed))
    def on_z(self, pressed):
        self.buttonrow.set_button(0, pressed)
        self.presetview.highlight(0, pressed)
        if pressed:
            self.activepreset.play_sample(0)
        #print("Input Z - pressed:" + str(pressed))
    def on_left(self, pressed):
        if pressed:
            self.set_current_preset((self.currpresetnum - 1) % len(self.presets))
        #print("Input left - pressed:" + str(pressed))
    def on_right(self, pressed):
        if pressed:
            self.set_current_preset((self.currpresetnum + 1) % len(self.presets))
        #print("Input right - pressed:" + str(pressed))
    def on_up(self, pressed):
        if pressed:
            self.activepreset.change_page(True)
            self.update_presetview()
        #print("Input up - pressed:" + str(pressed))
    def on_down(self, pressed):
        if pressed:
            self.activepreset.change_page(False)
            self.update_presetview()
        #print("Input down - pressed:" + str(pressed))
    def on_select(self, pressed):
        mixer.fadeout(self.fadetime)
        #print("Input select - pressed:" + str(pressed))
    def on_start(self, pressed):
        pass
        #print("Input start - pressed:" + str(pressed))
    def on_left_shoulder(self, pressed):
        print("left_shoulder")
        #print("Input select - pressed:" + str(pressed))
    def on_right_shoulder(self, pressed):
        print("right shoulder")
        #print("Input start - pressed:" + str(pressed))
    def on_red_buttons(self, pressed):
        #called if any red button (sample) is pressed
        #stop previous samples
        if pressed and not self.input.red_button:
            mixer.fadeout(self.fadetime)

# RUN GAME
App().run()







