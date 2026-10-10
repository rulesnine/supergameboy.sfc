#!/usr/bin/env python3
"""Offline SGBPACK1 + known NETTOU KOF 96 SGB command audit.

Reads a private user-owned pack. Never writes ROM/BIOS contents to the
repository or the JSON report. Detects static command tables only; this
is NOT a dynamic SNES/APU execution trace.
"""
import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

TABLE = [
    (0x10000, 0x17, None),
    (0x10010, 0x17, None),
    (0x10020, 0x11, None),
    (0x10030, 0x11, None),
    (0x10040, 0x11, None),
    (0x10050, 0x0F, 0x085D),
    (0x10060, 0x0F, 0x0852),
    (0x10070, 0x0F, 0x0847),
    (0x10080, 0x0F, 0x083C),
    (0x10090, 0x0F, 0x0831),
    (0x100A0, 0x0F, 0x0826),
    (0x100B0, 0x0F, 0x081B),
    (0x100C0, 0x0F, 0x0810),
    (0x103C8, 0x13, None),
    (0x103DA, 0x13, None),
    (0x103EC, 0x14, None),
]


def read_u32(b, p):
    return struct.unpack_from("<I", b, p)[0]


def inspect_pack(source: bytes):
    if len(source) < 256 or source[-256:-248] != b"SGBPACK1":
        raise ValueError("SGBPACK1 footer missing")
    f = source[-256:]
    if read_u32(f, 8) != 1:
        raise ValueError("unsupported pack version")
    payload_end = len(source) - 256
    sections = []
    for name, o, n, crc in (
        ("sgb", read_u32(f, 0x10), read_u32(f, 0x14), read_u32(f, 0x28)),
        ("gb", read_u32(f, 0x18), read_u32(f, 0x1C), read_u32(f, 0x2C)),
        ("gb_boot", read_u32(f, 0x20), read_u32(f, 0x24), read_u32(f, 0x30)),
    ):
        if o + n > payload_end:
            raise ValueError(f"out of bounds: {name}")
        actual = zlib.crc32(source[o:o + n])
        if crc != actual:
            raise ValueError(f"CRC mismatch: {name}")
        sections.append({"name": name, "offset": o, "length": n, "crc32": f"{crc:08x}"})
    if (sections[0]["offset"] != 0
        or sections[0]["offset"] + sections[0]["length"] != sections[1]["offset"]
        or sections[1]["offset"] + sections[1]["length"] != sections[2]["offset"]
        or sections[2]["offset"] + sections[2]["length"] != payload_end
        or sections[2]["length"] != 256):
        raise ValueError("invalid contiguous pack layout")
    if zlib.crc32(source[:payload_end]) != read_u32(f, 0xA8):
        raise ValueError("payload CRC mismatch")
    start = sections[1]["offset"]
    rom = source[start:start + sections[1]["length"]]
    title = rom[0x134:0x144].split(b"\x00", 1)[0].decode("ascii", "replace")
    commands = []
    for offset, cmd, expected_address in TABLE:
        packet = rom[offset:offset + 16]
        if len(packet) != 16 or packet[0] != (cmd << 3) | 1:
            raise ValueError(f"wrong KOF96 SGB command at GB ROM offset 0x{offset:X}")
        item = {
            "gb_rom_offset": f"0x{offset:05X}",
            "bank": offset // 0x4000,
            "gb_cpu_address": f"0x{(offset % 0x4000) + 0x4000:04X}",
            "command": f"0x{cmd:02X}",
        }
        if cmd == 0x0F:
            address = packet[1] | (packet[2] << 8)
            bank = packet[3]
            count = packet[4]
            if bank != 0 or address != expected_address or count != 11:
                raise ValueError(f"unexpected DATA_SND at 0x{offset:X}")
            item.update({"snes_bank": bank, "snes_address": f"0x{address:04X}",
                         "write_length": count})
        commands.append(item)
    return {
        "sha256": hashlib.sha256(source).hexdigest(),
        "size": len(source),
        "game": title,
        "sgb_support_flag": rom[0x146],
        "sections": sections,
        "known_static_sgb_packet_table": commands,
        "snes_data_snd_patch_span": "bank 00:$0810-$0867",
        "caveat": "Static data analysis only, not an audio or CPU execution trace",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sgbpack", type=Path)
    parser.add_argument("--output", type=Path, help="optional JSON report with metadata only")
    args = parser.parse_args()
    result = inspect_pack(args.sgbpack.read_bytes())
    out = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(out, encoding="utf8")
    else:
        print(out, end="")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
