#!/usr/bin/env python3
"""Generate a copyright-free DMG ROM for verifying GB core and frame output.

The ROM is built from scratch and intentionally contains NO Nintendo boot ROM,
game program, logo, artwork or proprietary data. It runs a stable LCD-on loop.
"""
from pathlib import Path
import sys
path=Path(sys.argv[1]) if len(sys.argv)>1 else Path("ikcore-test.gb")
rom=bytearray(32768)
# Entry -> owned minimal program at $0150 (inside bank 0).
rom[0x100:0x104]=bytes([0xC3,0x50,0x01,0x00])
# Zero the LCD/interrupt state deterministically; then loop.
# LD SP,$FFFE; LD A,$91; LDH ($40),A; EI; JR -2
rom[0x150:0x159]=bytes([0x31,0xFE,0xFF,0x3E,0x91,0xE0,0x40,0xFB,0x18])
rom[0x159]=0xFE
rom[0x134:0x143]=b"IKCORE-GB-TEST\x00"
rom[0x143]=0 # DMG
rom[0x146]=0 # no SGB enhancement
rom[0x147]=0 # no MBC
rom[0x148]=0 # 32KB
rom[0x149]=0 # no RAM
rom[0x14B]=0x33
rom[0x14C]=0
value=0
for i in range(0x134,0x14D): value=(value-rom[i]-1)&0xFF
rom[0x14D]=value
total=sum(rom[:0x14E])+sum(rom[0x150:])
rom[0x14E]=(total>>8)&0xFF
rom[0x14F]=total&0xFF
# mGBA's cartridge detector accepts either a registered brand-logo sequence
# or a standards-based GBX metadata trailer. Use the latter so NO Nintendo
# logo or proprietary bytes need appear in a synthetic test cartridge.
footer=bytearray(64)
footer[0:4]=b"ROM"+bytes([0]) # MBC-none FourCC
footer[8:12]=(len(rom)).to_bytes(4,"big")
footer[12:16]=(0).to_bytes(4,"big")
footer[48:52]=(64).to_bytes(4,"big")
footer[52:56]=(1).to_bytes(4,"big")
footer[60:64]=b"GBX!"
rom.extend(footer)
path.write_bytes(rom)
print(f"IKCORE_SYNTHETIC_GBX {path} bytes={len(rom)} header={value:02X}")
