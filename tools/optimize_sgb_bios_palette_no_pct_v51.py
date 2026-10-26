#!/usr/bin/env python3
"""Ik Core v51: optimize BIOS-assigned SGB colors without a custom border.

The 43 fast compositor requires perf_stable_border_valid. The 50 DMG fast
compositor requires palette_writes==0. SGB BIOS can assign palettes to
original plain GB games even when no custom PCT_TRN is sent, leaving neither
path eligible and forcing the 256x224 BGR555 reference compositor. v51
supports this exact missing case, preserving SGB active palettes and attr map.

- No ROM matching/hacks, SGB palette overrides or guessed colors.
- Cache border per completed transfer (border_plane), even pre-PCT.
- Fast 20x18 tile palettes; 160x144 shade lookup, host RGB565 preconverted.
- Respect mask/freeze and do not touch the GB CPU, PPU, audio, timing.
- Leave all existing #43 SGB and #50 DMG code paths untouched.
- Provide first/120th-frame gate logs: negative result remains diagnosable.
"""
from pathlib import Path
p=Path("supersnes9x/sgb/sgb.cpp")
s=p.read_text(encoding="utf-8")
start=s.index("void Emulator::BlitScreen(uint16_t *dest, uint32_t pitch_pixels)")
end=s.index("void Emulator::BlitScreenGB(",start)
part=s[start:end]
anchor="\tif (!impl_->has_rom || !dest) return;\n"
if part.count(anchor)!=1:raise RuntimeError(f"Blit entry match {part.count(anchor)}")
code=r'''
#ifdef IKCORE_SGB_UNIVERSAL_V51
	// Gate evidence, sampled without changing frame state or input.
	// Run at the beginning of every full-screen BlitScreen call, whether
	// later handled by v51, #50 DMG, #43 SGB or the original fallback.
	static uint32_t ik51_frames=0;
	++ik51_frames;
	if (ik51_frames==1 || ik51_frames==120 || ik51_frames==600)
	{
		char m[180];
		std::snprintf(m,sizeof m,
		    "IKDISPLAY51 gate frame=%u direct=%u cgb=%u palWrites=%u "
		    "stable=%u pct=%u borderPlane=%u dmg=%u",
		    (unsigned)ik51_frames, (unsigned)!impl_->BiosMode(),
		    (unsigned)impl_->ppu.cgb,
		    (unsigned)impl_->sgb_state.palette_writes,
		    (unsigned)impl_->perf_stable_border_valid,
		    (unsigned)impl_->border_pct, (unsigned)impl_->border_plane,
		    (unsigned)DmgPaletteActive(impl_->sgb_state,impl_->ppu));
		S9xMessage(S9X_INFO,S9X_ROM_INFO,m);
	}

	// New uncovered case: BIOS-assigned SGB palettes, but cart has not
	// supplied a PCT_TRN-complete (stable) border.
	if (!impl_->BiosMode() && !impl_->ppu.cgb &&
	    impl_->sgb_state.palette_writes!=0 &&
	    !impl_->perf_stable_border_valid)
	{
		// Unlike #43, source border can be the built-in/default one.
		// Rebuild only when CHR_TRN/PCT_TRN actually changed the border.
		if (impl_->perf_host_border_version!=impl_->border_plane)
		{
			SgbRenderBorder(impl_->sgb_state,impl_->composite);
			for (uint32_t i=0;i<SGB_BORDER_W*SGB_BORDER_H;++i)
				impl_->perf_host_border[i]=
				    BgrToHost(impl_->composite[i]);
			impl_->perf_host_border_version=impl_->border_plane;
		}
		for (uint32_t y=0;y<SGB_BORDER_H;++y)
			std::memcpy(dest+y*pitch_pixels,
			    impl_->perf_host_border+y*SGB_BORDER_W,
			    SGB_BORDER_W*sizeof(uint16_t));

		const uint8_t mask=impl_->sgb_state.mask_mode;
		const uint8_t *src=impl_->ppu.framebuffer;
		if(mask==SGB_MASK_FREEZE && impl_->sgb_state.frozen_frame_valid)
			src=impl_->sgb_state.frozen_frame;

		if(mask==SGB_MASK_BLACK || mask==SGB_MASK_BLANK)
		{
			const uint16_t original=(mask==SGB_MASK_BLACK) ?
			     0x0000u : impl_->sgb_state.active[0].colors[0];
			const uint16_t value=BgrToHost(GbShowColor(original,false));
			for(uint32_t y=0;y<GB_SCREEN_HEIGHT;++y)
			{
				uint16_t *row=dest+(y+SGB_GB_TILE_Y*8u)*pitch_pixels
				                  +SGB_GB_TILE_X*8u;
				for(uint32_t x=0;x<GB_SCREEN_WIDTH;++x)
					row[x]=value;
			}
		}
		else
		{
			uint16_t lookup[SGB_TILES][4];
			for(uint32_t tile=0;tile<SGB_TILES;++tile)
			{
				const uint8_t pal=impl_->sgb_state.attr_map[tile]&3u;
				for(uint32_t shade=0;shade<4;++shade)
					lookup[tile][shade]=BgrToHost(GbShowColor(
					     impl_->sgb_state.active[pal].colors[shade],false));
			}
			for(uint32_t y=0;y<GB_SCREEN_HEIGHT;++y)
			{
				uint16_t *row=dest+(y+SGB_GB_TILE_Y*8u)*pitch_pixels
				                  +SGB_GB_TILE_X*8u;
				const uint8_t *line=src+y*GB_SCREEN_WIDTH;
				const uint32_t row_tile=(y>>3)*SGB_TILE_COLS;
				for(uint32_t x=0;x<GB_SCREEN_WIDTH;++x)
					row[x]=lookup[row_tile+(x>>3)][line[x]&3u];
			}
		}
		static bool message=false;
		if(!message)
		{
			message=true;
			char m[164];
			std::snprintf(m,sizeof m,
			    "IKDISPLAY51 active: BIOS palette no PCT. "
			    "palWrites=%u borderPlane=%u mask=%u",
			    (unsigned)impl_->sgb_state.palette_writes,
			    (unsigned)impl_->border_plane, (unsigned)mask);
			S9xMessage(S9X_INFO,S9X_ROM_INFO,m);
		}
		return;
	}
#endif
'''
part=part.replace(anchor,anchor+code,1)
s=s[:start]+part+s[end:]
p.write_text(s,encoding="utf-8")
print("IKDISPLAY51 universal direct SGB compositor gate + fallback installed.")
