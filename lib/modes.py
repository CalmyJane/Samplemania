"""Screen modes. The App owns the hardware and shared widgets, each mode owns
its own input handling and drawing."""

import os
import time

import pygame
from pygame import mixer
from pygame.locals import Color

import config
import recorder
import sample_edit
from PiBoyUI import Text, Meter, ConfirmDialog
from sampler import graveyard


def stop_all_channels():
    """Silence everything with a single mixer call, and only if something
    plays. Each stop takes SDL's audio lock while holding the GIL - the
    fewer of those, the fewer chances to collide with the audio thread."""
    if mixer.get_busy():
        mixer.stop()


class Mode:
    """Base mode. frame_timeout drives the main loop: None means block until a
    button event (zero polling latency), a float means also wake up that often
    so animated screens can redraw."""

    frame_timeout = None

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
    def on_select(self, pressed): pass
    def on_left_shoulder(self, pressed): pass
    def on_right_shoulder(self, pressed): pass
    def on_red_buttons(self, pressed): pass


class PlayMode(Mode):
    """The original Samplemania screen: 6 buttons, 6 channels, paged presets."""

    frame_timeout = None

    def enter(self):
        self.app.update_presetview()

    def draw(self, screen):
        app = self.app
        app.dpad.set_values(app.input.up, app.input.down, app.input.left, app.input.right)
        app.bg.draw(screen)
        app.dpad.draw(screen)
        app.presetview.draw(screen)
        app.buttonrow.draw(screen)
        app.presetlabel.draw(screen)

    def _hit(self, button_index, list_index, pressed):
        self.app.buttonrow.set_button(button_index, pressed)
        self.app.presetview.highlight(list_index, pressed)
        if pressed:
            self.app.activepreset.play_sample(list_index, self.app.channels[list_index])

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
            mixer.fadeout(self.app.fadetime)

    def on_start(self, pressed):
        # start+select is the quit combo, handled by App - don't open the menu then
        if pressed and not self.app.input.select:
            self.app.menu.open()

    def on_red_buttons(self, pressed):
        if pressed:
            # Instant stop across all channels for beat-tight performance
            stop_all_channels()


class RecordMode(Mode):
    """Arm, record, auto-trim, save into the Recordings preset.

    Also the file manager for recordings: every take in the folder can be
    picked with up/down, previewed and deleted, not just the newest one.
    """

    frame_timeout = 1.0 / 30.0
    VISIBLE = 3                 # take rows that fit under the meter
    MIN_TAKE_SECONDS = 0.3      # shorter holds are a tap, not a take - discarded

    HELP1 = "hold Z record   A preview   SELECT delete"
    HELP2 = "UP/DOWN pick take   START menu"
    HELP_RECORDING = "release Z to save     B cancels the take"

    def __init__(self, app):
        Mode.__init__(self, app)
        self.recorder = None        # created on first enter, see there
        self._preview_sound = None
        self.meter = Meter((100, 180), size=(330, 18))
        self.status = ""
        self.last_info = ""
        self.confirm = None         # ConfirmDialog while asking to delete
        self._blink = 0

        self.takes = []             # file names, newest first
        self.sel = 0                # index into self.takes
        self.top = 0                # first visible row

        # Labels are built once and re-rendered only when their text changes.
        # Black backgrounds keep them readable over the background lines.
        black = Color('black')
        self.lbl_timer = Text("  0.0s", (492, 177), 30, (255, 120, 120), black, padding=4)
        self.lbl_status = Text("", (100, 228), 26, (120, 255, 140), black, padding=4)
        self.lbl_header = Text("", (100, 258), 22, (150, 150, 150), black, padding=4)
        self.lbl_rows = [Text("", (100, 284 + i * 27), 26, (220, 220, 120), black, padding=4)
                         for i in range(self.VISIBLE)]
        self.lbl_help1 = Text(self.HELP1, (100, 380), 24, (180, 180, 180), black, padding=4)
        self.lbl_help2 = Text(self.HELP2, (100, 408), 24, (180, 180, 180), black, padding=4)

    ## LIFECYCLE ##

    def enter(self):
        # The recorder (and with it PortAudio) is only set up once the record
        # screen is actually used - a playback-only session never touches it.
        if self.recorder is None:
            self.recorder = recorder.Recorder()
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

    def on_start(self, pressed):
        if not pressed or self.app.input.select:
            return
        if self.recorder.recording:
            self.status = "STOP RECORDING FIRST"
            return
        self.confirm = None
        self.app.menu.open()

    ## DRAW ##

    def draw(self, screen):
        app = self.app
        app.bg.draw(screen)

        if self.recorder.recording:
            if self._blink < 18:
                pygame.draw.circle(screen, (240, 40, 40), (478, 189), 8)
            self.lbl_timer.set_text("{0:5.1f}s".format(self.recorder.duration))
            self.lbl_timer.draw(screen)

        self.meter.draw(screen)

        bad = "ERROR" in self.status or "FAIL" in self.status or "MIC:" in self.status
        self.lbl_status.set_color((255, 120, 120) if bad else (120, 255, 140))
        self.lbl_status.set_text(self.status[:46])
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
            row.set_text("{0} {1}".format(">" if picked else " ", name[:30]))
            row.set_color((255, 240, 140) if picked else (150, 150, 110))
            row.draw(screen)


class Menu(Mode):
    """Main menu, drawn as an overlay on top of the active mode.

    START opens it with the first entry picked, UP/DOWN picks an entry, A or
    START opens it, B closes the menu. So START, START always leads back to
    Playback. The mode underneath is not exited while the menu is open, so
    closing it returns to that screen exactly as it was.

    An entry is (label, target): a Mode is switched to, anything else is
    called. A called entry can ask for confirmation with ask().
    """

    WIDTH = 360
    ROW = 48
    HIGHLIGHT = (230, 60, 60)

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

        self.title = Text("MENU", (x + 24, y + 20), 44, Color('white'), None)
        self.rows = [Text(label, (x + 48, y + 88 + i * self.ROW), 38, Color('white'), None)
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
        # START never answers a confirmation - only A does, so pressing START
        # a few times can't quit by accident. START + SELECT is the quit combo.
        if pressed and not self.confirm and not self.app.input.select:
            self._choose()

    ## DRAW ##

    def draw(self, screen):
        screen.blit(self.overlay, (0, 0))
        pygame.draw.rect(screen, (25, 25, 30), self.rect)
        pygame.draw.rect(screen, self.HIGHLIGHT, self.rect, 3)
        self.title.draw(screen)

        for i, row in enumerate(self.rows):
            picked = i == self.sel
            if picked:
                bar = pygame.Rect(self.rect.x + 16, row.rect.y - 8,
                                  self.WIDTH - 32, self.ROW - 6)
                pygame.draw.rect(screen, self.HIGHLIGHT, bar)
            row.set_color(Color('white') if picked else (150, 150, 150))
            row.draw(screen)

        self.hint.draw(screen)

        if self.confirm:
            self.confirm[0].draw(screen)
