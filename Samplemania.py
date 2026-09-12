"""Samplemania launcher - this is the file EmulationStation starts.

The app itself (lib/app.py) runs in a child process. If it crashes, or hangs
and gets killed by its watchdog, it is started again straight away and comes
back on the preset and page it was on - during a performance a problem costs
a few seconds instead of the show. Quitting through the menu (Exit) ends the
app normally and the launcher with it.

Helper modules live in lib/ so this is the only .py EmulationStation lists.
"""

import os
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(ROOT, "lib", "app.py")

# Give up if the app fails this often within RESTART_WINDOW seconds - then
# something is broken for good (e.g. no controller) and looping won't help.
MAX_RESTARTS = 5
RESTART_WINDOW = 60.0

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(ROOT, "lib"))
import config


def log(message):
    line = "{0} LAUNCHER {1}".format(time.strftime("%Y-%m-%d %H:%M:%S"), message)
    print(line)
    try:
        with open(config.LOG_PATH, "a") as f:
            f.write(line + "\n")
    except (IOError, OSError):
        pass


def main():
    child = [None]

    def stop_child(signum, frame):
        if child[0] is not None and child[0].poll() is None:
            child[0].terminate()
            try:
                child[0].wait(3)
            except subprocess.TimeoutExpired:
                child[0].kill()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop_child)

    failures = []
    env = dict(os.environ)
    while True:
        try:
            os.remove(config.QUIT_MARKER)
        except OSError:
            pass

        # -B: no __pycache__ folders in lib/
        child[0] = subprocess.Popen([sys.executable, "-B", APP], env=env)
        try:
            code = child[0].wait()
        except KeyboardInterrupt:
            stop_child(None, None)

        if code == 0 or os.path.exists(config.QUIT_MARKER):
            if code != 0:
                log("app exited with code {0} while quitting - not restarting".format(code))
            return 0

        now = time.time()
        failures = [t for t in failures if now - t < RESTART_WINDOW] + [now]
        log("app exited with code {0} ({1} failures in the last {2:.0f}s)".format(
            code, len(failures), RESTART_WINDOW))
        if len(failures) > MAX_RESTARTS:
            log("giving up")
            return 1

        log("restarting")
        env["SAMPLEMANIA_RESTART"] = "1"
        time.sleep(0.5)


if __name__ == "__main__":
    sys.exit(main())
