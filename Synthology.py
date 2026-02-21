import pyaudio
import pygame
import math
import itertools
import numpy as np
import time
import PiBoyUI
from PiBoyUI import *
import PiBoyInput
from PiBoyInput import PBInput
from pygame import midi
import sounddevice as sd
import array
from collections import deque
from scipy.signal import butter, lfilter, freqz

class Scale:
    def __init__(self, notes = (0, 2, 4, 5, 7, 9), root="C", octave = 0):
        self.frequencies = {
          "C": 261.6,
          "C#": 277.2,
          "D": 293.7,
          "D#": 311.1,
          "E": 329.6,
          "F": 349.2,
          "F#": 370,
          "G": 392,
          "G#": 415.4,
          "A": 440,
          "A#": 466.2,
          "H": 493.8,
        }
        self.basefreq = 440 #base frequency of A5
        self.pitchbend = 0 #current pitchbend value -1..1
        self.pitchbendrange = 1 #range of the pitchbend in semitones
        self.rootnote = root #the root note from which the self.notes indexes are counted
        self.notesigns = [ "A", "A#", "H", "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#"]
        self.freqfactor = 1.0594630943592952645618252949463 #factor of one semitone (2^(1/12))
        self.notes = notes #the indexes of 6 notes the scale contains
        self.octave = octave #the octave number

    def get_note_freq(self, index):
        return self.get_freq(self.notes[index])

    def get_freq(self, index):
        freq = self.basefreq + self.pitchbend * self.freqfactor * self.pitchbendrange 
        return freq * pow(self.freqfactor, index) * pow(2, self.octave) * pow(self.freqfactor, self.notesigns.index(self.rootnote))
    
    def change_octave(self, up):
        self.octave = self.octave + 1 if up else self.octave - 1

    def increment_rootnote(self, increment):
        if increment:
            self.rootnote = self.notesigns[(self.notesigns.index(self.rootnote) + 1) % len(self.notesigns)]
            if self.rootnote == "A":
                self.octave += 1
        else:
            self.rootnote = self.notesigns[(self.notesigns.index(self.rootnote) - 1) % len(self.notesigns)]
            if self.rootnote == "G#":
                self.octave += 1
      
class PolySynth:
    def __init__(self, amp_scale=1, max_amp=127, sample_rate=22050, num_samples=512):
        self.notes_dict = {}
        self.freq = 70
        self.osc = 0
        self.num_samples = num_samples
        self.sample_rate = sample_rate
        self.amp_scale = amp_scale
        self.max_amp = max_amp
        self.input = PBInput()
        self.crazy = False
        self.oscillators = (self.get_sin_oscillator, self.get_square_oscillator, self.get_saw_oscillator)
        self._init_stream(1)
        self.generating = False
        self.queue = deque()
        self.cutoff = 3000
        
    def _init_stream(self, nchannels):
        #Initialize the Stream object
        self.stream = pyaudio.PyAudio().open(
            rate=self.sample_rate,
            channels=nchannels,
            format=pyaudio.paInt16,
            output=True,
            stream_callback=self.stream_cb,
            frames_per_buffer=self.num_samples
        )
        
    def butter_lowpass(self, cutoff, fs, order=5):
        nyq = 0.5 * fs
        normal_cutoff = cutoff / nyq
        b, a = butter(order, normal_cutoff, btype='low', analog=False)
        return b, a

    def butter_lowpass_filter(self, data, cutoff, fs, order=5):
        b, a = self.butter_lowpass(cutoff, fs, order=order)
        y = lfilter(b, a, data)
        return y

    def _get_samples(self, notes_dict):
        # Return samples in int16 format
        samples = []
        if self.notes_dict:
            for _ in range(self.num_samples):
                samples.append(
                    [next(osc[0]) for _, osc in self.notes_dict.items()]
                )
            samples = np.array(samples).sum(axis=1) / len(self.notes_dict) * self.amp_scale
            samples = np.int16(samples.clip(-self.max_amp, self.max_amp) * 127)
            samples = samples.reshape(self.num_samples, -1)
            #samples = self.butter_lowpass_filter(samples, self.cutoff, self.sample_rate) #filter all oscillators
        else:
            samples = np.zeros(self.num_samples)
        return samples

    def stream_cb(self, in_data, frame_count, time_info, status):
        for i in range(len(self.queue)):
            (name, value, freq) = self.queue.popleft()
            if value:
                self.notes_dict[name] = [self.oscillators[self.osc](freq=freq, amp=100, sample_rate=self.sample_rate), False]
            else:
                if self.notes_dict.get(name):
                    del self.notes_dict[name]  
        if self.notes_dict:
            # Play the notes
            samples = self._get_samples(self.notes_dict)
            return(samples.tobytes(), pyaudio.paContinue)
        else:
            retdata = array.array("i", [0 for i in range(frame_count)])
            return (retdata, pyaudio.paContinue)

    def get_sin_oscillator(self, freq=55, amp=1, sample_rate=22050):
        increment = (2 * math.pi * freq) / sample_rate
        return (math.sin(v) * amp for v in itertools.count(start=0, step=increment))

    def get_square_oscillator(self, freq=55, amp=1, sample_rate=22050):
        increment = (2 * math.pi * freq) / sample_rate
        return (np.sign(math.sin(v)) * amp for v in itertools.count(start=0, step=increment))

    def get_saw_oscillator(self, freq=55, amp=1, sample_rate=22050):
        increment = (2 * math.pi * freq) / sample_rate
        return ((v % (2 * math.pi)) * amp for v in itertools.count(start=0, step=increment))

    def set_oscillator(self, index):
        self.osc = index

    def update(self):
        if self.crazy:
            self.set_note("Crazy", True, self.freq)
            self.freq = self.freq * 1.01 % 1000000
        else:
            self.freq = 70
            if self.notes_dict.get("Crazy"):
                self.set_note("Crazy", False, self.freq)

    def set_note(self, name, value, freq):
        #Add note to queue, will be added to notes_dict in audiostream callback function
        self.queue.append((name,value,freq))

    def switch_oscillator(self, up):
        self.osc = (self.osc + 1) % len(self.oscillators) if up else (self.osc - 1) % len(self.oscillators)

