#!/usr/bin/env python3
"""No-ROM test of native termination handlers and Hakchi .7z reset relay.

Tests a real POSIX signal reaching the generated native C handler and a real
SIGTERM sent to the shell wrapper while a fake native process is running.
The fake game/extractor never contains or executes a commercial ROM.
"""
from pathlib import Path
import os
import signal
import subprocess
import sys
import tempfile
import time

native = Path(sys.argv[1]).read_text("utf-8")
wrapper = Path(sys.argv[2]).read_text("utf-8")

assert "while (!g_shutdown_requested && !g_swap_failed && !ik_exit_signal)" in native
assert native.index("if (game_loaded) ik_sram_flush(1);") < native.index(
    "if (game_loaded && core_retro_unload_game)"
), "flush MUST precede cart unload"
assert "ik_exit_handlers_install()" in native
assert 'ik_exit_signal ? ik_exit_signal_name' in native

start = native.index("/* Clover may terminate")
end = native.index("\nint main(int argc, char **argv)\n{", start)
signal_impl = native[start:end]
with tempfile.TemporaryDirectory(prefix="ikcore-reset-test-") as tmp:
    root = Path(tmp)
    test_c = root / "signal_test.c"
    test_exe = root / "signal_test"
    test_c.write_text(r'''
#define _GNU_SOURCE
#include <signal.h>
#include <stdio.h>
#include <string.h>
''' + signal_impl + r'''
int main(void) {
    if (!ik_exit_handlers_install()) return 1;
    if (raise(SIGTERM) != 0 || ik_exit_signal != SIGTERM) return 2;
    if (strcmp(ik_exit_signal_name((int)ik_exit_signal), "SIGTERM")) return 3;
    /* A second signal must not discard the first termination reason. */
    if (raise(SIGINT) != 0 || ik_exit_signal != SIGTERM) return 4;
    puts("NATIVE SIGNAL: PASS");
    return 0;
}
''', encoding="utf-8")
    subprocess.run(["gcc", "-std=gnu11", "-O2", "-Wall", "-Wextra",
                    "-Werror", str(test_c), "-o", str(test_exe)], check=True)
    subprocess.run([str(test_exe)], check=True)

    base = root / "hakchi"
    base.mkdir()
    state = root / "state"
    events = root / "events.log"
    mock_core = root / "mock-native"
    mock_extract = root / "mock-7za"
    archive = base / "Guerreras_magicas.sfc.7z"
    archive.write_bytes(b"synthetic Hakchi archive placeholder")

    mock_extract.write_text(r'''#!/usr/bin/env python3
import pathlib, sys
output = next((x[2:] for x in sys.argv if x.startswith("-o")), None)
assert output
# Fake SGBPACK1: footer magic exactly 256 bytes from EOF.
(pathlib.Path(output) / "game.sfc").write_bytes(b"\0" * 8192 +
                                                b"SGBPACK1" + b"\0" * 248)
''', encoding="utf-8")
    mock_extract.chmod(0o755)
    mock_core.write_text(r'''#!/bin/sh
trap 'echo "native:term" >> "$IKCORE_TEST_EVENTS"; sleep 0.2; echo "native:clean" >> "$IKCORE_TEST_EVENTS"; exit 0' TERM
echo "native:running" >> "$IKCORE_TEST_EVENTS"
while :; do
    sleep 0.05
done
''', encoding="utf-8")
    mock_core.chmod(0o755)

    test_wrapper = wrapper.replace(
        "CORE=/usr/lib/ikcore-standalone/ikcore-standalone-native",
        "CORE=" + str(mock_core)
    ).replace(
        "P7ZIP=/usr/lib/ikcore-standalone/7za", "P7ZIP=" + str(mock_extract)
    ).replace(
        "P7LIB=/usr/lib/ikcore-standalone/lib", "P7LIB=" + str(root)
    ).replace(
        "TMPBASE=/var/lib/hakchi/sgb-native-test", "TMPBASE=" + str(state)
    ).replace("__IKCORE_RUN_NUMBER__", "5")
    assert test_wrapper != wrapper
    wrapper_file = root / "test-wrapper.sh"
    wrapper_file.write_text(test_wrapper, encoding="utf-8")
    wrapper_file.chmod(0o755)
    subprocess.run(["sh", "-n", str(wrapper_file)], check=True)

    env = dict(os.environ, IKCORE_TEST_EVENTS=str(events))
    # The Hakchi entry is a bare .sfc, but on-device only the .sfc.7z exists.
    proc = subprocess.Popen(
        [str(wrapper_file), str(base / "Guerreras_magicas.sfc")],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    try:
        end_time = time.monotonic() + 5.0
        while time.monotonic() < end_time:
            if events.exists() and "native:running" in events.read_text():
                break
            if proc.poll() is not None:
                raise RuntimeError("wrapper exited before game was running")
            time.sleep(0.03)
        else:
            raise RuntimeError("mock game never started")

        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5.0)
        text = events.read_text()
        assert "native:term" in text, text
        assert "native:clean" in text, text
        leftovers = list(state.glob("ikcore-archive.*"))
        assert not leftovers, f"temporary archive files not cleaned: {leftovers}"
        log = (state / "ikcore-standalone-5-wrapper.log").read_text()
        assert "señal-recibida=1" in log, log
        print("WRAPPER TERM -> NATIVE -> SRAM CLEANUP WAIT -> REMOVE TEMP: PASS")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5.0)
