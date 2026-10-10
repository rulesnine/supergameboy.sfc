# SGBPACK reference — verified from the user's Library (2026-10-10)

Original file: `KOF96_SGBPACK_v1_REUPLOAD.sfc` (user-supplied; binary remains in private Library, **never committed to repository**).

Overall SHA-256: `67bd27a135cefbe8815281dce085342d72cf9d06dfa251d54ded8dbaf0001f09`

Length: **1,311,232 bytes**; footer at `0x140100`; `SGBPACK1` version 1; flags `0x00000001`.

The following values were extracted from the actual footer and independently verified using Python `zlib.crc32` against the corresponding byte ranges:

| Region | Offset | Size | Stored CRC32 | Computed CRC32 | Result |
|---|---:|---:|---|---|---|
| Super Game Boy program | `0x000000` | 262144 | `8a4a174f` | `8a4a174f` | match |
| GB cartridge | `0x040000` | 1048576 | `78a3cc60` | `78a3cc60` | match |
| GB boot ROM | `0x140000` | 256 | `ec8a83b9` | `ec8a83b9` | match |
| Concatenated payload | `0x000000` | 1310976 | `9dd3d1a1` | `9dd3d1a1` | match |

GB header title: `NETTOU KOF 96`. GB SGB support flag at `0x146`: `03`.

## Audio validation implication

This proves the offline pack is structurally sound and its constituent ROM/BIOS sections match their embedded CRCs; **it does not demonstrate** that the existing PERF2 SPC700/DSP emulation, `SOUND`, `SOU_TRN`, `DATA_SND` mapping or audio timing is correct. To validate that, the same embedded program and boot ROM must be executed against a known-good reference and their CPU/APU port traces compared.

In the absence of such dynamic equivalence tests, keep PERF1 untouched and treat the PERF2 audio branch as experimental. Do not ship this private copyrighted ROM or boot image in a public HMOD/repository.
