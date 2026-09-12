"""Screen modes. The App owns the hardware and shared widgets, each mode owns
its own input handling and drawing."""

import math
import os
import time

import pygame
from pygame import mixer
from pygame.locals import Color

import config
import pitch
import recorder
import sample_edit
from PiBoyUI import (Text, Meter, ConfirmDialog, Panel, Splash, HEADER_H,
                     GB, GB_TEXT, GB_BRIGHT, split_number)

# The play and pitch screens redraw at the speed of the background animation.
# With the animation switched off they go back to drawing only when something
# changed, which is the cheapest the app can be.
ANIM_TIMEOUT = (1.0 / config.UI_ANIM_FPS) if config.UI_ANIM_FPS > 0 else None
from sampler import graveyard


def stop_all_channels():
    """Silence everything with a single mixer call, and only if something
    plays. Each stop takes SDL's audio lock while holding the GIL - the
    fewer of those, the fewer chances to collide with the audio thread."""
    if mixer.get_busy():
        mixer.stop()


def clear_buttons(app):
    """No tile lit and no button picture pressed. Called when a screen is
    entered or left, so nothing stays lit from the screen before."""
    app.presetview.clear()
    for i in range(6):
        app.set_button(i, False)


def stop_or_fade(fadetime):
    """SELECT: stop everything, or fade it out over fadetime ms.

    fadetime 0 means instant, so it has to be a real stop - mixer.fadeout(0)
    only takes effect with the next audio buffer, which is audible as a short
    tail when you cut the music.
    """
    if fadetime > 0:
        mixer.fadeout(fadetime)
    else:
        stop_all_channels()


class Mode:
    """Base mode. frame_timeout drives the main loop: None means block until a
    button event (zero polling latency), a float means also wake up that often
    so animated screens can redraw."""

    frame_timeout = None
    dirty = False           # set when the screen changed without a button event

    def __init__(self, app):
        self.app = app

    def enter(self):
        pass

    def exit(self):
        pass

    def tick(self):
        """Called once per main loop iteration, before draw."""
        pass

    def draw(self, screen):
        pass

    def on_a(self, pressed): pass
    def on_b(self, pressed): pass
    def on_c(self, pressed): pass
    def on_x(self, pressed): pass
    def on_y(self, pressed): pass
    def on_z(self, pressed): pass
    def on_up(self, pressed): pass
    def on_down(self, pressed): pass
    def on_left(self, pressed): pass
    def on_right(self, pressed): pass
    def on_start(self, pressed): pass

    def start_allowed(self):
        """May START open the menu / peek at playback right now? A screen that
        is busy (recording) says no and shows why."""
        return True
    def on_select(self, pressed): pass
    def on_left_shoulder(self, pressed): pass
    def on_right_shoulder(self, pressed): pass
    def on_red_buttons(self, pressed): pass


class SplashMode(Mode):
    """The title screen. Shown at startup for config.SPLASH_SECONDS and from
    the menu; any button ends it and goes back to where it came from.

    It draws its background live rather than from the pre-rendered frames, so
    the pattern keeps evolving instead of looping every second. That is only
    affordable here: nothing is playing while the title is up.
    """

    frame_timeout = ANIM_TIMEOUT or 1.0 / 15.0

    def __init__(self, app):
        Mode.__init__(self, app)
        self.splash = Splash()
        self.back = None            # screen to return to
        self.until = 0.0

    def show(self, back, seconds):
        """Open the title screen over `back` for `seconds` (0 = until a
        button is pressed)."""
        self.back = back
        self.until = time.time() + seconds if seconds > 0 else 0.0
        self.app.set_mode(self)

    def enter(self):
        clear_buttons(self.app)

    def tick(self):
        if self.until and time.time() >= self.until:
            self._done()

    def _done(self):
        back, self.back = self.back, None
        if back is not None and self.app.mode is self:
            self.app.set_mode(back)

    def draw(self, screen):
        self.splash.draw(screen, self.app.bg, time.time())

    # any button ends it - including START, which is why it is not allowed to
    # open the menu while the title is up
    def _any(self, pressed):
        if pressed:
            self._done()

    on_a = on_b = on_c = on_x = on_y = on_z = _any
    on_up = on_down = on_left = on_right = _any
    on_select = on_left_shoulder = on_right_shoulder = _any

    def start_allowed(self):
        self._done()
        return False


