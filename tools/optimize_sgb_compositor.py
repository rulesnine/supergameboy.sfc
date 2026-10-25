#!/usr/bin/env python3
"""Experimental lossless optimization for Ik Core #42 NES Mini SGB compositor.

Runs AFTER apply_sgbpack.py and fix_sgb_lcd_palette_transfers.py.
No changes to the GB CPU, PPU, SGB commands/masks, SPC700/DSP, or ALSA.
Only the direct-mode full-color SGB frame blit receives a branch that:
  * caches the stable border's BGR555->host converted pixels per border version,
  * computes four post-correction host colors once per SGB attribute tile,
  * overlays the same source GB 2-bit shades directly on the host frame.
All BIOS-mode, pre-border, CGB, and DMG-palette fallbacks remain unchanged.
"""
from pathlib import Path

p = Path("supersnes9x/sgb/sgb.cpp")
s = p.read_text(encoding="utf-8")

def one(old, new, title):
    global s
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f"{title}: expected one match, got {n}")
    s = s.replace(old, new, 1)

field_anchor = """\tuint16_t    perf_stable_border[SGB_BORDER_W * SGB_BORDER_H] = {};
\tbool        perf_stable_border_valid = false;"""
field_new = field_anchor + """
#ifdef IKCORE_SGB_COMPOSITOR_FAST
\t// Host-native preconverted immutable border, invalidated by border-plane
\t// transactions or GB cartridge reset. Saves 57K pixel format conversions
\t// per frame; writes to the live Game Boy pane are always dynamic.
\tuint16_t    perf_host_border[SGB_BORDER_W * SGB_BORDER_H] = {};
\tuint32_t    perf_host_border_version = ~0u;
#endif"""
one(field_anchor, field_new, "border cache state")

reset_anchor = """\timpl_->perf_stable_border_valid = false;
#endif
\timpl_->sgbc_trn.Reset();"""
reset_new = """\timpl_->perf_stable_border_valid = false;
#ifdef IKCORE_SGB_COMPOSITOR_FAST
\timpl_->perf_host_border_version = ~0u;
#endif
#endif
\timpl_->sgbc_trn.Reset();"""
one(reset_anchor, reset_new, "border cache reset")

start = s.index("void Emulator::BlitScreen(uint16_t *dest, uint32_t pitch_pixels)")
end = s.index("void Emulator::BlitScreenGB(", start)
region = s[start:end]
anchor = """\tif (!impl_->has_rom || !dest) return;

\t// Stage border"""
if region.count(anchor) != 1:
    raise RuntimeError(f"blit branch anchor: {region.count(anchor)}")

fast_code = r'''	if (!impl_->has_rom || !dest) return;

#if defined(IKCORE_SGB_COMPOSITOR_FAST) && defined(IKCORE_SGB_HYBRID_AUDIO)
	// The precise BIOS screen path is unchanged. Use cached presentation
	// only after the game has delivered a complete and stable SGB border.
	// CGB and non-SGB mono palettes keep the pre-existing generic path.
	if (!impl_->BiosMode() && impl_->perf_stable_border_valid &&
	    !impl_->ppu.cgb && !DmgPaletteActive(impl_->sgb_state, impl_->ppu))
	{
		if (impl_->perf_host_border_version != impl_->border_plane)
		{
			for (uint32_t i = 0; i < SGB_BORDER_W * SGB_BORDER_H; ++i)
				impl_->perf_host_border[i] =
					BgrToHost(impl_->perf_stable_border[i]);
			impl_->perf_host_border_version = impl_->border_plane;
		}
		// Exact original host border, including original behind-pane content.
		for (uint32_t y = 0; y < SGB_BORDER_H; ++y)
			std::memcpy(dest + y * pitch_pixels,
			            impl_->perf_host_border + y * SGB_BORDER_W,
			            SGB_BORDER_W * sizeof(uint16_t));

		const uint8_t mask = impl_->sgb_state.mask_mode;
		const uint8_t *src_fb = impl_->ppu.framebuffer;
		if (mask == SGB_MASK_FREEZE && impl_->sgb_state.frozen_frame_valid)
			src_fb = impl_->sgb_state.frozen_frame;

		// Masks are presentation-only; do not change the SGB mask state.
		if (mask == SGB_MASK_BLACK || mask == SGB_MASK_BLANK)
		{
			const uint16_t bgr = (mask == SGB_MASK_BLACK)
				? 0x0000u : impl_->sgb_state.active[0].colors[0];
			const uint16_t host = BgrToHost(GbShowColor(bgr, false));
			for (uint32_t y = 0; y < GB_SCREEN_HEIGHT; ++y)
			{
				uint16_t *row = dest + (y + SGB_GB_TILE_Y * 8u) *
					pitch_pixels + SGB_GB_TILE_X * 8u;
				for (uint32_t x = 0; x < GB_SCREEN_WIDTH; ++x)
					row[x] = host;
			}
			return;
		}

		// Attribute map and active SGB palettes may change per frame.
		// Preconvert all four colors once for each of the 20 x 18 tiles.
		// Never cache this table across frames.
		uint16_t pal_host[SGB_TILES][4];
		for (uint32_t tile = 0; tile < SGB_TILES; ++tile)
		{
			const uint8_t idx = impl_->sgb_state.attr_map[tile] & 3u;
			for (uint32_t shade = 0; shade < 4; ++shade)
				pal_host[tile][shade] = BgrToHost(GbShowColor(
					impl_->sgb_state.active[idx].colors[shade], false));
		}

		for (uint32_t y = 0; y < GB_SCREEN_HEIGHT; ++y)
		{
			uint16_t *row = dest + (y + SGB_GB_TILE_Y * 8u) *
				pitch_pixels + SGB_GB_TILE_X * 8u;
			const uint8_t *src = src_fb + y * GB_SCREEN_WIDTH;
			const uint32_t tile_row = (y >> 3) * SGB_TILE_COLS;
			for (uint32_t x = 0; x < GB_SCREEN_WIDTH; ++x)
				row[x] = pal_host[tile_row + (x >> 3)][src[x] & 3u];
		}
		return;
	}
#endif

	// Stage border'''
region=region.replace(anchor,fast_code,1)
s=s[:start]+region+s[end:]
p.write_text(s,encoding="utf-8")
print("IKCORE compositor fast branch: lossless cached border + per-tile host colors.")
