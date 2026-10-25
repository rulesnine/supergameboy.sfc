#!/usr/bin/env python3
"""Read-only comparison of SGB BIOS SNES CGRAM vs GB/SGB palette transfer.

Ik Core #43 baseline unchanged: same core, optimized compositor and PCM.
Two event-only probes, Castlevania Legends original 256 KiB ROM only:
  - IKCGRAM at BIOS/direct handoff, SNES 256-color RAM vs SGB active palettes
  - IKPALTRN on original PAL_TRN, raw vs output shade capture plus BGP
No sprite, frame, PPU, video, sample rate or audio mutations.
"""
from pathlib import Path

def replace_n(data,old,new,n,label):
    k=data.count(old)
    if k!=n: raise RuntimeError(f"{label}: expected {n} matches; got {k}")
    return data.replace(old,new)

cpu=Path("supersnes9x/cpuexec.cpp")
c=cpu.read_text(encoding="utf-8")
anchor="\t\tS9xSGBEnterPerfDirectMode();"
trace=r'''#ifdef IKCORE_CASTLEVANIA_BIOS_CGRAM_TRACE
		{
			const unsigned char *rom = nullptr;
			size_t size = 0;
			if (S9xSGBGetROMBytes(&rom, &size) && rom &&
			    size == 0x40000 && rom[0x134] == 'C' &&
			    rom[0x135] == 'A' && rom[0x136] == 'S' &&
			    rom[0x137] == 'T' && rom[0x138] == 'L')
			{
				unsigned numColored = 0, numNonzero = 0;
				for (unsigned i = 0; i < 128; ++i)
				{
					const uint16_t v = PPU.CGDATA[i] & 0x7FFF;
					if (v) ++numNonzero;
					const unsigned r = v & 31u;
					const unsigned g = (v >> 5) & 31u;
					const unsigned b = (v >> 10) & 31u;
					if (r != g || r != b) ++numColored;
				}
				const uint16_t *pal = S9xSGBGetActivePalettes();
				char msg[600];
				snprintf(msg, sizeof msg,
				    "IKCGRAM BIOS-HANDOFF SNES colored=%u nonzero=%u "
				    "CG0=%04X,%04X,%04X,%04X "
				    "CG4=%04X,%04X,%04X,%04X "
				    "CG8=%04X,%04X,%04X,%04X "
				    "CG16=%04X,%04X,%04X,%04X "
				    "CG32=%04X,%04X,%04X,%04X "
				    "SGB0=%04X,%04X,%04X,%04X SGB1=%04X,%04X,%04X,%04X",
				    numColored,numNonzero,
				    PPU.CGDATA[0],PPU.CGDATA[1],PPU.CGDATA[2],PPU.CGDATA[3],
				    PPU.CGDATA[4],PPU.CGDATA[5],PPU.CGDATA[6],PPU.CGDATA[7],
				    PPU.CGDATA[8],PPU.CGDATA[9],PPU.CGDATA[10],PPU.CGDATA[11],
				    PPU.CGDATA[16],PPU.CGDATA[17],PPU.CGDATA[18],PPU.CGDATA[19],
				    PPU.CGDATA[32],PPU.CGDATA[33],PPU.CGDATA[34],PPU.CGDATA[35],
				    pal ? pal[0] : 0,pal ? pal[1] : 0,
				    pal ? pal[2] : 0,pal ? pal[3] : 0,
				    pal ? pal[4] : 0,pal ? pal[5] : 0,
				    pal ? pal[6] : 0,pal ? pal[7] : 0);
				S9xMessage(S9X_INFO,S9X_ROM_INFO,msg);
			}
		}
#endif
		S9xSGBEnterPerfDirectMode();'''
c=replace_n(c,anchor,trace,1,"handoff CGRAM")
cpu.write_text(c,encoding="utf-8")

gb=Path("supersnes9x/sgb/sgb.cpp")
s=gb.read_text(encoding="utf-8")
orig="""\t\t++g_sgb_dbg.cap_fired;
\t\tSgbHandleCommand(impl_->sgb_state, cmd,
\t\t                 impl_->border_capture.pkt, 16,
\t\t                 decoded, impl_->ppu.framebuffer);"""
changed=r'''		++g_sgb_dbg.cap_fired;
#ifdef IKCORE_CASTLEVANIA_BIOS_CGRAM_TRACE
		if (cmd == 0x0B && impl_->cart.rom.size() == 0x40000 &&
		    std::memcmp(impl_->cart.rom.data() + 0x134, "CASTLEVANIA", 11) == 0)
		{
			uint8_t output[4096];
			DecodeBorderCapture(impl_->ppu.framebuffer, output);
			unsigned diff = 0;
			for (unsigned i = 0; i < 4096; ++i)
				if (decoded[i] != output[i]) ++diff;
			char msg[360];
			std::snprintf(msg,sizeof msg,
			    "IKPALTRN BGP=%02X LCDC=%02X rawVsOutputBytes=%u "
			    "rawPAL4=%02X%02X%02X%02X%02X%02X%02X%02X "
			    "outPAL4=%02X%02X%02X%02X%02X%02X%02X%02X "
			    "rawPAL15=%02X%02X%02X%02X",
			    (unsigned)impl_->ppu.bgp,(unsigned)impl_->ppu.lcdc,diff,
			    decoded[32],decoded[33],decoded[34],decoded[35],
			    decoded[36],decoded[37],decoded[38],decoded[39],
			    output[32],output[33],output[34],output[35],
			    output[36],output[37],output[38],output[39],
			    decoded[120],decoded[121],decoded[122],decoded[123]);
			S9xMessage(S9X_INFO,S9X_ROM_INFO,msg);
		}
#endif
		SgbHandleCommand(impl_->sgb_state, cmd,
		                 impl_->border_capture.pkt, 16,
		                 decoded, impl_->ppu.framebuffer);'''
s=replace_n(s,orig,changed,2,"both SGB cycle runner transfer callbacks")
gb.write_text(s,encoding="utf-8")
print("IKCGRAM + IKPALTRN read-only probes installed in both SGB cycle paths.")
