"""The Samplemania application. Started by Samplemania.py, which restarts it
if it crashes or hangs."""

import os
import sys
import time

import pygame
from pygame import mixer
from pygame.locals import *

import config
import stability
from stability import log
from PiBoyUI import *
from PiBoyInput import PBInput
from sampler import Preset, Loader, graveyard
from modes import SplashMode, PlayMode, PitchMode, RecordMode, Menu

# A frame (input handling + drawing) slower than this gets logged
SLOW_FRAME = 0.05


## MAIN APPLICATION ##
class App:
    def __init__(self):
        """Initialize pygame and the application."""
        # The audio thread needs the GIL whenever a sample ends. Hand it over
        # after 1ms instead of the default 5ms, so a busy main thread can't
        # starve the mixer (512 frames = 11.6ms of buffer).
        sys.setswitchinterval(0.001)

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
        self.input = PBInput()
        self.debugpads = None       # created in run() when config asks for it

        # Every button is routed to whichever mode is active (or the menu)
        for name in ('A', 'B', 'C', 'X', 'Y', 'Z', 'left', 'right', 'up', 'down',
                     'left_shoulder', 'right_shoulder', 'red_buttons', 'select', 'start'):
            self.input.set_callback(name, self._dispatch(name.lower()))

        self.fadetime = 0
        self.mode = None
        self.menu = None
        self.activepreset = None
        self.last_sample = None     # last sample played, pitch mode uses it
        # the file each channel was last started with, so the glow can follow
        # the sample through page and preset changes. By path, not by object:
        # leaving a preset throws its samples away, and coming back builds new
        # ones for the same files.
        self.playing = [None] * 6
        self.start_held_at = None   # when START went down, None while it is up
        self.peek_mode = None       # mode to return to after peeking at playback
        self.loader = Loader()
        self.watchdog = stability.Watchdog(config.WATCHDOG_SECONDS)

    def _dispatch(self, name):
        handler = 'on_' + name
        def callback(pressed):
            # A bug in a handler must never take the app down mid-performance:
            # log it and carry on with the next button press.
            try:
                # START belongs to the app, not to the screens - except while
                # the menu is open, where it picks the highlighted entry.
                if name == 'start' and not (self.menu is not None and self.menu.is_open):
                    self.on_start_button(pressed)
                    return
                # While the menu is open it takes the presses. Releases still go
                # to the mode, so a button held when the menu opened doesn't stay
                # lit on the play screen.
                if pressed and self.menu is not None and self.menu.is_open:
                    getattr(self.menu, handler)(pressed)
                else:
                    getattr(self.mode, handler)(pressed)
            except Exception:
                log.exception("error in %s", handler)
        return callback

    ## START BUTTON ##

    def on_start_button(self, pressed):
        """Tap START to open the menu; hold it to peek at the play screen.

        While it is held the play screen is active with all its buttons, so
        another sample can be picked, and releasing returns to the screen the
        peek started from - without opening the menu.
        """
        if pressed:
            if self.start_held_at is not None:
                return              # key repeat while held: don't restart the clock
            if not self.mode.start_allowed():
                return
            self.start_held_at = time.time()
            return

        held, self.start_held_at = self.start_held_at, None
        if self.peek_mode is not None:
            self.set_mode(self.peek_mode)
            self.peek_mode = None
        elif held is not None:
            self.menu.open()

    def check_start_hold(self):
        """Main loop: START held long enough switches to the play screen.
        Returns True when that just happened (the screen needs redrawing)."""
        if (self.start_held_at is None or self.peek_mode is not None
                or time.time() - self.start_held_at < config.MENU_HOLD_SECONDS):
            return False
        self.peek_mode = self.mode      # may be the play screen itself
        self.set_mode(self.playmode)
        return True

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
        if self.menu.is_open:
            self.menu.draw(App.screen)
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

        self.watchdog.feed(30)      # startup, generous
        stability.log_system_info()
        config.ensure_dirs()
        self.loader.start()

        # The screen: a shallow header and six big sample tiles below it.
        self.header = Header()
        self.style = config.UI_STYLE
        self.presetview = SampleGrid((10, HEADER_H + 8, 620,
                                      480 - HEADER_H - 18), self.style)
        if config.SHOW_DEBUG_PADS:
            self.debugpads = DebugPads()

        self.restore_style()
        self.scan_presets()
        self.currpresetnum = 0
        if not self.restore_state():
            self.set_current_preset(0)
        self.lasttime = time.time()

        self.playmode = PlayMode(self)
        self.pitchmode = PitchMode(self)
        self.recordmode = RecordMode(self)
        self.splashmode = SplashMode(self)

        # Main menu (START). Add new features here as (label, mode), or
        # (label, function) for an action. A callable label is asked for its
        # text every time the menu is drawn, for entries showing a setting.
        self.menu = Menu(self, [
            ("Playback", self.playmode),
            ("Pitch", self.pitchmode),
            ("Record", self.recordmode),
            (self.style_label, self.toggle_style),
            ("Title", self.show_splash),
            ("Exit", self.ask_exit),
        ])

        self.set_mode(self.playmode)
        if config.SPLASH_SECONDS > 0:
            self.splashmode.show(self.playmode, config.SPLASH_SECONDS)

        self.main_loop()
        self.shutdown()

    def main_loop(self):
        """Waits on the controller fd, so a button press is handled the moment
        it arrives. The wait always has a timeout, so the loop comes round at
        least every IDLE_WAIT seconds to feed the watchdog and free unused
        sounds, even when nobody touches a button.

        The screen is only redrawn after a button event, or every frame on
        animated screens. Nothing else (controller noise, idle wake-ups)
        causes a redraw - drawing holds the GIL, which the audio thread needs.
        """
        redraw = True
        last_slow_log = 0.0
        while App.running:
            self.watchdog.feed()

            # The background loops through its pre-rendered frames and the
            # glow of a sounding tile breathes - both are pure state here,
            # the modes decide (frame_timeout) whether they are drawn.
            now = time.time()
            if self.bg.tick(now):
                redraw = True
            self.presetview.tick(now)

            # modes set .dirty when they change something on their own
            # (a note ending, say), without a button event to trigger a redraw
            if redraw or self.mode.dirty:
                self.mode.dirty = False
                try:
                    self.draw()
                except Exception:
                    log.exception("error while drawing")

            timeout = self.mode.frame_timeout
            if timeout is None:
                timeout = config.IDLE_WAIT
            if self.start_held_at is not None:
                timeout = min(timeout, 0.02)    # watch for the hold to start
            ready = self.input.wait(timeout)

            started = time.time()
            events = 0
            if ready:
                try:
                    events = self.input.update()
                except Exception:
                    log.exception("error reading input")
            redraw = events > 0 or self.mode.frame_timeout is not None
            if self.check_start_hold():
                redraw = True

            try:
                self.mode.tick()
            except Exception:
                log.exception("error in %s.tick", type(self.mode).__name__)

            graveyard.collect()

            took = time.time() - started
            if took > SLOW_FRAME and started - last_slow_log > 5.0:
                last_slow_log = started
                log.warning("slow frame: %.0fms for %d events", took * 1000, events)

    ## SETTINGS ##

    def style_label(self):
        return "Style: {0}".format(self.style.upper())

    def toggle_style(self):
        """Menu entry: switch the six slots between boxes and a list."""
        self.style = LIST if self.style == BOXES else BOXES
        self.presetview.set_style(self.style)
        self.save_state()
        log.info("display style %s", self.style)

    def show_splash(self):
        """Menu entry: the title screen, until a button is pressed."""
        self.menu.close()
        self.splashmode.show(self.mode, 0)

    def ask_exit(self):
        """Menu entry: quit Samplemania after a yes/no confirmation."""
        self.menu.ask("QUIT SAMPLEMANIA?", self.quit)

    def quit(self):
        """End the main loop; shutdown() then marks it as a deliberate quit,
        so the launcher doesn't restart the app."""
        log.info("quit from the menu")
        App.running = False

    def shutdown(self):
        """Quit on purpose (the menu's Exit entry)."""
        try:
            open(config.QUIT_MARKER, "w").close()
        except (IOError, OSError):
            pass
        self.watchdog.feed(10)
        try:
            if self.mode is not None:
                self.mode.exit()
            self.loader.stop()
            self.pitchmode.engine.stop()
            mixer.stop()
        except Exception:
            log.exception("error while shutting down")
        self.watchdog.stop()
        pygame.quit()

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
            log.warning("No presets found in %s", config.SAMPLE_DIR)
            self.presets = [config.RECORDINGS_DIR]

    def refresh_presets(self):
        """Rescan the library, keeping the current preset selected by name."""
        current = self.presets[self.currpresetnum] if self.presets else None
        self.scan_presets()
        index = self.presets.index(current) if current in self.presets else 0
        self.set_current_preset(index)

    ## STATE (survives a restart by the launcher) ##

    def save_state(self):
        if self.activepreset is None:
            return
        try:
            with open(config.STATE_PATH, "w") as f:
                f.write("{0}\n{1}\n{2}\n".format(self.activepreset.path,
                                                 self.activepreset.page,
                                                 self.style))
        except (IOError, OSError):
            pass

    def restore_style(self):
        """The display style survives a restart by the launcher. The state
        file lives in RAM, so after a reboot config.UI_STYLE applies again."""
        try:
            with open(config.STATE_PATH) as f:
                style = f.read().split("\n")[2].strip()
        except (IOError, OSError, IndexError):
            return
        if style in (BOXES, LIST):
            self.style = style
            self.presetview.set_style(style)

    def restore_state(self):
        """After a restart by the launcher, go back to the saved preset and
        page. Returns True if it did."""
        if not os.environ.get("SAMPLEMANIA_RESTART"):
            return False
        try:
            with open(config.STATE_PATH) as f:
                path, page = f.read().split("\n")[:2]
            index = self.presets.index(path)
            page = int(page)
        except (IOError, OSError, ValueError):
            return False
        self.set_current_preset(index)
        self.activepreset.page = page % self.activepreset.numpages
        self.change_page_to_current()
        log.info("restored preset %s page %d after restart", path, page)
        return True

    def load_preset(self, path):
        # Creating the preset only lists the files; the loader thread reads
        # the audio into RAM in the background, current page first.
        if self.activepreset is not None:
            self.activepreset.close()
        self.activepreset = Preset(path)
        self.update_presetview()
        self.loader.load(self.activepreset)
        self.save_state()
        log.info("preset %s (%d samples), %s", self.activepreset.name,
                 len(self.activepreset.samples), stability.memory_info())

    def update_presetview(self):
        self.presetview.set_strings(self.activepreset.get_names())
        self.header.set_title(self.activepreset.name,
                              "{0}/{1}".format(self.activepreset.page + 1,
                                               self.activepreset.numpages))

    def refresh_tiles(self):
        """Keep the tiles in step with the mixer and the loader: a tile that
        is sounding glows, one whose sample is not in RAM yet shows a dot.
        Returns True when something changed, so the screen is redrawn.

        The glow follows the sample, not the channel: a channel keeps playing
        while you page or change preset, and the slot it started from then
        holds a different sample - which must not light up. Come back to the
        page it belongs to and it lights up again, as long as it still plays.
        """
        changed = False
        preset = self.activepreset
        for i in range(6):
            sample = preset.get_sample(i) if preset is not None else None
            loading = (sample is not None and sample.sound is None
                       and not sample.failed)
            if self.presetview.set_loading(i, loading):
                changed = True

            if not self.channels[i].get_busy():
                self.playing[i] = None
            playing = sample is not None and self.playing[i] == sample.path
            if self.presetview.set_playing(i, playing):
                changed = True
        return changed

    def started_playing(self, index, sample):
        """A sample was just started on the channel of slot `index`."""
        self.playing[index] = sample.path if sample is not None else None

    def set_button(self, index, pressed):
        """Debug button pictures, when they are switched on."""
        if self.debugpads is not None:
            self.debugpads.buttonrow.set_button(index, pressed)

    def change_page(self, up):
        self.activepreset.change_page(up)
        self.change_page_to_current()

    def change_page_to_current(self):
        self.update_presetview()
        self.loader.load(self.activepreset)     # new page gets loaded first
        self.save_state()

    def get_current_preset(self):
        return self.presets[self.currpresetnum]

    def set_current_preset(self, index):
        self.currpresetnum = index
        self.load_preset(self.presets[self.currpresetnum])


def main():
    stability.setup_logging()
    log.info("---- Samplemania starting ----")
    try:
        App().run()
    except Exception:
        log.exception("fatal error")
        sys.exit(1)
    log.info("Samplemania quit")


if __name__ == "__main__":
    main()
