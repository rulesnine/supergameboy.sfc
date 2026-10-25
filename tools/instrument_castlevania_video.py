#!/usr/bin/env python3
"""Experimental Ik Core SGB/PPU video trace. No gameplay, audio, or mask changes.

Runs AFTER tools/apply_sgbpack.py on pinned SuperSnes9x.
Records source GB framebuffer and composed SGB pane independently every 120
direct-mode frames, plus BIOS->direct handoff. No copyrighted ROM data.
"""
from pathlib import Path

p = Path("supersnes9x/sgb/sgb.cpp")
s = p.read_text(encoding="utf-8")
def once_scoped(source, anchor, replacement, label):
    count = source.count(anchor)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return source.replace(anchor, replacement, 1)

handoff_old = "\timpl_->ppu.hold_present_on_enable = false;\n\n\t// If the game's PCT already landed"
handoff_new = """\timpl_->ppu.hold_present_on_enable = false;
\t{
\t\tchar msg[256];
\t\tstd::snprintf(msg, sizeof msg,
\t\t\t"IKVID HANDOFF mode=%u setup=%u mask=%u LCDC=%02X LY=%u released=%u border_pct=%u",
\t\t\t(unsigned)impl_->host_bios_mode,
\t\t\t(unsigned)impl_->boot_setup_done,
\t\t\t(unsigned)impl_->sgb_state.mask_mode,
\t\t\t(unsigned)impl_->ppu.lcdc,
\t\t\t(unsigned)impl_->ppu.ly,
\t\t\t(unsigned)IsGBReleased(),
\t\t\t(unsigned)impl_->border_pct);
\t\tS9xMessage(S9X_INFO, S9X_ROM_INFO, msg);
\t}

\t// If the game's PCT already landed"""
s = once_scoped(s, handoff_old, handoff_new, "handoff video probe")

blit_start = s.find("void Emulator::BlitScreen(uint16_t *dest, uint32_t pitch_pixels)")
blit_end = s.find("void Emulator::BlitScreenGB(", blit_start)
if blit_start < 0 or blit_end < 0:
    raise RuntimeError("BlitScreen region not found")
region = s[blit_start:blit_end]
copy_anchor = "\tfor (uint32_t y = 0; y < SGB_BORDER_H; ++y)\n\t{\n\t\tuint16_t       *const drow = dest"
if region.count(copy_anchor) != 1:
    raise RuntimeError(f"BlitScreen copy anchor: {region.count(copy_anchor)}")
probe = """#ifdef IKCORE_SGB_VIDEO_TRACE
\t// Collect only once every 120 displayed SGB frames. Histograms distinguish
\t// blank Game Boy output from mask/compositor-induced black presentation.
\tstatic unsigned long ikvid_frames = 0;
\tif ((++ikvid_frames % 120UL) == 1UL)
\t{
\t\tunsigned shades[4] = {};
\t\tunsigned raw_nonzero = 0;
\t\tunsigned pane_nonzero = 0;
\t\tunsigned pane_different = 0;
\t\tconst uint16_t first_pane = staging[40 * SGB_BORDER_W + 48];
\t\tfor (unsigned y = 0; y < GB_SCREEN_HEIGHT; ++y)
\t\t{
\t\t\tfor (unsigned x = 0; x < GB_SCREEN_WIDTH; ++x)
\t\t\t{
\t\t\t\tconst unsigned idx = y * GB_SCREEN_WIDTH + x;
\t\t\t\t++shades[impl_->ppu.framebuffer[idx] & 3u];
\t\t\t\tif (impl_->ppu.raw_framebuffer[idx] & 3u) ++raw_nonzero;
\t\t\t\tconst uint16_t pix = staging[(y + 40) * SGB_BORDER_W + (x + 48)];
\t\t\t\tif (pix != 0) ++pane_nonzero;
\t\t\t\tif (pix != first_pane) ++pane_different;
\t\t\t}
\t\t}
\t\tchar msg[320];
\t\tstd::snprintf(msg, sizeof msg,
\t\t\t"IKVID FRAME n=%lu mask=%u LCDC=%02X LY=%u setup=%u "
\t\t\t"BIOS=%u shade=%u,%u,%u,%u rawNZ=%u paneNZ=%u paneDiff=%u "
\t\t\t"pal0=%04X pct=%u",
\t\t\tikvid_frames,
\t\t\t(unsigned)impl_->sgb_state.mask_mode,
\t\t\t(unsigned)impl_->ppu.lcdc,
\t\t\t(unsigned)impl_->ppu.ly,
\t\t\t(unsigned)impl_->boot_setup_done,
\t\t\t(unsigned)impl_->BiosMode(),
\t\t\tshades[0], shades[1], shades[2], shades[3],
\t\t\traw_nonzero, pane_nonzero, pane_different,
\t\t\t(unsigned)impl_->sgb_state.active[0].colors[0],
\t\t\t(unsigned)impl_->border_pct);
\t\tS9xMessage(S9X_INFO, S9X_ROM_INFO, msg);
\t}
#endif

"""
region=region.replace(copy_anchor,probe+copy_anchor,1)
s=s[:blit_start]+region+s[blit_end:]
p.write_text(s,encoding="utf-8")
print("IKVID trace inserted: handoff state + framebuffer/pane sample every 120 frames.")
