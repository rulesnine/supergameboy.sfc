#!/usr/bin/env python3
"""Force SGB1 for any DMG-compatible cart, without breaking CGB-only cartridges.
mGBA 0.10.5's model choice and overrides may prefer DMG/CGB despite the
frontend's SGB option. This patch belongs ONLY to the experimental core.
"""
import sys
from pathlib import Path
ANCHOR = '''\tif (gb->model < GB_MODEL_CGB) {
\t\tmemcpy(gbcore->memoryBlocks, _GBMemoryBlocks, sizeof(_GBMemoryBlocks));'''
REPLACEMENT = '''\t/* IKF5 SGB1 policy: DMG-compatible cartridges (including ordinary GB
\t * titles) may run in the Super Game Boy. This preserves SGB-only
\t * accessories/game commands. A CGB-only game cannot run on a real SGB,
\t * so never force it into unsupported hardware.
\t */
\tif (gb->memory.rom && (GBValidModels(gb->memory.rom) & GB_MODEL_MGB)) {
\t\tgb->model = GB_MODEL_SGB;
\t}

\tif (gb->model < GB_MODEL_CGB) {
\t\tmemcpy(gbcore->memoryBlocks, _GBMemoryBlocks, sizeof(_GBMemoryBlocks));'''
def patch(s):
    if s.count(ANCHOR)!=1: raise ValueError("mGBA core reset model anchor not unique")
    return s.replace(ANCHOR,REPLACEMENT,1)
if __name__ == "__main__":
    if len(sys.argv)!=2: raise SystemExit("Usage: patch_mgba_sgb_force_model.py SRC_GB_CORE_C")
    file=Path(sys.argv[1]);file.write_text(patch(file.read_text()))
    print("PASS: SGB model for DMG-compatible games; CGB-only unchanged")
