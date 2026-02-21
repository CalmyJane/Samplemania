import evdev
import pygame
from pygame import mixer
import os



for dp in evdev.list_devices():
    device = evdev.InputDevice(dp)
    if "PiBoy" in device.name:
        kb = device
pygame.mixer.pre_init(22050,-16,2, 256)
mixer.init()
paths = os.listdir("/home/pi/RetroPie/files/samples/18_Drums/")
paths = [os.path.join("/home/pi/RetroPie/files/samples/18_Drums/", path) for path in paths]
sounds =[mixer.Sound(path) for path in paths]

for event in kb.read_loop():
    data = evdev.categorize(event)
    if event.type != evdev.ecodes.EV_KEY:
        continue
    elif data.keystate == 0: # ignore keyup
        continue

    buttontags = ("BTN_A", "BTN_B", "BTN_C", "BTN_X", "BTN_Y", "BTN_Z")

    for i, tag in enumerate(buttontags):
        if tag in data.keycode:
            sounds[i].play()
