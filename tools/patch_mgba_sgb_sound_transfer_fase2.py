#!/usr/bin/env python3
"""Phase 2 SGB SOUND/SOU_TRN bridge into the pinned mGBA GB video pipeline.

Apply AFTER tools/patch_mgba_sgb_bridge.py and BEFORE compiling mGBA.
Modifications only add weak callouts and allow existing renderer to stage the
previously stubbed SOU_TRN LCD transfer; no GB timing/palette emulation replaced.

mGBA upstream files remain MPL-2.0.
"""
import sys
from pathlib import Path
if len(sys.argv)!=2:
    raise SystemExit("usage: patch_mgba_sgb_sound_transfer_fase2.py /path/to/mgba")
root=Path(sys.argv[1])
v=root/"src/gb/video.c"
r=root/"src/gb/renderers/software.c"
video=v.read_text(encoding="utf8")
render=r.read_text(encoding="utf8")

def exactly(text, old, new, desc):
    count=text.count(old)
    if count!=1:
        raise RuntimeError(f"{desc}: expected one anchor, got {count}")
    return text.replace(old,new,1)

# Capture full SGB packet after mGBA has assembled it, before dispatch.
anchor="""#if defined(__GNUC__)
extern void ikcore_sgb_packet_hook(unsigned command, const unsigned char *data,
                                   unsigned bytes) __attribute__((weak));
#endif"""
insert=anchor+"""

#if defined(__GNUC__)
extern void ikcore_sgb_sound_packet_hook(unsigned command,
                                        const unsigned char *data,
                                        unsigned bytes) __attribute__((weak));
extern void ikcore_sgb_lcd_row_hook(unsigned y, const unsigned char *row,
                                   unsigned width) __attribute__((weak));
#endif"""
video=exactly(video,anchor,insert,"additional sound and LCD callbacks")
old="""#endif
\tswitch (video->sgbCommandHeader >> 3) {
\tcase SGB_PAL01:"""
new="""#endif
#if defined(__GNUC__)
\tif (ikcore_sgb_sound_packet_hook)
\t\tikcore_sgb_sound_packet_hook(
\t\t    (unsigned)(video->sgbCommandHeader >> 3),
\t\t    video->sgbPacketBuffer, (unsigned)video->sgbBufferIndex * 16u);
#endif
\tswitch (video->sgbCommandHeader >> 3) {
\tcase 0x08: // SOUND: handled by optional SNES audio bridge.
\t\treturn;
\tcase 0x09: // SOU_TRN: unlike stock mGBA, initiate 2bpp LCD transfer.
#if defined(__GNUC__)
\t\tif (ikcore_sgb_lcd_row_hook) break;
#endif
\t\treturn; // no host sink: maintain original unsupported behavior.
\tcase SGB_PAL01:"""
video=exactly(video,old,new,"SGB command sound dispatch")

anchor="#include <mgba/internal/gb/renderers/software.h>"
new=anchor+"""

#if defined(__GNUC__)
extern void ikcore_sgb_lcd_row_hook(unsigned y, const unsigned char *row,
                                   unsigned width) __attribute__((weak));
#endif"""
render=exactly(render,anchor,new,"software renderer optional row tap")
anchor="""\tif (softwareRenderer->sgbTransfer == 1) {
\t\tsize_t offset = 2 * ((y & 7) + (y >> 3) * GB_VIDEO_HORIZONTAL_PIXELS);"""
repl="""\tif (softwareRenderer->sgbTransfer == 1) {
#if defined(__GNUC__)
\t\t// The 2bpp tokens in row[] are the exact source for CHR/PAL/ATTR
\t\t// transfer. Observe SOU_TRN without converting to RGB or touching VRAM.
\t\tif ((softwareRenderer->sgbCommandHeader >> 3) == 0x09 &&
\t\t    ikcore_sgb_lcd_row_hook)
\t\t\tikcore_sgb_lcd_row_hook((unsigned)y, softwareRenderer->row,
\t\t\t                         GB_VIDEO_HORIZONTAL_PIXELS);
#endif
\t\tsize_t offset = 2 * ((y & 7) + (y >> 3) * GB_VIDEO_HORIZONTAL_PIXELS);"""
render=exactly(render,anchor,repl,"LCD row during transfer frame")
anchor="""\t\tcase SGB_ATTR_TRN:
\t\t\t++softwareRenderer->sgbTransfer;"""
repl="""\t\tcase 0x09: // SOU_TRN: advance the same post-packet transfer frame as PAL_TRN.
#if defined(__GNUC__)
\t\t\tif (!ikcore_sgb_lcd_row_hook) break;
#endif
\t\t\t// Fall through.
\t\tcase SGB_ATTR_TRN:
\t\t\t++softwareRenderer->sgbTransfer;"""
render=exactly(render,anchor,repl,"advance SOU_TRN transfer state")
# Safety verification: one mGBA video command hook, one transfer-line hook.
assert video.count("ikcore_sgb_sound_packet_hook(")==2
assert render.count("ikcore_sgb_lcd_row_hook(")==2
v.write_text(video,encoding="utf8")
r.write_text(render,encoding="utf8")
print("IKCORE phase2 SOUND packet + SOU_TRN raw 2bpp LCD frame taps applied.")