class PlayMode(Mode):
    """The main screen: six sample tiles, six channels, paged presets.

    The tiles sit where the buttons sit (Z Y X over C B A), so pressing a
    button lights the tile you were reading. Nothing else on the screen is
    needed to know what is going on.
    """

    frame_timeout = ANIM_TIMEOUT

    def enter(self):
        self.app.header.set_tag("PLAY")
        self.app.update_presetview()
        clear_buttons(self.app)

    def exit(self):
        clear_buttons(self.app)

    def tick(self):
        # the glow follows the mixer, so a tile goes dark when its sample ends
        if self.app.refresh_tiles():
            self.dirty = True

    def draw(self, screen):
        app = self.app
        app.bg.draw(screen)
        app.header.draw(screen)
        app.presetview.draw(screen)
        if app.debugpads is not None:
            app.debugpads.draw(screen, app)

    def _hit(self, button_index, list_index, pressed):
        self.app.set_button(button_index, pressed)
        self.app.presetview.highlight(list_index, pressed)
        if pressed:
            if self.app.input.select:
                # SELECT held: pick the sample silently, e.g. to pitch it -
                # no sound, so it can be done in the middle of a performance
                sample = self.app.activepreset.get_sample(list_index)
            else:
                sample = self.app.activepreset.play_sample(list_index, self.app.channels[list_index])
                self.app.started_playing(list_index, sample)
            if sample is not None:
                self.app.last_sample = sample       # pitch mode plays this one

    def on_a(self, pressed): self._hit(5, 5, pressed)
    def on_b(self, pressed): self._hit(3, 4, pressed)
    def on_c(self, pressed): self._hit(1, 3, pressed)
    def on_x(self, pressed): self._hit(4, 2, pressed)
    def on_y(self, pressed): self._hit(2, 1, pressed)
    def on_z(self, pressed): self._hit(0, 0, pressed)

    def on_left(self, pressed):
        if pressed:
            self.app.set_current_preset((self.app.currpresetnum - 1) % len(self.app.presets))

    def on_right(self, pressed):
        if pressed:
            self.app.set_current_preset((self.app.currpresetnum + 1) % len(self.app.presets))

    def on_up(self, pressed):
        if pressed:
            self.app.change_page(True)

    def on_down(self, pressed):
        if pressed:
            self.app.change_page(False)

    def on_select(self, pressed):
        if pressed:
            stop_or_fade(self.app.fadetime)

    def on_red_buttons(self, pressed):
        if pressed:
            # Instant stop across all channels for beat-tight performance
            stop_all_channels()


