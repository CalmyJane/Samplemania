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
            self.app.activepreset.change_page(True)
            self.app.update_presetview()

    def on_down(self, pressed):
        if pressed:
            self.app.activepreset.change_page(False)
            self.app.update_presetview()

    def on_select(self, pressed):
        if pressed:
            mixer.fadeout(self.app.fadetime)

    def on_start(self, pressed):
        # start+select is the quit combo, handled by App - don't switch mode then
        if pressed and not self.app.input.select:
            self.app.set_mode(self.app.recordmode)

    def on_red_buttons(self, pressed):
        if pressed:
            # Instant stop across all channels for beat-tight performance
            for chan in self.app.channels:
                chan.stop()


class RecordMode(Mode):
    """Arm, record, auto-trim, save into the Recordings preset.

    Also the file manager for recordings: every take in the folder can be
    picked with up/down, previewed and deleted, not just the newest one.
    """

    frame_timeout = 1.0 / 30.0
    VISIBLE = 3                 # take rows that fit under the meter

    def __init__(self, app):
        Mode.__init__(self, app)
        self.recorder = recorder.Recorder()
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
        self.lbl_help1 = Text("Z rec/stop   A preview   SELECT delete",
                              (100, 380), 24, (180, 180, 180), black, padding=4)
        self.lbl_help2 = Text("UP/DOWN pick take   START back to play",
                              (100, 408), 24, (180, 180, 180), black, padding=4)

    ## LIFECYCLE ##

    def enter(self):
        # Nothing should be coming out of the speaker while a mic is open
        for chan in self.app.channels:
            chan.stop()
        self.meter.reset()
        self.scan_takes()
        if self.recorder.error:
            self.status = "MIC: {0}".format(self.recorder.error)
        else:
            self.status = "READY - {0}".format(self.recorder.device_name)

    def exit(self):
        if self.recorder.recording:
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
        for chan in self.app.channels:
            chan.stop()
        self.meter.reset()
        if self.recorder.start():
            self.status = "RECORDING"
        else:
            self.status = "MIC ERROR: {0}".format(self.recorder.error)

    def _stop_and_save(self):
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
            self.status = "PLAYING {0}".format(self.takes[self.sel])
        except Exception as e:
            self.status = "PREVIEW FAILED: {0}".format(e)

    def _delete_selected(self):
        paths = self.selected_paths()
        if not paths:
            return
        name = self.takes[self.sel]
        for chan in self.app.channels:
            chan.stop()          # never delete a file the mixer is streaming
        sample_edit.delete_sample(paths[0], paths[1])
        self.status = "DELETED {0}".format(name)
        self.last_info = ""
        self.scan_takes()
        if self.takes:
            self.last_info = self._describe(self.takes[self.sel])
        self.app.refresh_presets()

    ## INPUT ##

    def on_z(self, pressed):
        if not pressed or self.confirm:
            return
        if self.recorder.recording:
            self._stop_and_save()
        else:
            self._start()

    def on_a(self, pressed):
        if not pressed:
            return
        if self.confirm:
            self.confirm = None
            self._delete_selected()
        elif not self.recorder.recording:
            self._preview()

    def on_b(self, pressed):
        if pressed and self.confirm:
            self.confirm = None
            self.status = "CANCELLED"

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
        self.app.set_mode(self.app.playmode)

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

        self.lbl_help1.draw(screen)
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
