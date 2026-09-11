# Samplemania

## Overview

Samplemania is a musical python app for the PiBoy DMG, a raspberry-based gameboy emulator.

It is not a game but a sample player - with a built-in recorder, so you can
sample your own sounds straight into the library.

!['Samplemania running on PiBoy DMG'](graphics/samplemania.jpg)

## Samplemania

Samplemania plays back samples (16bit mono wav) that are copied to the piboys memory (`/home/pi/RetroPie/files/samples`). Every subfolder in there shows up as a preset. It's not a musical sampler with sequencer functionality, but main focus is to quickly navigate a big sample library, playing back different samples on one of the 6 buttons of the piboy.

It can also **record** from a USB microphone: takes are auto-trimmed, normalised
and dropped into the library as a preset called `Recordings`, ready to play
right away. See [Recording](#recording) below.

### Controls

| Button | Action |
| --- | --- |
| A / B / C / X / Y / Z | play the sample on that button |
| LEFT / RIGHT | previous / next preset |
| UP / DOWN | page through the samples of the preset (6 per page) |
| SELECT | fade out all samples |
| red buttons | stop all samples instantly |
| START | go to the record screen |
| START + SELECT | quit |

## Folder structure

    Samplemania.py      the app - the only file EmulationStation needs to list
    lib/                helper modules (UI, input, sampler, recorder, config, ...)
      config.py         paths, recording format, loudness and mic settings
      check_audio.py    diagnostic tool for the recording setup
    graphics/           images used by the UI

## How to run this

To run this code, you need to register python files as plugins.

Step by Step setup:

1. Setup your PiBoy DMG as described here: https://resources.experimentalpi.com/the-complete-piboy-dmg-getting-started-guide/
2. Connect PiBoy to your Wifi: https://resources.experimentalpi.com/piboy-dmg-wifi-setup/
3. Connect to your PiBoy DMG by typing `\\retropie` in your Explorer while the device is turned on and connected to wifi
4. Add some ROMs for testing, you can find them on google ;)
5. Add a new "System" to your EmulationStation, this is a new type of ROMs you want to load, make the file type ".py" and the command "sudo python3 %ROM%": https://retropie.org.uk/docs/Add-a-New-System-in-EmulationStation/ You can basically also add all kind of files or direct shell script this way. Be aware, that this as always is a security risk ;)
6. Copy `Samplemania.py` together with the `lib` and `graphics` folders to the folder you specified for the system on `\\retropie` (e.g. `/home/pi/RetroPie/roms/python`)
7. Copy your samples into `/home/pi/RetroPie/files/samples`, one subfolder per preset
8. Start your PiBoy and in EmulationStation instead of "GameBoy" or "GameBoy Color" select "python" and select Samplemania

I hope you find other ways to play around here, this was a really fun project, and can potentially be used to develop custom games for the PiBoy as well :D

## Recording

Samplemania can record from a USB microphone and drop the takes straight into
the library as a preset called `Recordings`.

Press **START** in the play screen to reach the record screen:

| Button | Action |
| --- | --- |
| Z | start / stop recording |
| UP / DOWN | pick a take from the list |
| A | preview the picked take (confirms when asked to delete) |
| SELECT | delete the picked take (asks first) |
| B | cancel the delete |
| START | back to the play screen |
| START + SELECT | quit |

While recording, a level meter shows the input level and a timer shows the
length of the take (max 5 minutes, `MAX_RECORD_SECONDS` in `lib/config.py`).

Takes are listed newest first, so the one you just recorded is already
selected - but any take in the folder can be picked and deleted, not only the
last one. Deleting removes the raw original along with it. New takes show up
in the play screen's `Recordings` preset without restarting the app.

On stop the take is written twice: the untouched original to
`Recordings/.raw/`, and an auto-trimmed copy to `Recordings/` which is what
plays back. The trim estimates the room's noise floor from the take itself, so
it still finds the start of a word in a loud room; if nothing rises above the
floor the full take is kept instead. The raw file is never modified, so a bad
trim can always be redone from it.

The trimmed copy is also peak normalised to -3dBFS, because USB mics record
far too quietly to sit next to the rest of the library. `NORMALIZE`,
`TARGET_PEAK_DBFS` and `MAX_GAIN_DB` in `lib/config.py` control that; the 30dB gain
cap stops a take of pure room noise being lifted into a wall of hiss. If takes
are still quiet, the mic's own capture level is the thing to raise - run
`alsamixer`, press F6 to pick the USB card, F4 for capture, and turn it up
(plus `Mic Boost` if the card has one). `RECORD_GAIN` in `lib/config.py` is the
last resort, applied before the trim detector, for a mic with no usable gain
control of its own.

### Setup

    sudo apt install libportaudio2 python3-cffi python3-numpy python3-pip
    sudo pip3 install sounddevice

`python3-sounddevice` is not in the RetroPie repos, hence pip. Install it with
`sudo` rather than `--user`: EmulationStation launches the app as root, and
root does not read `~/.local`.

Then check the mic is seen and producing level:

    python3 /home/pi/RetroPie/roms/python/lib/check_audio.py

If it picks the wrong device, set `INPUT_DEVICE` in `lib/config.py` to the device
index or a piece of its name.

A dynamic handheld mic (e.g. Samson Q2U) works far better than a condenser at a
party - it rejects the room instead of recording all of it.
