#!/usr/bin/env python3
"""Generate a 32 KiB, self-authored GBX Game Boy ROM that sends ONE SGB SOUND packet.

No Nintendo logo, commercial code, BIOS, games, sound assets or proprietary
firmware is included. mGBA recognizes it via GBX metadata. Executes a
deterministic JOYP bitstream 0x00 -> 0x30 -> {0x10/0x20,0x30} -> 0x20.
"""
from pathlib import Path
import sys
path=Path(sys.argv[1]) if len(sys.argv)>1 else Path("ikcore-test-sgb.gb")
payload=bytes([0x41,0x37,0x23,0x51,0x13]+[0]*11)
rom=bytearray(32768)
rom[0x100:0x104]=bytes([0xC3,0x50,0x01,0])
rom[0x134:0x144]=b"IKCORE-SGB-TEST\x00"
rom[0x143]=0
rom[0x146]=0x03
rom[0x147]=0
rom[0x148]=0
rom[0x149]=0
rom[0x14B]=0x33
rom[0x14C]=0
program=bytearray([0x31,0xFE,0xFF, 0x3E,0x91,0xE0,0x40])
def joyp_write(value):
    program.extend([0x3E,value,0xE0,0x00])
joyp_write(0x00)
joyp_write(0x30)
for b in payload:
    for shift in range(8):
        joyp_write(0x10 if (b>>shift)&1 else 0x20)
        joyp_write(0x30)
joyp_write(0x20)
program.extend([0x18,0xFE])
assert len(program)<4096
rom[0x150:0x150+len(program)]=program
checksum=0
for i in range(0x134,0x14D):checksum=(checksum-rom[i]-1)&0xFF
rom[0x14D]=checksum
rom[0x14E:0x150]=(sum(rom[:0x14E])+sum(rom[0x150:])&65535).to_bytes(2,"big")
gbx=bytearray(64)
gbx[0:4]=b"ROM"+bytes([0])
gbx[8:12]=len(rom).to_bytes(4,"big")
gbx[48:52]=(64).to_bytes(4,"big")
gbx[52:56]=(1).to_bytes(4,"big")
gbx[60:64]=b"GBX!"
rom.extend(gbx)
path.write_bytes(rom)
print(f"IKCORE_SYNTHETIC_SGB_SOUND bytes={len(rom)} gbCodeBytes={len(program)} packet={payload.hex()}")
