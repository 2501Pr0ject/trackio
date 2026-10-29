import os
import re
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX SIGTERM semantics only"
)

CHILD = textwrap.dedent(
    """
    import time

    import trackio
    from trackio import utils

    trackio.init(project="sigterm-test", name="run")
    print(f"ready {utils.MEDIA_DIR}", flush=True)
    for step in range(100_000):
        print(f"step {step}", flush=True)
        time.sleep(0.01)
    """
)


def test_sigterm_flushes_console_capture(tmp_path):
    env = {
        **os.environ,
        "TRACKIO_DIR": str(tmp_path),
        "HF_HOME": str(tmp_path / "hf"),
        "TRACKIO_CAPTURE_CONSOLE": "1",
    }
    proc = subprocess.Popen(
        [sys.executable, "-c", CHILD],
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )

    # trackio.init() prints its own lines first; wait for ours.
    media_dir = None
    while media_dir is None:
        line = proc.stdout.readline()
        assert line, "child exited before becoming ready"
        if line.startswith("ready "):
            media_dir = Path(line.split(" ", 1)[1].strip())
    assert str(tmp_path) in str(media_dir), "child is not using the temp dir"

    # Well below the 10 s console flush interval: without a SIGTERM
    # handler, the tail of the console is never written.
    time.sleep(2)
    proc.send_signal(signal.SIGTERM)
    out, _ = proc.communicate(timeout=60)

    assert proc.returncode == 128 + signal.SIGTERM

    printed = [line for line in out.splitlines() if line.startswith("step ")]
    assert printed, "child printed no steps"

    console_files = sorted(media_dir.glob("sigterm-test/run/console-*.log"))
    assert console_files, "no console file written"
    captured = re.findall(r"step \d+", console_files[-1].read_text())
    assert captured and captured[-1] == printed[-1]