## MAIN APPLICATION ##
class App:
    def __init__(self):
        pygame.init()
        pygame.mouse.set_visible(False)
        App.running = True
        self.input = PBInput()
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
        self.synth = PolySynth()
        self.synth.set_oscillator(0)
        self.print_console_header()
        self.scale = Scale(notes=(0, 2, 3, 5, 7, 8), root="A", octave=-1)
        self.input_id = 3 #input id of midi device
        try:
            pygame.midi.init()
            self.midiinput = pygame.midi.Input(self.input_id)
        except:
            self.midiinput = None
            print("midi device not found")
        self.screen = pygame.display.set_mode((640, 480))
        self.bg = Background()
        #initialize Button Row of 6 buttons
        self.buttonrow = ButtonRow((50, 350))

    def run(self):
        #Main Loop
        while App.running:
            #udpate input (poll buttons)
            self.input.update()
            self.update_midi()
            self.synth.update()
            #stop if start+select is pressed
            if self.input.start and self.input.select:
                App.running = False
            self.buttonrow.draw(self.screen)
            pygame.display.update()
            time.sleep(0.01)

    def update_midi(self):
        if self.midiinput:
            if self.midiinput.poll():
                midi_events = self.midiinput.read(1)
                for event in midi_events:
                    (status, note, vel, _), _ = event
                    note = note -48
                    if status == 144:
                        if vel == 0:
                            #note released
                            print("release: " + str(note))
                            self.synth.set_note(str(note), False, 0)
                        else:
                            print("pressed: " + str(note))
                            self.synth.set_note(str(note), True, self.scale.get_freq(note))

    #Input Callbacks
    def on_any(keyevent):
        pass
    def on_a(self, pressed):
        self.buttonrow.set_button(5, pressed)
        self.synth.set_note("A", pressed, self.scale.get_note_freq(5))
        #print("Input A - pressed:" + str(pressed))
    def on_b(self, pressed):
        self.buttonrow.set_button(3, pressed)
        self.synth.set_note("B", pressed, self.scale.get_note_freq(4))
        #print("Input B - pressed:" + str(pressed))
    def on_c(self, pressed):
        self.buttonrow.set_button(1, pressed)
        self.synth.set_note("C", pressed, self.scale.get_note_freq(3))
        #print("Input C - pressed:" + str(pressed))
    def on_x(self, pressed):
        self.buttonrow.set_button(4, pressed)
        self.synth.set_note("X", pressed, self.scale.get_note_freq(2))
        #print("Input X - pressed:" + str(pressed))
    def on_y(self, pressed):
        self.buttonrow.set_button(2, pressed)
        self.synth.set_note("Y", pressed, self.scale.get_note_freq(1))
        #print("Input Y - pressed:" + str(pressed))
    def on_z(self, pressed):
        self.buttonrow.set_button(0, pressed)
        self.synth.set_note("Z", pressed, self.scale.get_note_freq(0))
        #print("Input Z - pressed:" + str(pressed))
    def on_left(self, pressed):
        self.scale.increment_rootnote(False)
        #print("Input left - pressed:" + str(pressed))
    def on_right(self, pressed):
        self.scale.increment_rootnote(True)
        #print("Input right - pressed:" + str(pressed))
    def on_up(self, pressed):
        if pressed:
            self.scale.change_octave(True)
        #print("Input up - pressed:" + str(pressed))
    def on_down(self, pressed):
        if pressed:
            self.scale.change_octave(False)
        #print("Input down - pressed:" + str(pressed))
    def on_select(self, pressed):
        self.synth.crazy = pressed
        #print("Input select - pressed:" + str(pressed))
    def on_start(self, pressed):
        pass
        #print("Input start - pressed:" + str(pressed))
    def on_left_shoulder(self, pressed):
        self.synth.switch_oscillator(False)
        #print("Input select - pressed:" + str(pressed))
    def on_right_shoulder(self, pressed):
        self.synth.switch_oscillator(True)
        #print("Input start - pressed:" + str(pressed))
    def on_red_buttons(self, pressed):
        #called if any red button (sample) is pressed
        pass

    def print_console_header(self):
        print("<------------------------------------------------------------------------------>")
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
        print("<------------------------------------------------------------------------------>")
        print("")
        print(" ______  _______  __      __   __  __   __        __  _______  __    _  _______ ")
        print("|      ||   _   ||  |    |  |_|  ||  | |  |      |  ||   _   ||  |  | ||       |")
        print("|    __||  | |  ||  |    |       ||  |_|  |      |  ||  | |  ||   |_| ||    ___|")
        print("|   |   |  |_|  ||  |    |       ||       |      |  ||  |_|  ||       ||   |___ ")
        print("|   |   |       ||  |___ |       ||_     _|   ___|  ||       ||  _    ||    ___|")
        print("|   |__ |   _   ||      || ||_|| |  |   |    |      ||   _   || | |   ||   |___ ")
        print("|______||__| |__||______||_|   |_|  |___|    |______||__| |__||_|  |__||_______|")
        print("")
        print("<------------------------------------------------------------------------------>")
        print("                            Copyright Calmy Jane 2022")
        print("<------------------------------------------------------------------------------>")

# RUN GAME
App().run()