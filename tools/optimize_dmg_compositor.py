#!/usr/bin/env python3
"""Fast native DMG/non-SGB-palette compositor for Ik Core NES Mini #50.

Adds a separate, source-fidelity DMG branch alongside the #43 SGB fast path.
Only display presentation is modified. Does not change ROM, SGB commands,
clocking, GB CPU/PPU, SPC/DSP, ALSA, masks, palette configuration or input.

Preexisting fallback repaints 57,344 border pixels + 23,040 game pixels each
frame using pixel-by-pixel color conversion. Precompute host-color border when
its version changes, and cache 12 possible DMG colors per displayed frame
(3 layers x 4 shades), retaining live per-pixel OBJ/BG selection.

Keep the #43 true-SGB direct fast path byte-for-byte untouched.
"""
from pathlib import Path
p=Path("supersnes9x/sgb/sgb.cpp")
s=p.read_text(encoding="utf-8")
start=s.index("void Emulator::BlitScreen(uint16_t *dest, uint32_t pitch_pixels)")
end=s.index("void Emulator::BlitScreenGB(", start)
region=s[start:end]
anchor="\t// Stage border into our heap-resident 256"
if region.count(anchor) != 1:
    raise RuntimeError(f"Expected single fallback anchor, saw {region.count(anchor)}")
branch=r'''#if defined(IKCORE_SGB_COMPOSITOR_FAST) && defined(IKCORE_SGB_HYBRID_AUDIO)
	// DMG fast presentation is a sibling of the #43 true-SGB fast path,
	// and takes the case that #43 excluded: no game-supplied SGB palettes.
	if (!impl_->BiosMode() && !impl_->ppu.cgb &&
	    DmgPaletteActive(impl_->sgb_state, impl_->ppu))
	{
		// Border appearance only depends on CHR_TRN/PCT_TRN transactions,
		// not on live GB pixels. Reuse the same #43 host-border cache.
		if (impl_->perf_host_border_version != impl_->border_plane)
		{
			const uint16_t *border_bgr = impl_->perf_stable_border;
			if (!impl_->perf_stable_border_valid)
			{
				// No SGB-enhanced border? Preserve exactly the original
				// default SGB border from the reference renderer.
				SgbRenderBorder(impl_->sgb_state, impl_->composite);
				border_bgr = impl_->composite;
			}
			for (uint32_t i = 0; i < SGB_BORDER_W * SGB_BORDER_H; ++i)
				impl_->perf_host_border[i] = BgrToHost(border_bgr[i]);
			impl_->perf_host_border_version = impl_->border_plane;
		}
		for (uint32_t y = 0; y < SGB_BORDER_H; ++y)
			std::memcpy(dest + y * pitch_pixels,
			            impl_->perf_host_border + y * SGB_BORDER_W,
			            SGB_BORDER_W * sizeof(uint16_t));

		const uint8_t mask = impl_->sgb_state.mask_mode;
		if (mask == SGB_MASK_BLACK || mask == SGB_MASK_BLANK)
		{
			const uint16_t bgr = (mask == SGB_MASK_BLACK)
				? 0x0000u : impl_->sgb_state.active[0].colors[0];
			const uint16_t host = BgrToHost(GbShowColor(bgr, false));
			for (uint32_t y = 0; y < GB_SCREEN_HEIGHT; ++y)
			{
				uint16_t *out = dest + (y + SGB_GB_TILE_Y * 8u) *
					pitch_pixels + SGB_GB_TILE_X * 8u;
				for (uint32_t x = 0; x < GB_SCREEN_WIDTH; ++x)
					out[x] = host;
			}
			return;
		}

		const uint8_t *src_fb = impl_->ppu.framebuffer;
		if (mask == SGB_MASK_FREEZE &&
		    impl_->sgb_state.frozen_frame_valid)
			src_fb = impl_->sgb_state.frozen_frame;

		// Rebuild every frame, so live Settings.GBPalette settings are
		// preserved. Background/window and both OBJ palettes remain
		// separate, as they are in the original DmgShadeColor().
		uint16_t host_colors[3][4];
		for (uint32_t shade = 0; shade < 4; ++shade)
		{
			host_colors[0][shade] = BgrToHost(GbShowColor(
				DmgShadeColor((uint8_t)shade, 0), false));
			host_colors[1][shade] = BgrToHost(GbShowColor(
				DmgShadeColor((uint8_t)shade, GB_PIXEL_OBJ), false));
			host_colors[2][shade] = BgrToHost(GbShowColor(
				DmgShadeColor((uint8_t)shade,
					GB_PIXEL_OBJ | GB_PIXEL_OBJ_PAL1), false));
		}

		const uint8_t *src_layer = impl_->ppu.layer;
		for (uint32_t y = 0; y < GB_SCREEN_HEIGHT; ++y)
		{
			const uint32_t off = y * GB_SCREEN_WIDTH;
			const uint8_t *src = src_fb + off;
			const uint8_t *layer = src_layer + off;
			uint16_t *out = dest + (y + SGB_GB_TILE_Y * 8u) *
				pitch_pixels + SGB_GB_TILE_X * 8u;
			for (uint32_t x = 0; x < GB_SCREEN_WIDTH; ++x)
			{
				const uint8_t z = layer[x];
				const uint32_t pal = ((z & GB_PIXEL_LAYER) == GB_PIXEL_OBJ)
					? ((z & GB_PIXEL_OBJ_PAL1) ? 2u : 1u) : 0u;
				out[x] = host_colors[pal][src[x] & 3u];
			}
		}
		static bool printed = false;
		if (!printed)
		{
			printed = true;
			S9xMessage(S9X_INFO, S9X_ROM_INFO,
				"IKDMG fast compositor active: cached border + 3x4 DMG shades.");
		}
		return;
	}
#endif

'''
region=region.replace(anchor,branch+anchor,1)
s=s[:start]+region+s[end:]
p.write_text(s,encoding="utf-8")
print("IKCORE #50 DMG fast compositor added, #43 SGB fast branch preserved.")
