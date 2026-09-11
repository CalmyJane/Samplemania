"""Offline sample processing. Pure numpy + stdlib - no pygame, no hardware.

This module is deliberately dependency-light so it can be developed and tested
on a desktop machine before deploying to the PiBoy.
"""

import os
import wave

import numpy as np

INT16_MAX = 32768.0


## FILE IO ##

def read_wav(path):
    """Read a wav into (int16 numpy array, samplerate, channels).

    Multi channel data comes back interleaved-free: shape (frames, channels)
    for stereo, flat 1D for mono.
    """
    w = wave.open(path, 'rb')
    try:
        channels = w.getnchannels()
        samplerate = w.getframerate()
        width = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    finally:
        w.close()

    if width != 2:
        raise ValueError("{0}: only 16 bit wav supported (got {1} byte)".format(path, width))

    data = np.frombuffer(raw, dtype='<i2')
    if channels > 1:
        data = data.reshape(-1, channels)
    return data, samplerate, channels


def write_wav(path, data, samplerate, channels=1):
    """Write int16 data to a wav. Writes to a temp file and renames, so a
    crash mid-write can never leave a half sample in the preset folder."""
    data = np.asarray(data, dtype=np.int16)
    tmp = path + ".tmp"
    w = wave.open(tmp, 'wb')
    try:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(samplerate)
        w.writeframes(data.tobytes())
    finally:
        w.close()
    os.replace(tmp, path)


## ANALYSIS ##

def _rms_windows(data, samplerate, window_ms):
    """Per-window RMS of a mono int16 signal. Returns (rms array, window size)."""
    win = max(1, int(samplerate * window_ms / 1000.0))
    count = len(data) // win
    if count == 0:
        return np.array([]), win
    frames = data[:count * win].astype(np.float32).reshape(count, win)
    return np.sqrt(np.mean(frames * frames, axis=1)), win


def peak_dbfs(data):
    if len(data) == 0:
        return -99.0
    peak = float(np.max(np.abs(data.astype(np.int32)))) / INT16_MAX
    if peak <= 0.0:
        return -99.0
    return 20.0 * np.log10(peak)


## EDITING ##

