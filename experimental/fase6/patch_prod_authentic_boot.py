#!/usr/bin/env python3
"""RC8: no artificial GAME BOY/CARGANDO splash, ever.
Keep the existing verified SGB custom PCT border handoff gate, but make
the BIOS pixels the ONLY visual output before the game is ready.
"""
from pathlib import Path
import sys
def patch(s):
    anchors={
        "    ik_prod_show_loading();":"    /* RC8: no artificial loading picture; show real SGB firmware video only. */",
        "    ik_f6_spc_set_boot_progress(ik_prod_loading_animate);":"    ik_f6_spc_set_boot_progress(NULL); /* no fabricated loading animation */",
        "                ik_prod_loading_animate(ik_prod_gate.frames);":"                (void)ik_prod_gate.frames; /* keep real firmware picture */"
    }
    for a,b in anchors.items():
        n=s.count(a)
        if n!=1:raise ValueError(f"expected exactly one RC8 handoff anchor {a!r}: {n}")
        s=s.replace(a,b,1)
    assert "ik_prod_show_firmware_video" in s
    assert "ik_f6_spc_set_boot_audio(audio_batch_cb)" in s
    assert "ik_f6_spc_set_boot_cancel(ik_rc7_boot_cancel)" in s
    return s
if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("patch_prod_authentic_boot.py FRONTEND.c")
    p=Path(sys.argv[1]);p.write_text(patch(p.read_text()))
    print("PASS: original SGB BIOS video only; synthetic CARGANDO disabled")
