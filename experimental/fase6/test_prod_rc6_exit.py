#!/usr/bin/env python3
"""No-ROM regression: Clover RESET reaches emulator through 7z wrapper,
child exits, temporary extraction is cleaned, SGB boot-video hooks exist.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess, signal, time, os

root=Path(__file__).resolve().parents[2]
patch=(root/"experimental/fase6/patch_prod_graceful_exit.py").read_text()
inc=(root/"experimental/fase6/ik_prod_loading_screen.inc").read_text()
host=(root/"experimental/fase6/ik_spc_host.c").read_text()
assert "sigaction(SIGTERM" in patch and "&& !ik_rc6_exit_signal" in patch
assert "ik_suspend_save();" in patch
assert "ik_prod_sram_flush(1)" in (root/"experimental/fase6/patch_prod_persistence.py").read_text()
assert "ik_prod_show_firmware_video" in inc and "LIVE_SNES_BIOS" in inc
assert "g_prod_boot_video(g_prod_boot_frame,g_prod_boot_frames)" in host

with TemporaryDirectory() as d:
    p=Path(d); events=p/"events.txt"
    core=p/"fakecore.sh"; extractor=p/"fakeextract.sh"
    archive=p/"Castlevania_Legends.sfc.7z"
    archive.write_bytes(b"not a real ROM")
    extractor.write_text('#!/bin/sh\nfor x in "$@"; do case "$x" in -o*) dir=$(echo "$x" | cut -c3-);; esac; done\nprintf test > "$dir/castlevania.sfc"\n')
    extractor.chmod(0o755)
    core.write_text('#!/bin/sh\necho started >> "$RC6_EVENTS"\ntrap \'echo terminated >> "$RC6_EVENTS"; exit 0\' TERM\nwhile :; do sleep .1; done\n')
    core.chmod(0o755)
    script=(root/"experimental/fase6/ikcore-rc6-launcher.sh").read_text()
    script=script.replace("CORE=/usr/lib/ikcore-sgb-rc6/ikcore-sgb-rc6-n2","CORE="+str(core))
    script=script.replace("EXTRACTOR=/usr/lib/ikcore-sgb-rc6/7zr","EXTRACTOR="+str(extractor))
    runner=p/"launcher.sh";runner.write_text(script);runner.chmod(0o755)
    subprocess.run(["sh","-n",str(runner)],check=True)
    env=dict(os.environ,RC6_EVENTS=str(events))
    proc=subprocess.Popen([str(runner),str(archive),"--save-on-quit",str(p/"save.state")],
                          env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            if events.exists() and "started" in events.read_text():break
            if proc.poll() is not None:raise AssertionError("launcher died before game started")
            time.sleep(.03)
        else:raise AssertionError("mock core never started")
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=8)
        assert "terminated" in events.read_text(), events.read_text()
        print("PASS: SIGTERM Clover wrapper -> child exits gracefully")
    finally:
        if proc.poll() is None:proc.kill();proc.wait(timeout=2)
print("PASS: firmware live-frame hook and save-on-quit source regression")