class PitchMode(Mode):
    """Play the sample you triggered last as a scale across the 6 buttons.

    The buttons are the first six steps of the scale, starting at the root.
    LEFT/RIGHT pick the scale (chromatic, major, minor, pentatonics, ...),
    UP/DOWN move the root one step of that scale. Like the play screen, a new
    note cuts off the one before it.

    The pitched copies come from lib/pitch.py, which prepares the six notes
    of the current scale in the background.
    """

    frame_timeout = ANIM_TIMEOUT

    # which button belongs to which note of the scale (note index -> button)
    NOTE_BUTTONS = {0: 0, 1: 2, 2: 4, 3: 1, 4: 3, 5: 5}

    # names for the semitone offsets, so the tiles read as notes and not as
    # numbers. The sample itself is taken as C4, whatever it really is.
    NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

    def __init__(self, app):
        Mode.__init__(self, app)
        self.engine = pitch.PitchEngine()
        self.scale = 0              # index into pitch.SCALES
        self.root = 0               # in steps of that scale
        self.notes = [0] * 6        # semitone offset per button
        self.lit = None             # note index shown as pressed
        self.playing = None         # (channel, semitones) of the sounding note

    @classmethod
    def note_name(cls, semitones):
        return "{0}{1}".format(cls.NOTE_NAMES[semitones % 12],
                               4 + int(math.floor(semitones / 12.0)))

    ## LIFECYCLE ##

    def enter(self):
        clear_buttons(self.app)
        self.lit = None
        self.playing = None
        sample = self.app.last_sample
        if sample is None:
            self.engine.set_source(None)
        else:
            if sample.sound is None:
                sample.load()
            self.engine.set_source(sample.sound, sample.get_name())
        self._refresh()

    def exit(self):
        # the note may keep sounding, but the screen it was lit on is gone
        clear_buttons(self.app)
        self.lit = None
        self.playing = None

    def tick(self):
        # the lamp shows what is sounding, so it goes out when the note ends
        if self.playing is not None and not self.app.channels[self.playing[0]].get_busy():
            self.playing = None
            self._light(None)

    def _light(self, note_index):
        """Show this note as the pressed button (None = nothing pressed)."""
        if note_index == self.lit:
            return
        if self.lit is not None:
            self.app.set_button(self.NOTE_BUTTONS[self.lit], False)
            self.app.presetview.highlight(self.lit, False)
        self.lit = note_index
        if note_index is not None:
            self.app.set_button(self.NOTE_BUTTONS[note_index], True)
            self.app.presetview.highlight(note_index, True)
        self.dirty = True           # the main loop redraws for this

    def _refresh(self):
        """Work out the six notes, relabel and prepare them in the background."""
        name, intervals = pitch.SCALES[self.scale]
        self.notes = [pitch.step_semitones(intervals, self.root + i) for i in range(6)]
        self.app.header.set_tag(name)
        if self.engine.ready:
            # the number in front of the name belongs to the slot, not to
            # the sample - the tiles show it in their corner
            self.app.header.set_title(split_number(self.engine.name)[1],
                                      self.note_name(self.notes[0]))
            self.app.presetview.set_strings(
                [self.note_name(n) for n in self.notes],
                ["{0:+d}".format(n) for n in self.notes])
            self.engine.want(self.notes)
        else:
            self.app.header.set_title("PLAY A SAMPLE FIRST", "-")
            self.app.presetview.set_strings(["-"] * 6)
        # the sounding note keeps its lamp, on whichever button it now sits
        if self.playing is not None and self.playing[1] in self.notes:
            self._light(self.notes.index(self.playing[1]))
        else:
            self._light(None)

    ## INPUT ##

    def _hit(self, note_index, pressed):
        # Releasing does not clear the lamp: it follows the sound, not the
        # finger, so a long note stays marked while it plays.
        if not pressed or not self.engine.ready:
            return
        self.engine.play(self.notes[note_index], self.app.channels[note_index])
        self.playing = (note_index, self.notes[note_index])
        self._light(note_index)

    def on_a(self, pressed): self._hit(5, pressed)
    def on_b(self, pressed): self._hit(4, pressed)
    def on_c(self, pressed): self._hit(3, pressed)
    def on_x(self, pressed): self._hit(2, pressed)
    def on_y(self, pressed): self._hit(1, pressed)
    def on_z(self, pressed): self._hit(0, pressed)

    def on_up(self, pressed):
        if pressed:
            self.root += 1
            self._refresh()

    def on_down(self, pressed):
        if pressed:
            self.root -= 1
            self._refresh()

    def on_left(self, pressed):
        if pressed:
            self.scale = (self.scale - 1) % len(pitch.SCALES)
            self._refresh()

    def on_right(self, pressed):
        if pressed:
            self.scale = (self.scale + 1) % len(pitch.SCALES)
            self._refresh()

    def on_select(self, pressed):
        if pressed:
            stop_or_fade(self.app.fadetime)
            self.playing = None
            self._light(None)

    def on_red_buttons(self, pressed):
        # Fires before the note's own handler, so every note cuts off the one
        # before it - same behaviour as the play screen.
        if pressed:
            stop_all_channels()

    ## DRAW ##

    def draw(self, screen):
        app = self.app
        app.bg.draw(screen)
        app.header.draw(screen)
        app.presetview.draw(screen)
        if app.debugpads is not None:
            app.debugpads.draw(screen, app)


