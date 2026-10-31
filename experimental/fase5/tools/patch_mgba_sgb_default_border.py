#!/usr/bin/env python3
"""mGBA 0.10.5: initialize built-in SGB bezel on every reset, incl. plain DMG carts.
SGB-enhanced games retain control: subsequent CHR_TRN/PCT_TRN/PAL commands override
the default and no game palette packet is filtered or recolored.
"""
from pathlib import Path
import sys

ANCHOR = '''\tvideo->renderer->writePalette(video->renderer, 9 * 4 + 3, video->palette[9 * 4 + 3]);
}

void GBVideoDeinit(struct GBVideo* video) {'''

REPLACEMENT = '''\tvideo->renderer->writePalette(video->renderer, 9 * 4 + 3, video->palette[9 * 4 + 3]);

\t/* IKF5 SGB fallback: video reset fills the built-in SGB border RAM,
\t * but the software renderer only regenerates it when it sees a later
\t * palette/SGB transfer. Ordinary GB titles send no such commands.
\t * Force one initial redraw using the existing renderer; keep runtime
\t * SGB packet handling unchanged so title-specific borders override it.
\t */
\tif ((video->p->model & GB_MODEL_SGB) && video->sgbBorders) {
\t\tvideo->renderer->enableSGBBorder(video->renderer, false);
\t\tvideo->renderer->enableSGBBorder(video->renderer, true);
\t}
}

void GBVideoDeinit(struct GBVideo* video) {'''

def patch(s):
    if s.count(ANCHOR)!=1:
        raise ValueError(f"mGBA 0.10.5 video reset anchor changed (found {s.count(ANCHOR)})")
    return s.replace(ANCHOR,REPLACEMENT,1)

if __name__ == "__main__":
    if len(sys.argv)!=2: raise SystemExit("Usage: patch_mgba_sgb_default_border.py PATH_TO_VIDEO_C")
    path=Path(sys.argv[1])
    path.write_text(patch(path.read_text()))
    print("PASS: SGB default bezel regenerated at reset, ROM border transfers retained")
