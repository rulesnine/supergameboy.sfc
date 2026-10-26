#!/usr/bin/env python3
"""Apply sound-program LCD capture hooks to pinned mGBA core.

Run AFTER tools/patch_mgba_sgb_bridge.py and BEFORE mGBA compilation.
All hooks are weak: upstream mGBA standalone remains functional without Ik Core.
The patch only observes existing software-renderer rows and frame boundaries.
Requires software GB PPU (not a GLSL/GPU renderer).
mGBA's existing decoder drops unsupported SOU_TRN before writeSGBPacket(),
therefore the sound hook must be at GBVideoWriteSGBPacket() completion,
not at GBVideoSoftwareRendererWriteSGBPacket().
"""
from pathlib import Path
import sys
if len(sys.argv)!=2: raise SystemExit("usage: patch_mgba_sou_trn_capture.py /path/to/mgba")
root=Path(sys.argv[1])
video=root/"src/gb/video.c"
software=root/"src/gb/renderers/software.c"
v=video.read_text()
s=software.read_text()
def rep(data,old,new,what):
    if data.count(old)!=1:
        raise RuntimeError(f"{what}: expected one anchor, found {data.count(old)}")
    return data.replace(old,new,1)
v=rep(v,'#include <mgba/internal/gb/video.h>',
r'''#include <mgba/internal/gb/video.h>
// IKCORE_SOU_TRN_FASE2: optional host observer, never alters mGBA state.
#if defined(__GNUC__)
extern void ikcore_sgb_transfer_command_hook(unsigned cmd) __attribute__((weak));
extern void ikcore_sgb_transfer_reset_hook(void) __attribute__((weak));
#endif''',"SGB video.h")
v=rep(v,"void GBVideoReset(struct GBVideo* video) {\n",
r'''void GBVideoReset(struct GBVideo* video) {
#if defined(__GNUC__)
    if (ikcore_sgb_transfer_reset_hook)
        ikcore_sgb_transfer_reset_hook();
#endif
''',"video reset")
anchor=r'''		if (ikcore_sgb_packet_hook)
			ikcore_sgb_packet_hook((unsigned)(video->sgbCommandHeader >> 3),
			                       video->sgbPacketBuffer,
			                       (unsigned)video->sgbBufferIndex * 16u);
#endif
	switch (video->sgbCommandHeader >> 3) {'''
replacement=r'''		if (ikcore_sgb_packet_hook)
			ikcore_sgb_packet_hook((unsigned)(video->sgbCommandHeader >> 3),
			                       video->sgbPacketBuffer,
			                       (unsigned)video->sgbBufferIndex * 16u);
		// SOU_TRN never reaches software renderer's writeSGBPacket(),
		// since mGBA doesn't currently implement SGB's SNES audio upload.
		if (ikcore_sgb_transfer_command_hook)
			ikcore_sgb_transfer_command_hook((unsigned)(video->sgbCommandHeader >> 3));
#endif
	switch (video->sgbCommandHeader >> 3) {'''
v=rep(v,anchor,replacement,"fully assembled SOU_TRN command observer")

s=rep(s,'#include <mgba/internal/gb/renderers/software.h>',
r'''#include <mgba/internal/gb/renderers/software.h>
// IKCORE_SOU_TRN_FASE2: software PPU 2-bit row and completed-frame observer.
#if defined(__GNUC__)
extern void ikcore_sgb_transfer_scanline_hook(int y,const uint16_t *row,
                                              unsigned width) __attribute__((weak));
extern void ikcore_sgb_transfer_frame_hook(void) __attribute__((weak));
#endif''',"software include")
s=rep(s,r'''	softwareRenderer->currentWx = 0;

	if (softwareRenderer->sgbTransfer == 1) {''',
r'''	softwareRenderer->currentWx = 0;
#if defined(__GNUC__)
	if (ikcore_sgb_transfer_scanline_hook && (softwareRenderer->model & GB_MODEL_SGB))
		ikcore_sgb_transfer_scanline_hook(y,softwareRenderer->row,
		                                 GB_VIDEO_HORIZONTAL_PIXELS);
#endif

	if (softwareRenderer->sgbTransfer == 1) {''',"software scanline hook")
s=rep(s,r'''static void GBVideoSoftwareRendererFinishFrame(struct GBVideoRenderer* renderer) {
	struct GBVideoSoftwareRenderer* softwareRenderer = (struct GBVideoSoftwareRenderer*) renderer;

	if (softwareRenderer->temporaryBuffer) {''',
r'''static void GBVideoSoftwareRendererFinishFrame(struct GBVideoRenderer* renderer) {
	struct GBVideoSoftwareRenderer* softwareRenderer = (struct GBVideoSoftwareRenderer*) renderer;
#if defined(__GNUC__)
	if (ikcore_sgb_transfer_frame_hook && (softwareRenderer->model & GB_MODEL_SGB))
		ikcore_sgb_transfer_frame_hook();
#endif

	if (softwareRenderer->temporaryBuffer) {''',"software frame hook")
video.write_text(v)
software.write_text(s)
print("IKCORE_SOU_TRN_FASE2 video command, reset, 160x144 row, frame complete hooks installed")