class RecordMode(Mode):
    """Arm, record, auto-trim, save into the Recordings preset.

    Also the file manager for recordings: every take in the folder can be
    picked with up/down, previewed and deleted, not just the newest one.
    """

    frame_timeout = 1.0 / 30.0
    VISIBLE = 5                 # take rows that fit under the meter
    MIN_TAKE_SECONDS = 0.3      # shorter holds are a tap, not a take - discarded

    HELP1 = "hold Z record   A preview   SELECT delete"
    HELP2 = "UP/DOWN pick take   START menu"
    HELP_RECORDING = "release Z to save     B cancels the take"

    def __init__(self, app):
        Mode.__init__(self, app)
        self.recorder = None        # created on first enter, see there
        self._preview_sound = None
        self.panel = Panel((10, HEADER_H + 8, 620, 480 - HEADER_H - 18))
        self.meter = Meter((44, 122), size=(472, 26))
        self.status = ""
        self.last_info = ""
        self.confirm = None         # ConfirmDialog while asking to delete
        self._blink = 0

        self.takes = []             # file names, newest first
        self.sel = 0                # index into self.takes
        self.top = 0                # first visible row

        # Labels are built once and re-rendered only when their text changes.
        # Black backgrounds keep them readable over the background lines.
        self.lbl_timer = Text("  0.0s", (74, 78), 40, (255, 120, 120), None, bold=True)
        self.lbl_status = Text("", (44, 164), 28, (120, 255, 140), None, bold=True)
        self.lbl_header = Text("", (44, 200), 24, (150, 150, 150), None, bold=True)
        self.lbl_rows = [Text("", (44, 230 + i * 32), 30, (150, 150, 150), None, bold=True)
                         for i in range(self.VISIBLE)]
        self.lbl_help1 = Text(self.HELP1, (44, 400), 24, (180, 180, 180), None)
        self.lbl_help2 = Text(self.HELP2, (44, 428), 24, (180, 180, 180), None)

    ## LIFECYCLE ##

    def enter(self):
        # The recorder (and with it PortAudio) is only set up once the record
        # screen is actually used - a playback-only session never touches it.
        if self.recorder is None:
            self.recorder = recorder.Recorder()
        self.app.header.set_tag("REC")
        # Nothing should be coming out of the speaker while a mic is open
        stop_all_channels()
        self.meter.reset()
        self.scan_takes()
        if self.recorder.error:
            self.status = "MIC: {0}".format(self.recorder.error)
        else:
            self.status = "READY - {0}".format(self.recorder.device_name)

    def exit(self):
        if self.recorder is not None and self.recorder.recording:
            self.recorder.abort()
        self.confirm = None

    def tick(self):
        self._blink = (self._blink + 1) % 30
        if self.recorder.recording:
            self.meter.set_values(self.recorder.rms, self.recorder.peak, self.recorder.clipped)
            if self.recorder.full:
                self.status = "MAX LENGTH REACHED"
                self._stop_and_save()

    ## TAKE LIST ##

    def scan_takes(self, keep=None):
        """Rescan the recordings folder. keep is a file name to stay on if it
        is still there - otherwise the selection holds its position."""
        names = []
        try:
            for n in sorted(os.listdir(config.RECORDINGS_DIR)):
                if n.startswith('.') or not n.lower().endswith('.wav'):
                    continue
                names.append(n)
        except OSError:
            pass
        names.reverse()          # timestamped names, so this is newest first
        self.takes = names

        self.app.header.set_title(config.RECORDINGS_NAME, str(len(names)))
        if keep and keep in names:
            self.sel = names.index(keep)
        self.sel = max(0, min(self.sel, len(names) - 1))
        self._scroll_to_sel()

    def _scroll_to_sel(self):
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + self.VISIBLE:
            self.top = self.sel - self.VISIBLE + 1
        self.top = max(0, min(self.top, max(0, len(self.takes) - self.VISIBLE)))

    def _move_sel(self, delta):
        if not self.takes:
            return
        self.sel = (self.sel + delta) % len(self.takes)
        self._scroll_to_sel()
        self.last_info = self._describe(self.takes[self.sel])

    def _describe(self, name):
        path = os.path.join(config.RECORDINGS_DIR, name)
        secs = sample_edit.wav_duration(path)
        return "{0}  {1:.1f}s".format(os.path.splitext(name)[0], secs)

    def selected_paths(self):
        """(sample path, raw path) for the highlighted take, or None."""
        if not self.takes:
            return None
        name = self.takes[self.sel]
        return (os.path.join(config.RECORDINGS_DIR, name),
                os.path.join(config.RAW_DIR, name))

    ## RECORDING ##

    def _start(self):
        if not recorder.available():
            self.status = "sounddevice missing: {0}".format(recorder.SD_ERROR)
            return
        stop_all_channels()
        self.meter.reset()
        if self.recorder.start():
            self.status = "RECORDING - release Z to stop"
        else:
            self.status = "MIC ERROR: {0}".format(self.recorder.error)

    def _stop_and_save(self):
        # Trimming and writing a long take can take seconds on the Pi
        self.app.watchdog.feed(120)
        data = self.recorder.stop()
        self.meter.reset()
        if data is None or len(data) == 0:
            self.status = "NOTHING RECORDED"
            return

        stamp = time.strftime("%Y%m%d_%H%M%S")
        name = "rec_{0}.wav".format(stamp)
        raw_path = os.path.join(config.RAW_DIR, name)
        out_path = os.path.join(config.RECORDINGS_DIR, name)

        try:
            config.ensure_dirs()
            # raw first - if trimming goes wrong the take still exists
            sample_edit.write_wav(raw_path, data, self.recorder.samplerate,
                                  self.recorder.channels)

            work = sample_edit.apply_gain(data, config.RECORD_GAIN)
            trimmed, did_trim = sample_edit.smart_trim(work, self.recorder.samplerate)

            gain_db = 0.0
            if config.NORMALIZE:
                trimmed, gain_db = sample_edit.normalize(
                    trimmed, config.TARGET_PEAK_DBFS, config.MAX_GAIN_DB)

            sample_edit.write_wav(out_path, trimmed, self.recorder.samplerate,
                                  self.recorder.channels)
        except Exception as e:
            self.status = "SAVE FAILED: {0}".format(e)
            print("Save failed: {0}".format(e))
            return

        secs = len(trimmed) / float(self.recorder.samplerate)
        self.last_info = "{0}  {1:.1f}s  {2:.0f}dB{3}".format(
            os.path.splitext(name)[0], secs,
            sample_edit.peak_dbfs(trimmed),
            "" if did_trim else "  (no trim)")
        self.status = "SAVED"
        if gain_db:
            self.status += " +{0:.0f}dB".format(gain_db)
        if not did_trim:
            self.status += " - all quiet, kept full take"

        self.scan_takes(keep=name)
        self.app.refresh_presets()

    def _preview(self):
        paths = self.selected_paths()
        if not paths:
            self.status = "NO TAKES YET"
            return
        try:
            sound = mixer.Sound(paths[0])
            self.app.channels[0].play(sound)
            # keep a reference - see sampler.Graveyard for why sounds must
            # not simply be dropped
            if self._preview_sound is not None:
                graveyard.add(self._preview_sound)
            self._preview_sound = sound
            self.status = "PLAYING {0}".format(self.takes[self.sel])
        except Exception as e:
            self.status = "PREVIEW FAILED: {0}".format(e)

    def _delete_selected(self):
        paths = self.selected_paths()
        if not paths:
            return
        name = self.takes[self.sel]
        stop_all_channels()      # never delete a file the mixer is streaming
        sample_edit.delete_sample(paths[0], paths[1])
        self.status = "DELETED {0}".format(name)
        self.last_info = ""
        self.scan_takes()
        if self.takes:
            self.last_info = self._describe(self.takes[self.sel])
        self.app.refresh_presets()

    ## INPUT ##

    def on_z(self, pressed):
        # Hold Z to record, release to stop. The release click then lands at
        # the very end of the take, where the trim drops it, instead of just
        # after the start.
        if self.confirm:
            return
        if pressed:
            if not self.recorder.recording:     # key repeats while held: ignore
                self._start()
        elif self.recorder.recording:
            if self.recorder.duration < self.MIN_TAKE_SECONDS:
                self.recorder.abort()
                self.meter.reset()
                self.status = "HOLD Z WHILE RECORDING"
            else:
                self._stop_and_save()

    def on_a(self, pressed):
        if not pressed:
            return
        if self.confirm:
            self.confirm = None
            self._delete_selected()
        elif not self.recorder.recording:
            self._preview()

    def on_b(self, pressed):
        if not pressed:
            return
        if self.confirm:
            self.confirm = None
            self.status = "CANCELLED"
        elif self.recorder is not None and self.recorder.recording:
            # B while Z is held: throw the take away. Releasing Z afterwards
            # finds nothing recording and saves nothing.
            self.recorder.abort()
            self.meter.reset()
            self.status = "RECORDING CANCELLED"

    def on_up(self, pressed):
        if pressed and not self.confirm and not self.recorder.recording:
            self._move_sel(-1)

    def on_down(self, pressed):
        if pressed and not self.confirm and not self.recorder.recording:
            self._move_sel(1)

    def on_select(self, pressed):
        if not pressed or self.recorder.recording:
            return
        if self.confirm:
            return
        if not self.takes:
            self.status = "NO TAKE TO DELETE"
            return
        self.confirm = ConfirmDialog("DELETE THIS TAKE?", self.takes[self.sel])

    def start_allowed(self):
        if self.recorder is not None and self.recorder.recording:
            self.status = "STOP RECORDING FIRST"
            return False
        self.confirm = None
        return True

    ## DRAW ##

    def draw(self, screen):
        app = self.app
        app.bg.draw(screen)
        app.header.draw(screen)
        self.panel.draw(screen)

        # the timer is always there, so the top of the panel isn't a hole;
        # the blinking dot next to it only while a take is running
        if self.recorder.recording:
            if self._blink < 18:
                pygame.draw.circle(screen, (240, 40, 40), (54, 92), 10)
            self.lbl_timer.set_color((255, 120, 120))
            self.lbl_timer.set_text("{0:5.1f}s".format(self.recorder.duration))
        else:
            self.lbl_timer.set_color((110, 115, 115))
            self.lbl_timer.set_text("  0.0s")
        self.lbl_timer.draw(screen)

        self.meter.draw(screen)

        bad = "ERROR" in self.status or "FAIL" in self.status or "MIC:" in self.status
        self.lbl_status.set_color((255, 120, 120) if bad else (120, 255, 140))
        self.lbl_status.set_text(self.status[:42])
        self.lbl_status.draw(screen)

        self._draw_takes(screen)

        # While recording, the help line says how to save or cancel instead
        if self.recorder is not None and self.recorder.recording:
            self.lbl_help1.set_text(self.HELP_RECORDING)
            self.lbl_help2.set_text("")
        else:
            self.lbl_help1.set_text(self.HELP1)
            self.lbl_help2.set_text(self.HELP2)
        self.lbl_help1.draw(screen)
        if self.lbl_help2.text:
            self.lbl_help2.draw(screen)

        if self.confirm:
            self.confirm.draw(screen)

    def _draw_takes(self, screen):
        if not self.takes:
            self.lbl_header.set_text("NO TAKES YET")
            self.lbl_header.draw(screen)
            return

        self.lbl_header.set_text("TAKES  {0}/{1}".format(self.sel + 1, len(self.takes)))
        self.lbl_header.draw(screen)

        for i, row in enumerate(self.lbl_rows):
            index = self.top + i
            if index >= len(self.takes):
                continue
            name = os.path.splitext(self.takes[index])[0]
            picked = index == self.sel
            row.set_text("{0} {1}".format(">" if picked else " ", name[:28]))
            row.set_color(GB_BRIGHT if picked else (150, 150, 150))
            row.draw(screen)


