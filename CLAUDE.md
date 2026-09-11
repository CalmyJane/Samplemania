# Samplemania

Musical sample player + recorder for the PiBoy DMG (Raspberry Pi based handheld running RetroPie).

## Stability comes first - it is used in live performances

Playback must never lag, hang or crash on stage. Weigh every change against that, and
prefer the boring, robust solution over a clever one.

- **GIL vs. audio thread:** when a sample ends, pygame's SDL audio thread takes the GIL.
  Anything that holds the GIL for long (heavy drawing, font rendering, big Python loops)
  starves the mixer -> crackles/lag. Calls that take SDL's audio lock while holding the GIL
  (stopping channels, freeing a `Sound`) can deadlock against it for good on older pygame.
  So: keep the main thread light, redraw only when something changed, pre-render and
  `convert()` surfaces, stop channels with one `mixer.stop()` only when `mixer.get_busy()`,
  and never drop the last reference to a `Sound` - hand it to `sampler.graveyard`, which
  frees sounds only while the mixer is idle.
- **One background loader** (`sampler.Loader`) - never start a thread per preset/action.
  Background work that is pure Python/numpy (e.g. `pitch.PitchEngine` resampling) holds
  the GIL too: do it in small chunks with a `time.sleep(0.001)` in between.
- **Never block the main loop:** it has to come round at least every `config.IDLE_WAIT`
  seconds, or the watchdog (`stability.Watchdog`, `config.WATCHDOG_SECONDS`) kills the app.
  Known long operations must call `app.watchdog.feed(seconds)` first (see saving a take).
- **Errors are logged, not fatal:** button handlers, drawing and ticks run inside
  try/except in `lib/app.py` and log to `samplemania.log`. Don't add code paths outside that.
- `Samplemania.py` is a launcher that restarts the app (`lib/app.py`) after a crash or
  hang and restores preset/page. START + SELECT writes a quit marker so it doesn't restart.
- Keep playback independent of optional features: e.g. `sounddevice`/PortAudio is only
  imported when the record screen is opened.
- Test what can be tested offline before handing over: the stress test pattern (fake
  controller, real main loop, random presses/preset changes for 60s, check threads,
  memory, errors) catches regressions. Redirect `config.LOG_PATH`, `STATE_PATH` and
  `QUIT_MARKER` to the scratchpad in tests so no files land in the project.

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

    Samplemania.py   launcher: runs lib/app.py, restarts it after a crash/hang
    lib/             app (App + main loop), stability (log, watchdog), PiBoyUI,
                     PiBoyInput, sampler (samples, loader, graveyard), modes
                     (play/pitch/record screens, menu), pitch (scales +
                     resampling), recorder, sample_edit (trim/normalise),
                     config, check_audio
    graphics/        UI images (loaded via config.asset)

## Screens and the menu

Each screen is a `Mode` subclass in `lib/modes.py` (button handlers `on_a`, `on_up`, ...,
plus `enter`/`exit`/`tick`/`draw`). START opens the `Menu`, an overlay drawn on top of
the active mode - the mode is not exited while the menu is open. The menu always opens
with the first entry (Playback) picked; A or START selects, B closes, so START, START
always returns to playback. To add a feature: write a new `Mode`, create it in `App.run()`
in `lib/app.py` and add a `(label, mode)` entry to the menu list there. An entry can also
be `(label, function)` for an action; use `menu.ask(message, on_yes)` for a yes/no
confirmation (A = yes, B = no, START never confirms).

START belongs to `App.on_start_button`, not to the modes: a tap opens the menu on
release, holding it past `config.MENU_HOLD_SECONDS` switches to the play screen until
it is released, then returns to the screen it started from (`App.peek_mode`). A new mode
must therefore not define `on_start`; if it may not be left right now (recording),
override `start_allowed()` and set a status message there. START + SELECT is always quit.
