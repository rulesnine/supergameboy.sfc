#!/usr/bin/env python3
"""Minimal ABI-safe packet observer for a pinned mGBA GB core.

Copyright 2026 Ik Core project contributors.
Original modified file src/gb/video.c is from mGBA under MPL 2.0.
No mGBA sources are vendored here; CI checks out pinned upstream.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2: raise SystemExit("usage: patch_mgba_sgb_bridge.py /path/to/mgba")
p=Path(sys.argv[1])/"src/gb/video.c"
s=p.read_text(encoding="utf8")
include_anchor='#include <mgba/internal/gb/video.h>'
if s.count(include_anchor)!=1:
    raise RuntimeError(f"mGBA pinned source changed: {include_anchor!r} count={s.count(include_anchor)}")
new_includes=include_anchor+"""

// IKCORE_MGBA_PACKET_BRIDGE: observe *completed* SGB commands; never
// modify the upstream GB core's decoding or emulated cycle order.
// Weak export allows a standalone libretro GB-core smoke test with no
// audio/SGB frontend, and later a single Ik Core host bridge implementation.
#if defined(__GNUC__)
extern void ikcore_sgb_packet_hook(unsigned command, const unsigned char *data,
                                   unsigned bytes) __attribute__((weak));
#endif
"""
s=s.replace(include_anchor,new_includes,1)
anchor='''\tif (video->sgbCommandHeader & 7) {
\t\treturn;
\t}
\tswitch (video->sgbCommandHeader >> 3) {'''
if s.count(anchor)!=1:
    raise RuntimeError(f"mGBA SGB multipart completion anchor changed, found {s.count(anchor)}")
replacement='''\tif (video->sgbCommandHeader & 7) {
\t\treturn;
\t}
#if defined(__GNUC__)
\t// Forward assembled command before mGBA handles or ignores it.
\t// The bridge must queue SOUND/SOU_TRN for the Ik Core SPC thread,
\t// and PAL/ATTR/CHR/PCT for the one chosen SGB renderer.
\tif (ikcore_sgb_packet_hook)
\t\tikcore_sgb_packet_hook((unsigned)(video->sgbCommandHeader >> 3),
\t\t                       video->sgbPacketBuffer,
\t\t                       (unsigned)video->sgbBufferIndex * 16u);
#endif
\tswitch (video->sgbCommandHeader >> 3) {'''
s=s.replace(anchor,replacement,1)
p.write_text(s,encoding="utf8")
print("IKCORE_MGBA_PACKET_BRIDGE installed at completed SGB packet boundary")
