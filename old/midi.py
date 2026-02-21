import sys
import os

import pygame as pg
import pygame.midi



def input_main(device_id=None):
    pg.init()
    pygame.midi.init()
    i = pygame.midi.Input(device_id)

    going = True
    while going:
        events = pygame.event.get()
        for e in events:
            if e.type in [pg.QUIT]:
                going = False
            if e.type in [pg.KEYDOWN]:
                going = False
            if e.type in [pygame.midi.MIDIIN]:
                print(e)

        if i.poll():
            midi_events = i.read(10)
            for event in midi_events:
                (status, note, vel, _), _ = event
                if not status == 248:
                    print(event)
                # Note OFF
                if status == 0x80:
                    pass
                    #if has_trigger:
                    #    notes_dict[note][0].trigger_release()
                    #    notes_dict[note][1] = True
                    #else:
                    #    del notes_dict[note]
                        
                # Note ON
                elif status == 0x90:
                    pass
                    #freq = midi.midi_to_frequency(note)
                    #notes_dict[note] = [
                    #    osc_function(freq=freq, amp=vel/127, sample_rate=self.sample_rate), 
                    #    False
                    #]

    del i
    pygame.midi.quit()

if __name__ == "__main__":

    input_main(3)

    pg.quit()