class Menu(Mode):
    """Main menu, drawn as an overlay on top of the active mode.

    START opens it with the first entry picked, UP/DOWN picks an entry, A or
    START opens it, B closes the menu. So START, START always leads back to
    Playback. The mode underneath is not exited while the menu is open, so
    closing it returns to that screen exactly as it was.

    An entry is (label, target): a Mode is switched to, anything else is
    called. A called entry can ask for confirmation with ask(). The label may
    be a function instead of a string, for an entry that shows a setting
    ("STYLE: BOXES") - it is asked for the current text on every draw.
    """

    WIDTH = 360
    ROW = 48
    HIGHLIGHT = GB                  # the accent; red stays for warnings

    def __init__(self, app, entries):
        Mode.__init__(self, app)
        self.entries = entries          # [(label, mode or callable), ...]
        self.is_open = False
        self.sel = 0
        self.confirm = None             # (ConfirmDialog, on_yes) while asking

        h = 78 + len(entries) * self.ROW + 52
        self.rect = pygame.Rect((640 - self.WIDTH) // 2, (480 - h) // 2, self.WIDTH, h)
        x, y = self.rect.x, self.rect.y

        self.overlay = pygame.Surface((640, 480))
        self.overlay.set_alpha(170)
        self.overlay.fill((0, 0, 0))

        self.title = Text("MENU", (x + 24, y + 20), 44, Color('white'), None, bold=True)
        self.rows = [Text(label() if callable(label) else label,
                          (x + 48, y + 88 + i * self.ROW), 38,
                          Color('white'), None, bold=True)
                     for i, (label, _) in enumerate(entries)]
        self.hint = Text("A / START open     B close", (x + 24, y + h - 38), 24,
                         (180, 180, 180), None)

    def open(self):
        """Show the menu with the first entry picked."""
        self.is_open = True
        self.sel = 0
        self.confirm = None

    def close(self):
        self.is_open = False
        self.confirm = None

    def ask(self, message, on_yes):
        """Show a yes/no box over the menu; A calls on_yes, B goes back."""
        self.confirm = (ConfirmDialog(message), on_yes)

    def _choose(self):
        target = self.entries[self.sel][1]
        if isinstance(target, Mode):
            self.close()
            self.app.set_mode(target)
        else:
            target()
            if self.confirm is None:
                self.close()

    ## INPUT ##

    def on_up(self, pressed):
        if pressed and not self.confirm:
            self.sel = (self.sel - 1) % len(self.entries)

    def on_down(self, pressed):
        if pressed and not self.confirm:
            self.sel = (self.sel + 1) % len(self.entries)

    def on_a(self, pressed):
        if not pressed:
            return
        if self.confirm:
            on_yes = self.confirm[1]
            self.close()
            on_yes()
        else:
            self._choose()

    def on_b(self, pressed):
        if not pressed:
            return
        if self.confirm:
            self.confirm = None         # back to the menu
        else:
            self.close()

    def on_start(self, pressed):
        # START never answers a confirmation - only A does, so tapping START
        # a few times can't quit by accident.
        if pressed and not self.confirm:
            self._choose()

    ## DRAW ##

    def draw(self, screen):
        screen.blit(self.overlay, (0, 0))
        pygame.draw.rect(screen, (25, 25, 30), self.rect)
        pygame.draw.rect(screen, self.HIGHLIGHT, self.rect, 3)
        self.title.draw(screen)

        for i, row in enumerate(self.rows):
            label = self.entries[i][0]
            if callable(label):
                row.set_text(label())
            picked = i == self.sel
            if picked:
                bar = pygame.Rect(self.rect.x + 16, row.rect.y - 8,
                                  self.WIDTH - 32, self.ROW - 6)
                pygame.draw.rect(screen, self.HIGHLIGHT, bar)
            row.set_color(GB_TEXT if picked else (160, 160, 160))
            row.draw(screen)

        self.hint.draw(screen)

        if self.confirm:
            self.confirm[0].draw(screen)