def apply_fades(data, samplerate, fade_in_ms=5, fade_out_ms=20):
    """Fade the edges so a hard cut in the middle of a waveform doesn't click."""
    out = data.astype(np.float32).copy()
    n = len(out)
    fin = min(int(samplerate * fade_in_ms / 1000.0), n // 2)
    fout = min(int(samplerate * fade_out_ms / 1000.0), n // 2)
    if fin > 0:
        out[:fin] *= np.linspace(0.0, 1.0, fin, dtype=np.float32)
    if fout > 0:
        out[n - fout:] *= np.linspace(1.0, 0.0, fout, dtype=np.float32)
    return out.astype(np.int16)


def _sustained(over, min_windows):
    """Indices of windows belonging to a run of at least min_windows
    consecutive over-threshold windows. Falls back to every over-threshold
    window if no run is long enough."""
    if min_windows <= 1 or over.size < min_windows:
        return np.nonzero(over)[0]
    runs = np.convolve(over.astype(np.int32), np.ones(min_windows, np.int32), 'valid')
    starts = np.nonzero(runs == min_windows)[0]
    if starts.size == 0:
        return np.nonzero(over)[0]
    return np.array([starts[0], starts[-1] + min_windows - 1])


def _runs(over):
    """(start, end) window indices of each run of True values, end exclusive."""
    edges = np.diff(np.concatenate(([0], over.astype(np.int8), [0])))
    return list(zip(np.nonzero(edges == 1)[0], np.nonzero(edges == -1)[0]))


def _drop_start_click(over, head_windows, max_windows, gap_windows):
    """Remove the click of the PiBoy's record button from an over-threshold mask.

    A click is a short run (max_windows or less) starting inside the first
    head_windows, followed by at least gap_windows of quiet before the next
    sound. The gap keeps the first consonant of a word spoken straight away
    from being mistaken for a click.

    smart_trim also runs it on the reversed mask, which finds the click of
    releasing the button at the very end of the take.

    Returns (mask, head_end): head_end is the window after the last dropped
    click, so the preroll can be kept clear of it.
    """
    over = over.copy()
    runs = _runs(over)
    head_end = 0

    for i, (s, e) in enumerate(runs):
        if s >= head_windows:
            break
        next_start = runs[i + 1][0] if i + 1 < len(runs) else len(over)
        if e - s > max_windows or next_start - e < gap_windows:
            break           # real sound has started, keep everything from here
        over[s:e] = False
        head_end = e

    return over, head_end


def smart_trim(data, samplerate,
               window_ms=10.0,
               floor_percentile=10.0,
               threshold_mult=2.5,
               min_run_ms=50.0,
               preroll_ms=30.0,
               tail_ms=150.0,
               fade_in_ms=5.0,
               fade_out_ms=20.0,
               min_floor=8.0,
               click_head_ms=500.0,
               click_tail_ms=200.0,
               click_max_ms=120.0,
               click_gap_ms=60.0):
    """Cut leading/trailing room noise, adaptively.

    The noise floor is estimated from the quietest 10% of windows in the take
    rather than assumed, so a loud party room raises the threshold with it. A
    fixed threshold (as in `sox silence 1%`) either keeps all the crowd noise
    or eats the start of the word.

    threshold_mult of 2.5 is ~8dB over the floor. Window RMS of steady room
    noise only wobbles a few percent, so that will not false-trigger on the
    room itself, and it still catches a quiet talker in a loud bar. A stray
    transient can beat it though, hence min_run_ms: the level has to stay up
    for 50ms before it counts as the start of the take.

    The record button is on the PiBoy itself and held while recording, so
    its clicks land at the edges of the take: pressing it (and the pop of the
    stream opening) in the first moments, releasing it at the very end. Short
    isolated bursts in the first click_head_ms and the last click_tail_ms are
    ignored, and the preroll/tail never reach into them. A sound meant to be
    recorded that close to pressing or releasing the button is lost - the raw
    take still has it. Clicks anywhere else in the take are kept.

    min_floor keeps the threshold off zero on digitally silent input.
    Returns (trimmed int16 array, True) or (original, False) if nothing in the
    take ever crossed the threshold.
    """
    if data.ndim > 1:
        mono = data.mean(axis=1)
    else:
        mono = data

    rms, win = _rms_windows(mono, samplerate, window_ms)
    if rms.size == 0:
        return data, False

    floor = float(np.percentile(rms, floor_percentile))
    threshold = max(floor * threshold_mult, min_floor)

    def windows(ms):
        return max(1, int(round(ms / window_ms)))

    over, head_end = _drop_start_click(
        rms > threshold, windows(click_head_ms),
        windows(click_max_ms), windows(click_gap_ms))
    # The same check on the reversed mask finds the release click at the end
    reversed_over, tail_len = _drop_start_click(
        over[::-1], windows(click_tail_ms),
        windows(click_max_ms), windows(click_gap_ms))
    over = reversed_over[::-1]

    loud = _sustained(over, windows(min_run_ms))
    if loud.size == 0:
        return data, False

    start = int(loud[0] * win - samplerate * preroll_ms / 1000.0)
    end = int((loud[-1] + 1) * win + samplerate * tail_ms / 1000.0)
    start = max(0, start, head_end * win)
    end = min(len(data), end)
    if tail_len:
        end = min(end, (len(over) - tail_len) * win)
    if end - start < win:
        return data, False

    return apply_fades(data[start:end], samplerate, fade_in_ms, fade_out_ms), True


def apply_gain(data, gain):
    """Multiply by a linear gain, clipping at full scale.

    int16 is multiplied in float32 - doing it in place on the int array wraps
    around instead of clipping, which turns a loud sample into noise.
    """
    if gain == 1.0:
        return np.asarray(data, dtype=np.int16)
    out = data.astype(np.float32) * float(gain)
    np.clip(out, -INT16_MAX, INT16_MAX - 1, out=out)
    return out.astype(np.int16)


def normalize(data, target_dbfs=-3.0, max_gain_db=30.0):
    """Peak normalise to target_dbfs. Returns (data, gain_db_applied).

    Peak rather than RMS/LUFS: these are one shot percussive samples, and peak
    is what decides whether stacking six of them clips the mixer.

    max_gain_db is the point of the cap - a take that is nothing but room noise
    would otherwise be lifted 40dB into a hiss wall.
    """
    if len(data) == 0:
        return np.asarray(data, dtype=np.int16), 0.0

    peak = float(np.max(np.abs(data.astype(np.int32))))
    if peak <= 0.0:
        return np.asarray(data, dtype=np.int16), 0.0

    target = INT16_MAX * (10.0 ** (target_dbfs / 20.0))
    gain = target / peak
    gain_db = 20.0 * np.log10(gain)
    if gain_db > max_gain_db:
        gain_db = max_gain_db
        gain = 10.0 ** (max_gain_db / 20.0)
    if abs(gain_db) < 0.1:
        return np.asarray(data, dtype=np.int16), 0.0

    return apply_gain(data, gain), float(gain_db)


## HOUSEKEEPING ##

def delete_sample(path, raw_path=None):
    """Remove a sample and, if given, the raw original behind it."""
    removed = []
    for p in (path, raw_path):
        if p and os.path.isfile(p):
            try:
                os.remove(p)
                removed.append(p)
            except OSError as e:
                print("Could not delete {0}: {1}".format(p, e))
    return removed


def wav_duration(path):
    """Length in seconds, from the wav header only - no sample data is read,
    so this is cheap enough to call while drawing a file list."""
    try:
        w = wave.open(path, 'rb')
    except Exception:
        return 0.0
    try:
        rate = w.getframerate()
        return w.getnframes() / float(rate) if rate else 0.0
    finally:
        w.close()
