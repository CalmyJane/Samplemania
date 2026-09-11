"""Run this on the PiBoy to check the recording setup:

    python3 /home/pi/RetroPie/roms/python/check_audio.py

Lists the audio devices, shows which one Samplemania would pick, and records a
2 second test take so you can see whether the mic is actually producing level.
"""

import sys

import config


def main():
    print("Sample dir      : {0}".format(config.SAMPLE_DIR))
    print("Recordings dir  : {0}".format(config.RECORDINGS_DIR))
    try:
        config.ensure_dirs()
        print("Dirs            : OK")
    except Exception as e:
        print("Dirs            : FAILED - {0}".format(e))

    try:
        import numpy as np
    except ImportError:
        print("\nnumpy is missing:  sudo apt install python3-numpy")
        return 1

    import recorder
    if not recorder.available():
        print("\nsounddevice is missing: {0}".format(recorder.SD_ERROR))
        print("  sudo apt install python3-sounddevice libportaudio2")
        return 1

    import sounddevice as sd
    print("\n--- devices ---")
    print(sd.query_devices())

    index, name = recorder.find_input_device(config.INPUT_DEVICE)
    if index is None:
        print("\nNo usable input device: {0}".format(name))
        return 1
    print("\nSamplemania will record from: [{0}] {1}".format(index, name))
    print("(to force a different one, set INPUT_DEVICE in config.py to that "
          "index or a piece of the name)")

    print("\nRecording 2 seconds - say something...")
    rec = recorder.Recorder(max_seconds=2.0)
    if not rec.start():
        print("Could not open the device: {0}".format(rec.error))
        return 1

    import time
    while rec.recording and not rec.full:
        time.sleep(0.1)
        bars = int(rec.peak * 40)
        sys.stdout.write("\r[{0:<40}] peak {1:5.1f}%".format("#" * bars, rec.peak * 100))
        sys.stdout.flush()
    data = rec.stop()
    print("")

    if data is None or len(data) == 0:
        print("Nothing captured.")
        return 1

    import sample_edit
    print("Captured {0:.2f}s, peak {1:.1f} dBFS{2}".format(
        len(data) / float(rec.samplerate),
        sample_edit.peak_dbfs(data),
        "  CLIPPED - turn the mic gain down" if rec.clipped else ""))
    if rec.overruns:
        print("{0} buffer overruns - if this is high, raise blocksize in "
              "recorder.Recorder".format(rec.overruns))

    trimmed, did = sample_edit.smart_trim(data, rec.samplerate)
    print("Auto-trim would cut it to {0:.2f}s{1}".format(
        len(trimmed) / float(rec.samplerate), "" if did else "  (nothing over the noise floor)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
