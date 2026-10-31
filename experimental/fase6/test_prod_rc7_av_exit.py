#!/usr/bin/env python3
"""RC7 no-ROM regression for original SGB BIOS video/audio and Clover RESET."""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess, signal, os, time
root=Path(__file__).resolve().parents[2]
host=(root/"experimental/fase6/ik_spc_host.c").read_text()
header=(root/"experimental/fase6/ik_spc_host.h").read_text()
display=(root/"experimental/fase6/ik_prod_loading_screen.inc").read_text()
patch=(root/"experimental/fase6/patch_prod_loading_screen.py").read_text()
graceful=(root/"experimental/fase6/patch_prod_graceful_exit.py").read_text()
for token in ["ik_f6_spc_set_boot_audio","ik_f6_spc_set_boot_cancel"]:
    assert token in host and token in header and token in patch,token
assert "g_prod_boot_audio((const int16_t*)p,frames)" in host
assert "g_prod_boot_video(g_prod_boot_frame,g_prod_boot_frames)" in host
assert "g_prod_boot_frames%12u" not in host
assert "target_fps=60.0" in host
assert "cap_hz=60.10" in display
assert "ik_rc7_boot_cancel(void)" in graceful
assert "ik_rc6_exit_signal" in graceful

shell=(root/"experimental/fase6/ikcore-rc7-launcher.sh").read_text()
assert "case \"$rc\" in" in shell
assert "129|130|131|143)" in shell
assert "watchdog" in shell
with TemporaryDirectory() as d:
    p=Path(d);events=p/"events.txt"
    fakecore=p/"core.sh";extractor=p/"extract.sh";archive=p/"test.sfc.7z"
    archive.write_bytes(b"fake")
    extractor.write_text(
      '#!/bin/sh\nfor a in "$@"; do case "$a" in -o*) dir=$(echo "$a" | cut -c3-);; esac; done\n'
      'printf demo > "$dir/test.sfc"\n')
    extractor.chmod(0o755)
    fakecore.write_text('#!/bin/sh\necho "start:$$:$*" >> "$RC7_EVENTS"\n'
      'trap \'echo clean >> "$RC7_EVENTS"; exit 0\' TERM\n'
      'while :; do sleep 0.05; done\n')
    fakecore.chmod(0o755)
    runner=p/"launcher.sh"
    runner.write_text(shell.replace(
       "CORE=/usr/lib/ikcore-sgb-rc7/ikcore-sgb-rc7-n2",
       "CORE="+str(fakecore)).replace(
       "EXTRACTOR=/usr/lib/ikcore-sgb-rc7/7zr",
       "EXTRACTOR="+str(extractor)))
    runner.chmod(0o755)
    subprocess.run(["sh","-n",str(runner)],check=True)
    env=dict(os.environ,RC7_EVENTS=str(events))
    child=subprocess.Popen([str(runner),str(archive),"--save-on-quit",str(p/"save.state")],
       env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            if events.exists() and "start:" in events.read_text():break
            if child.poll() is not None:raise AssertionError("launcher quit unexpectedly")
            time.sleep(.025)
        else:raise AssertionError("child did not start")
        assert "--save-on-quit" in events.read_text()
        child.send_signal(signal.SIGTERM)
        rc=child.wait(timeout=9)
        assert rc==0,f"Clover signal must return success: rc={rc}"
        assert "clean" in events.read_text(),"native child never received SIGTERM"
    finally:
        if child.poll() is None:child.kill();child.wait()
print("PASS: real Nintendo SNES video each frame, BIOS PCM, exit cancellation, Clover RESET=0, save flags")
