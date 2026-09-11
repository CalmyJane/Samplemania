# Samplemania

Musical sample player + recorder for the PiBoy DMG (Raspberry Pi based handheld running RetroPie).

## Deployment - keep this in mind for every change

- The code is developed on Windows but **runs only on the PiBoy**. It is copied there
  **manually** (e.g. into `/home/pi/RetroPie/roms/python`) and started from
  **EmulationStation** via a custom "python" system with the command `sudo python3 %ROM%`.
- EmulationStation lists every `.py` file in that folder as a "game". So the root must
  contain **only `Samplemania.py`** - all helper modules go into `lib/`, all images into
  `graphics/`. Never add another `.py` to the root.
- Everything in the folder gets copied to the device, so **never leave generated files
  behind**: no `__pycache__`, no `.pyc`, no test scripts, screenshots or temp files in the
  project. Put those in the scratchpad. Python runs here have `PYTHONDONTWRITEBYTECODE=1`
  (`.claude/settings.json`); also pass `python -B` and don't use `py_compile`.
- The app runs as root, fullscreen 640x480, controlled only by the PiBoy buttons
  (evdev via `lib/PiBoyInput.py`) - no keyboard, mouse or terminal while it runs.
- Hardware-dependent parts (evdev, sounddevice/USB mic, PiBoy display) can't be run on
  Windows. Test what can be tested offline (e.g. `lib/sample_edit.py` is pure numpy,
  UI screens can be rendered with `SDL_VIDEODRIVER=dummy`) and say clearly what still
  needs checking on the device.
- Target is the Pi's system **Python 3.7** (old RetroPie image) - no syntax or stdlib
  features newer than 3.7 (no walrus, no `match`, no `list[int]` hints), and no libraries
  that aren't installable there (`apt` or `sudo pip3`).
- Paths on the device: samples in `/home/pi/RetroPie/files/samples` (one subfolder per
  preset), recordings in its `Recordings/` subfolder, settings in `lib/config.py`.

## ProtonDrive

The project folder lives in ProtonDrive. Several quick writes to the same file can make
the sync create a `<name> (# Name clash <date> <id> #).py` copy and put an older version
back in place. After editing, check for `*Name clash*` files, compare them with the
original and restore the right version before finishing - a clash copy in `lib/` would
also be copied to the PiBoy.

## Layout

    Samplemania.py   entry point, adds lib/ to sys.path
    lib/             PiBoyUI, PiBoyInput, sampler, modes (play/record screens),
                     recorder, sample_edit (trim/normalise), config, check_audio
    graphics/        UI images (loaded via config.asset)
