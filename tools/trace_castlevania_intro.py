#!/usr/bin/env python3
"""Bounded, read-only SGB palette timeline for Castlevania Legends intro/title.

Runs after apply_sgbpack.py + fix_sgb_lcd_palette_transfers.py
+ optimize_sgb_compositor.py. No palette mutations, no audio changes.
Samples 360 attribute-map entries at most once every 90 BlitScreen calls,
and logs select SGB commands as events. ROM-title-gated so KOF96 untouched.
"""
from pathlib import Path

p = Path("supersnes9x/sgb/sgb.cpp")
s = p.read_text(encoding="utf-8")

def only(old,new,label):
    global s
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {n}")
    s=s.replace(old,new,1)

# Log every SGB palette/attribute command at its first handler entry, including
# packets preceding the BIOS->direct handoff. No per-frame busy polling.
start=s.index("void Emulator::OnSgbCommandInternal(uint8_t cmd, const uint8_t *data, uint32_t len)")
end=s.index("\n// ===================================================================",start)
region=s[start:end]
anchor="\tDbgPushCmd(cmd);\n"
event=r'''	DbgPushCmd(cmd);
#ifdef IKCORE_CASTLEVANIA_TITLE_TRACE
	const auto &ikrom = impl_->cart.rom;
	if (ikrom.size() == 0x40000 &&
	    std::memcmp(ikrom.data() + 0x134, "CASTLEVANIA", 11) == 0 &&
	    (cmd <= 0x07 || cmd == 0x0A || cmd == 0x0B ||
	     cmd == 0x13 || cmd == 0x14 || cmd == 0x15 ||
	     cmd == 0x16 || cmd == 0x17))
	{
		char msg[272];
		std::snprintf(msg, sizeof msg,
		    "IKTITLE CMD id=%02X len=%u d1=%02X d2=%02X "
		    "d9=%02X BIOS=%u mask=%u palWrites=%u attrWrites=%u "
		    "loaded=%u atfLoaded=%u LCDC=%02X pct=%u",
		    (unsigned)cmd,(unsigned)len,
		    (unsigned)(len > 1 ? data[1] : 0),
		    (unsigned)(len > 2 ? data[2] : 0),
		    (unsigned)(len > 9 ? data[9] : 0),
		    (unsigned)impl_->BiosMode(),
		    (unsigned)impl_->sgb_state.mask_mode,
		    (unsigned)impl_->sgb_state.palette_writes,
		    (unsigned)impl_->sgb_state.attr_writes,
		    (unsigned)impl_->sgb_state.system_palettes_loaded,
		    (unsigned)impl_->sgb_state.attr_files_loaded,
		    (unsigned)impl_->ppu.lcdc,
		    (unsigned)impl_->border_pct);
		S9xMessage(S9X_INFO, S9X_ROM_INFO, msg);
	}
#endif
'''
if region.count(anchor)!=1: raise RuntimeError("event anchor count mismatch")
region=region.replace(anchor,event,1)
s=s[:start]+region+s[end:]

# In BlitScreen, sample BEFORE the optimized early return. Once/90 frames.
start=s.index("void Emulator::BlitScreen(uint16_t *dest, uint32_t pitch_pixels)")
end=s.index("void Emulator::BlitScreenGB(",start)
region=s[start:end]
anchor="\tif (!impl_->has_rom || !dest) return;\n"
trace=r'''	if (!impl_->has_rom || !dest) return;
#ifdef IKCORE_CASTLEVANIA_TITLE_TRACE
	{
		static unsigned long iktitle_n = 0;
		const auto &rom = impl_->cart.rom;
		if (rom.size() == 0x40000 &&
		    std::memcmp(rom.data() + 0x134, "CASTLEVANIA", 11) == 0 &&
		    (++iktitle_n == 1 || iktitle_n % 90 == 0))
		{
			unsigned used[4] = {0,0,0,0};
			for (unsigned i=0; i<SGB_TILES; ++i)
				++used[impl_->sgb_state.attr_map[i] & 3u];
			const auto &st = impl_->sgb_state;
			char msg[384];
			std::snprintf(msg,sizeof msg,
			    "IKTITLE FRAME n=%lu BIOS=%u mask=%u "
			    "palWrites=%u attrWrites=%u pal0=%04X,%04X,%04X,%04X "
			    "pal1=%04X,%04X,%04X,%04X "
			    "pal2=%04X,%04X,%04X,%04X "
			    "attrUse=%u,%u,%u,%u centerPal=%u mapLoaded=%u "
			    "LCDC=%02X pct=%u",
			    iktitle_n,(unsigned)impl_->BiosMode(),(unsigned)st.mask_mode,
			    (unsigned)st.palette_writes,(unsigned)st.attr_writes,
			    (unsigned)st.active[0].colors[0],(unsigned)st.active[0].colors[1],
			    (unsigned)st.active[0].colors[2],(unsigned)st.active[0].colors[3],
			    (unsigned)st.active[1].colors[0],(unsigned)st.active[1].colors[1],
			    (unsigned)st.active[1].colors[2],(unsigned)st.active[1].colors[3],
			    (unsigned)st.active[2].colors[0],(unsigned)st.active[2].colors[1],
			    (unsigned)st.active[2].colors[2],(unsigned)st.active[2].colors[3],
			    used[0],used[1],used[2],used[3],
			    (unsigned)st.attr_map[10*20+10],
			    (unsigned)st.border.map_loaded,
			    (unsigned)impl_->ppu.lcdc,(unsigned)impl_->border_pct);
			S9xMessage(S9X_INFO,S9X_ROM_INFO,msg);
		}
	}
#endif
'''
if region.count(anchor)!=1:raise RuntimeError(f"Blit anchor count {region.count(anchor)}")
region=region.replace(anchor,trace,1)
s=s[:start]+region+s[end:]
p.write_text(s,encoding="utf-8")
print("IKTITLE read-only logging installed; output every 90 direct SGB frames.")
