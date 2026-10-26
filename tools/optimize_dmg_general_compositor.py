#!/usr/bin/env python3
"""Ik Core #50: full-frame optimized direct DMG compositor for NES Mini.

#43 optimized the full-color SGB path only. Titles which do not send SGB
PAL_SET remain in the costly general compositor, whose 256x224 border is
reconstructed/color-converted each frame.

This patch adds a genuinely general *monochrome GB* fast path while keeping
the existing 60-FPS SGB path from #43 untouched. A title without SGB
palettes (e.g. Castlevania II: Belmont's Revenge) draws its complete SGBPACK
256x224 presentation using:
 - a versioned cached border (including original, pre-PCT default frame),
 - three DMG register palette LUTs (BG, OBJ0, OBJ1) preconverted just once
   per frame from the existing Settings.GBPalette entries,
 - direct 160x144 GB shade+layer lookup with preserved SGB MASK_EN modes.
No changed emulator clock, 2-bit framebuffer, GB CPU/PPU, audio, BIOS,
SGB command semantics, SGB palettes, custom borders, or ROM data.

Must run AFTER apply_sgbpack.py, fix_sgb_lcd_palette_transfers.py and
optimize_sgb_compositor.py; it is enabled only with
IKCORE_SGB_DMG_FAST_DISPLAY.
"""
from pathlib import Path

p=Path("supersnes9x/sgb/sgb.cpp")
s=p.read_text(encoding="utf-8")
scope=s.index("void Emulator::BlitScreen(uint16_t *dest, uint32_t pitch_pixels)")
end=s.index("void Emulator::BlitScreenGB(",scope)
part=s[scope:end]
anchor="\tif (!impl_->has_rom || !dest) return;\n"
if part.count(anchor)!=1:
    raise RuntimeError(f"BlitScreen entry: found {part.count(anchor)}")
patch=r'''
#ifdef IKCORE_SGB_DMG_FAST_DISPLAY
	// DMG titles with no PAL_SET don't satisfy #43's SGB fast-path gate.
	// Their precise original per-pixel DMG palette is nonetheless available
	// and can be calculated once, without changing the Game Boy state.
	if (!impl_->BiosMode() && !impl_->ppu.cgb &&
	    DmgPaletteActive(impl_->sgb_state, impl_->ppu))
	{
		// Works even when no game-originated PCT_TRN exists: render the
		// SgbState's own pre-PCT border, just as the old slow path does.
		if (impl_->perf_host_border_version != impl_->border_plane)
		{
			SgbRenderBorder(impl_->sgb_state, impl_->composite);
			for (uint32_t i=0; i<SGB_BORDER_W*SGB_BORDER_H; ++i)
				impl_->perf_host_border[i] =
					BgrToHost(impl_->composite[i]);
			impl_->perf_host_border_version = impl_->border_plane;
		}
		for (uint32_t y=0; y<SGB_BORDER_H; ++y)
			std::memcpy(dest + y*pitch_pixels,
			            impl_->perf_host_border + y*SGB_BORDER_W,
			            SGB_BORDER_W*sizeof(uint16_t));

		const uint8_t mask=impl_->sgb_state.mask_mode;
		const uint8_t *src_fb=impl_->ppu.framebuffer;
		if (mask == SGB_MASK_FREEZE && impl_->sgb_state.frozen_frame_valid)
			src_fb=impl_->sgb_state.frozen_frame;

		if (mask == SGB_MASK_BLACK || mask == SGB_MASK_BLANK)
		{
			const uint16_t color=(mask == SGB_MASK_BLACK) ?
				0 : impl_->sgb_state.active[0].colors[0];
			const uint16_t host=BgrToHost(GbShowColor(color,false));
			for (uint32_t y=0;y<GB_SCREEN_HEIGHT;++y)
			{
				uint16_t *row=dest+(y+SGB_GB_TILE_Y*8u)*pitch_pixels
				             +SGB_GB_TILE_X*8u;
				for (uint32_t x=0;x<GB_SCREEN_WIDTH;++x) row[x]=host;
			}
			return;
		}

		// Same palette choice as DmgShadeColor(shade, layer), but choose
		// the actual layer palette once for each of the three DMG types
		// rather than running a 5-bit -> RGB565 conversion per pixel.
		uint16_t lut[3][4];
		const uint8_t kinds[3] = {
			0,
			static_cast<uint8_t>(GB_PIXEL_OBJ),
			static_cast<uint8_t>(GB_PIXEL_OBJ | GB_PIXEL_OBJ_PAL1)
		};
		for (uint32_t pal=0;pal<3;++pal)
			for (uint32_t shade=0;shade<4;++shade)
				lut[pal][shade]=BgrToHost(GbShowColor(
					DmgShadeColor(static_cast<uint8_t>(shade),kinds[pal]),
					false));
		for (uint32_t y=0;y<GB_SCREEN_HEIGHT;++y)
		{
			uint16_t *row=dest+(y+SGB_GB_TILE_Y*8u)*pitch_pixels
			             +SGB_GB_TILE_X*8u;
			const uint32_t offset=y*GB_SCREEN_WIDTH;
			for (uint32_t x=0;x<GB_SCREEN_WIDTH;++x)
			{
				const uint32_t pixel=offset+x;
				const uint8_t layer=impl_->ppu.layer[pixel];
				const uint32_t pal =
					((layer & GB_PIXEL_LAYER) == GB_PIXEL_OBJ) ?
					((layer & GB_PIXEL_OBJ_PAL1) ? 2u : 1u) : 0u;
				row[x]=lut[pal][src_fb[pixel] & 3u];
			}
		}
		static bool reported=false;
		if (!reported)
		{
			reported=true;
			char report[160];
			std::snprintf(report,sizeof report,
			    "IKDMGFAST active: direct 160x144 DMG, cached 256x224 "
			    "border, palWrites=%u pct=%u",
			    (unsigned)impl_->sgb_state.palette_writes,
			    (unsigned)impl_->border_pct);
			S9xMessage(S9X_INFO,S9X_ROM_INFO,report);
		}
		return;
	}
#endif
'''
part=part.replace(anchor,anchor+patch,1)
s=s[:scope]+part+s[end:]
p.write_text(s,encoding="utf-8")
print("IKDMGFAST installed as an isolated DMG-only direct-compositor fast path; SGB #43 unchanged.")
