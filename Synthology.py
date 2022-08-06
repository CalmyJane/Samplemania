import pyaudio
import pygame
import math
import itertools
import numpy as np
import time
from PiBoyInput import PBInput
from pygame import midi
import sounddevice as sd

def get_sin_oscillator(freq=55, amp=1, sample_rate=44100):
    increment = (2 * math.pi * freq)/ sample_rate
    return (math.sin(v) * amp for v in itertools.count(start=0, step=increment))
      
class PolySynth:
    def __init__(self, amp_scale=0.1, max_amp=0.1, sample_rate=22050, num_samples=256):
        # Initialize MIDI
        midi.init()
        if midi.get_count() > 0:
            self.midi_input = midi.Input(midi.get_default_input_id())
        else: 
            raise Exception("no midi devices detected")
        
        # Constants
        self.num_samples = num_samples
        self.sample_rate = sample_rate
        self.amp_scale = amp_scale
        self.max_amp = max_amp
        self.input = PBInput()
        self.input.set_callback("A", self.on_a)
        self.input.set_callback("B", self.on_b)
        self.input.set_callback("C", self.on_c)
        self.input.set_callback("X", self.on_x)
        self.input.set_callback("Y", self.on_y)
        self.input.set_callback("Z", self.on_z)
        self.input.set_callback("select", self.on_select)
        self.input.set_callback("start", self.on_start)
        self.input.set_callback("red_buttons", self.on_red_buttons)
        self.crazy = False
        
    def _init_stream(self, nchannels):
        #Initialize the Stream object
        self.stream = pyaudio.PyAudio().open(
            rate=self.sample_rate,
            channels=nchannels,
            format=pyaudio.paInt8,
            output=True,
            frames_per_buffer=self.num_samples
        )
        
    def _get_samples(self, notes_dict):
        # Return samples in int16 format
        samples = []
        for _ in range(self.num_samples):
            samples.append(
                [next(osc[0]) for _, osc in notes_dict.items()]
            )
        samples = np.array(samples).sum(axis=1) * self.amp_scale
        samples = np.int16(samples.clip(-self.max_amp, self.max_amp) * 127)
        return samples.reshape(self.num_samples, -1)

    def play(self, osc_function=get_sin_oscillator, close=False):
        # Check for release trigger, number of channels and init Stream
        self.osc = osc_function
        tempcf = osc_function(1, 1, self.sample_rate)
        has_trigger = hasattr(tempcf, "trigger_release")
        tempsm = self._get_samples({-1: [tempcf, False]})
        nchannels = tempsm.shape[1]
        self._init_stream(nchannels)
        print(nchannels)
        self.print_console_header()
        try:
            self.notes_dict = {}
            self.freq = 70
            while True:
                if self.input.start and self.input.select:
                    break
                self.input.update()
                if self.notes_dict:
                    # Play the notes
                    samples = self._get_samples(self.notes_dict)
                    self.stream.write(samples.tobytes())
                if self.crazy:  
                    self.notes_dict["Crazy"] = [self.osc(freq=self.freq, amp=100, sample_rate=self.sample_rate),False]
                    self.freq = self.freq * 1.01 % 1000000
                else:
                    self.freq = 70
                    if self.notes_dict.get("Crazy"):
                        del self.notes_dict["Crazy"]
                

                #if self.midi_input.poll():
                #    # Add or remove notes from notes_dict
                #    for event in self.midi_input.read(num_events=16):
                #        (status, note, vel, _), _ = event
                        
                #        # Note OFF
                #        if status == 0x80 and note in notes_dict:
                #            if has_trigger:
                #                notes_dict[note][0].trigger_release()
                #                notes_dict[note][1] = True
                #            else:
                #                del notes_dict[note]
                        
                #        # Note ON
                #        elif status == 0x90:
                #            freq = midi.midi_to_frequency(note)
                #            notes_dict[note] = [
                #                osc_function(freq=freq, amp=vel/127, sample_rate=self.sample_rate), 
                #                False
                            #]

                if has_trigger:
                    # Delete notes if ended
                    ended_notes = [k for k,o in notes_dict.items() if o[0].ended and o[1]]
                    for note in ended_notes:
                        del notes_dict[note]

        except KeyboardInterrupt as err:
            self.stream.close()
            if close:
                self.midi_input.close()

    def on_a(self, pressed):
        if pressed:
            self.notes_dict["A"] = [self.osc(freq=740, amp=100, sample_rate=self.sample_rate), False]
        else:
            del self.notes_dict["A"]
    def on_b(self, pressed):
        if pressed:
            self.notes_dict["B"] = [self.osc(freq=587.3, amp=100, sample_rate=self.sample_rate), False]
        else:
            del self.notes_dict["B"]
    def on_c(self, pressed):
        if pressed:
            self.notes_dict["C"] = [self.osc(freq=523.3, amp=100, sample_rate=self.sample_rate), False]
        else:
            del self.notes_dict["C"]
    def on_x(self, pressed):
        if pressed:
            self.notes_dict["X"] = [self.osc(freq=493.9, amp=100, sample_rate=self.sample_rate), False]
        else:
            del self.notes_dict["X"]
    def on_y(self, pressed):
        if pressed:
            self.notes_dict["Y"] = [self.osc(freq=466.2, amp=100, sample_rate=self.sample_rate), False]
        else:
            del self.notes_dict["Y"]
    def on_z(self, pressed):
        if pressed:
            self.notes_dict["Z"] = [self.osc(freq=440, amp=100, sample_rate=self.sample_rate), False]
        else:
            del self.notes_dict["Z"]
    def on_select(self, pressed):
        self.crazy = pressed
    def on_start(self, pressed):
        pass
    def on_red_buttons(self, pressed):
        pass

    def print_console_header(self):
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


synth = PolySynth()
synth.play(osc_function=get_sin_oscillator)