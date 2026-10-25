#!/usr/bin/env python3
"""Read-only Castlevania ATTR_TRN source comparator, executed after title trace.
Runs only when a 4 KiB ATTR_TRN transfer completes. Audio/graphics unchanged.
"""
from pathlib import Path

p=Path("supersnes9x/sgb/sgb.cpp")
s=p.read_text(encoding="utf-8")

old = """\t\t++g_sgb_dbg.cap_fired;
\t\tSgbHandleCommand(impl_->sgb_state, cmd,
\t\t                 impl_->border_capture.pkt, 16,
\t\t                 decoded, impl_->ppu.framebuffer);"""

new = r'''		++g_sgb_dbg.cap_fired;
#ifdef IKCORE_CASTLEVANIA_ATTR_AUDIT
		if (cmd == 0x15)
		{
			const auto &rom = impl_->cart.rom;
			if (rom.size() == 0x40000 &&
			    std::memcmp(rom.data() + 0x134, "CASTLEVANIA", 11) == 0)
			{
				auto count_tiles = [](const uint8_t *p) -> unsigned {
					unsigned n = 0;
					for (unsigned i=0; i<90; ++i)
						for (unsigned j=0; j<4; ++j)
							n += (((p[i] >> (j*2)) & 3u) != 0);
					return n;
				};
				uint8_t displayed[4096];
				DecodeBorderCapture(impl_->ppu.framebuffer, displayed);
				const unsigned raw0 = count_tiles(decoded);
				const unsigned lcd0 = count_tiles(displayed);
				const unsigned vram0 = count_tiles(impl_->ppu.vram);
				const unsigned raw5 = count_tiles(decoded + 450);
				const unsigned lcd5 = count_tiles(displayed + 450);
				const unsigned vram5 = count_tiles(impl_->ppu.vram + 450);
				char msg[240];
				std::snprintf(msg, sizeof msg,
				    "IKATF ATTR_TRN first file 0 raw=%u LCD=%u VRAM=%u "
				    "file5 raw=%u LCD=%u VRAM=%u BGP=%02X LCDC=%02X "
				    "rawHead=%02X%02X%02X%02X VRAMHead=%02X%02X%02X%02X",
				    raw0,lcd0,vram0,raw5,lcd5,vram5,
				    (unsigned)impl_->ppu.bgp,(unsigned)impl_->ppu.lcdc,
				    decoded[0],decoded[1],decoded[2],decoded[3],
				    impl_->ppu.vram[0],impl_->ppu.vram[1],
				    impl_->ppu.vram[2],impl_->ppu.vram[3]);
				S9xMessage(S9X_INFO,S9X_ROM_INFO,msg);
			}
		}
#endif
		SgbHandleCommand(impl_->sgb_state, cmd,
		                 impl_->border_capture.pkt, 16,
		                 decoded, impl_->ppu.framebuffer);'''

count=s.count(old)
if count != 2:
    raise RuntimeError(f"Expected standard and fast sync transfer sites, got {count}")
s=s.replace(old,new)
p.write_text(s,encoding="utf-8")
print("IKATF comparator installed on both sync paths (read-only).")
