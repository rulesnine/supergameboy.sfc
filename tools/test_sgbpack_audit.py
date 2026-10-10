#!/usr/bin/env python3
"""Synthetic test for private-ROM SGBPACK auditor: no copyrighted bytes."""
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_sgbpack_reference import TABLE, inspect_pack

sgb = bytearray(0x40000)
gb = bytearray(0x100000)
gb[0x134:0x134 + 13] = b"NETTOU KOF 96"
gb[0x146] = 3
boot = bytearray(256)
for at, command, dest in TABLE:
    gb[at] = command * 8 + 1
    if dest is not None:
        struct.pack_into("<H", gb, at + 1, dest)
        gb[at + 3] = 0
        gb[at + 4] = 11
payload = bytes(sgb + gb + boot)
footer = bytearray(256)
footer[:8] = b"SGBPACK1"
for off, val in (
    (8, 1), (0x10, 0), (0x14, len(sgb)),
    (0x18, len(sgb)), (0x1c, len(gb)),
    (0x20, len(sgb) + len(gb)), (0x24, len(boot)),
    (0x28, zlib.crc32(sgb)), (0x2c, zlib.crc32(gb)),
    (0x30, zlib.crc32(boot)), (0xa8, zlib.crc32(payload)),
):
    struct.pack_into("<I", footer, off, val)
pack = payload + footer

assert len(inspect_pack(pack)["known_static_sgb_packet_table"]) == len(TABLE)

def must_reject(blob):
    try:
        inspect_pack(blob)
    except ValueError:
        return
    raise AssertionError("bad pack was accepted")

bad_crc = bytearray(pack)
bad_crc[0x40000 + 0x10050 + 4] ^= 1
must_reject(bytes(bad_crc))

bad_command = bytearray(pack)
bad_command[0x40000 + 0x10050] = 0x41
# Update both CRCs to ensure auditor checks command identity beyond CRC.
struct.pack_into("<I", bad_command, len(pack) - 256 + 0x2c,
                 zlib.crc32(bad_command[0x40000:0x140000]))
struct.pack_into("<I", bad_command, len(pack) - 256 + 0xa8,
                 zlib.crc32(bad_command[:-256]))
must_reject(bytes(bad_command))
print("SGBPACK auditor synthetic tests: PASS (valid / CRC mismatch / command mismatch)")
