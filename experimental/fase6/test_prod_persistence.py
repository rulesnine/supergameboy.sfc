#!/usr/bin/env python3
"""Fail fast if RC5 loses Hakchi flags, PNG capture or GB SRAM again.
The real frontend is cross-compiled in the following ARMv7 workflow step.
"""
from pathlib import Path
import importlib.util
import subprocess

root=Path(__file__).resolve().parents[2]
script=root/"experimental/fase6/patch_prod_persistence.py"
spec=importlib.util.spec_from_file_location("persist_patch",script)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
s=m.adapted_suspend()
assert '"IKCSUSP2"' in s
assert 'ik_susp_get32(h+12)!=2' in s
assert 'ik_susp_le32(h+12,2)' in s
assert 'ik_suspend_maybe_restore(void)' in s
assert 'core_retro_unserialize(ik_suspend_pending,ik_suspend_pending_size)' in s
assert 'ik_susp_png_write(ik_suspend_png)' in s
assert 'existing legacy/unknown file protected' in s
assert 'ik_suspend_framebuffer' in s
assert 'SGB v11 only' not in s
b=(root/"experimental/fase6/ik_prod_sram.inc").read_text()
assert 'RETRO_MEMORY_SAVE_RAM' in b
assert 'ik_prod_sram_flush(int force)' in b
assert 'ik_prod_sram_rebase(void)' in b
assert 'IK_PROD_SAVE_DIR' in b
assert '/var/lib/hakchi/ikcore-saves/%s.srm' in b
q=(root/"experimental/fase6/ikcore-quick-launcher.sh")
subprocess.run(["sh","-n",str(q)],check=True)
v=q.read_text()
assert 'set -- "$GAME" "$@"' in v
assert 'IKF6_ORIGINAL_ARCHIVE' in v
assert '--save-on-quit' in v
print("PASS: mGBA state ABI v2, original PNG, GB SRAM, backup isolation, Clover args")
