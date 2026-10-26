#!/usr/bin/env python3
"""#49: connect mGBA-style center-border overlay to *both* Ik Core SGB blit paths.

#48 compiled but IKOVERLAY was inside the optional compositor fast branch.
If that branch's guard was false, the optional overlay never initialized.
#49 generates the lightweight overlay cache at entry to the full SGB blit
and uses it from either fast or reference renderer.

No palette, boot firmware, ROM, GB CPU/PPU, SPC/DSP, timing, or ALSA change.
The fast compositor retains exactly the original #43 path when overlay empty.
"""
from pathlib import Path
p=Path("supersnes9x/sgb/sgb.cpp")
s=p.read_text(encoding="utf-8")
start=s.index("void Emulator::BlitScreen(uint16_t *dest, uint32_t pitch_pixels)")
end=s.index("void Emulator::BlitScreenGB(", start)
part=s[start:end]

def one(old,new,label):
    global part
    n=part.count(old)
    if n!=1:
        raise RuntimeError(f"{label}: expected 1 occurrence, found {n}")
    part=part.replace(old,new,1)

build_first="#ifdef IKCORE_SGB_MGBA_BORDER_OVERLAY\n\t\tif (impl_->perf_overlay_cached != impl_->perf_overlay_serial)"
a=part.find(build_first)
if a<0: raise RuntimeError("can't find #48 disabled fast-path overlay builder")
stop="\n#endif\n\t\tconst uint8_t mask = impl_->sgb_state.mask_mode;"
b=part.find(stop,a)
if b<0: raise RuntimeError("can't find overlay builder end before fast mask")
cached=part[a:b+len("\n#endif")]
# remove from fast branch, preserving original flow
part=part[:a]+part[b+len("\n#endif"):]
intro="\tif (!impl_->has_rom || !dest) return;\n"
if part.count(intro)!=1: raise RuntimeError("unexpected BlitScreen entry")
diagnostic=r'''
#ifdef IKCORE_SGB_MGBA_BORDER_OVERLAY
	// Print the actual path and gate status a few times only.
	// This distinguishes overlay 0-pixel source from a disabled fast path.
	static uint32_t ik_overlay_probe_frame = 0;
	++ik_overlay_probe_frame;
	if (ik_overlay_probe_frame == 1u || ik_overlay_probe_frame == 120u)
	{
		char info[230];
		std::snprintf(info, sizeof info,
		    "IKOVERLAY path=BlitScreen frame=%u direct=%u stable=%u "
		    "cgb=%u dmg=%u pct=%u palWrites=%u opaque=%u",
		    (unsigned)ik_overlay_probe_frame,
		    (unsigned)!impl_->BiosMode(),
		    (unsigned)impl_->perf_stable_border_valid,
		    (unsigned)impl_->ppu.cgb,
		    (unsigned)DmgPaletteActive(impl_->sgb_state, impl_->ppu),
		    (unsigned)impl_->border_pct,
		    (unsigned)impl_->sgb_state.palette_writes,
		    (unsigned)impl_->perf_overlay_pixels);
		S9xMessage(S9X_INFO,S9X_ROM_INFO,info);
	}
#endif
'''
# move the cache builder above both fast and fallback branches; no cache
# churn except on atomic PCT commit or initial construction.
part=part.replace(intro,intro+"\n"+cached+"\n"+diagnostic,1)

# Overlay must also be applied to the *host* pixels output by the slow
# fallback because staging is BGR555 and the cache is already RGB565.
# Only the viewport overlay's nonzero pixels are drawn.
fallback=r'''
#ifdef IKCORE_SGB_MGBA_BORDER_OVERLAY
	// mGBA draws only nontransparent SGB border pixels over the GB window.
	// The direct fallback has already converted staging BGR555 to host RGB565.
	if (!impl_->BiosMode() && !impl_->ppu.cgb &&
	    impl_->sgb_state.mask_mode == SGB_MASK_CANCEL &&
	    impl_->perf_overlay_pixels != 0u)
	{
		for (uint32_t y=0; y<GB_SCREEN_HEIGHT; ++y)
		{
			uint16_t *row = dest + (y + SGB_GB_TILE_Y*8u) * pitch_pixels
			                      + SGB_GB_TILE_X*8u;
			for (uint32_t x=0; x<GB_SCREEN_WIDTH; ++x)
			{
				const uint32_t index=y*GB_SCREEN_WIDTH+x;
				if (impl_->perf_overlay_mask[index])
					row[x] = impl_->perf_overlay_colors[index];
			}
		}
	}
#endif
'''
# Function end, not any intermediate brace.
closing=part.rfind("\n}\n")
if closing<0 or closing<len(part)-9: raise RuntimeError("failed to find BlitScreen function closing brace")
part=part[:closing]+"\n"+fallback+part[closing:]
s=s[:start]+part+s[end:]
p.write_text(s,encoding="utf-8")
print("IKCORE #49 overlay cache now initialized in real BlitScreen entry; fast+fallback overlay enabled.")
