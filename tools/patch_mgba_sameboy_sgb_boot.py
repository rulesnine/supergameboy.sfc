#!/usr/bin/env python3
"""Accept the original MIT/Expat-licensed SGB boot sequence already embedded in
pinned SuperSnes9x/SameBoy, without patching mGBA's standard BIOS whitelist for
any other custom boot ROM. The source copy is upstream; no BIOS is distributed
in our SDK. Only executed as part of our experimental compiled mGBA integration.
"""
from pathlib import Path
import re
import sys
import zlib

if len(sys.argv) not in (3, 4):
    raise SystemExit("usage: patch_mgba_sameboy_sgb_boot.py /path/to/mgba /path/to/snes9x [local-test-fixtures-dir]")
mgba=Path(sys.argv[1])
snes=Path(sys.argv[2])
text=(snes/"sgb/sgb.cpp").read_text(encoding="utf-8-sig")
checks={}
for name in ("kSgbBootRom", "kSgb2BootRom"):
    match=re.search(r"static const uint8_t\s+"+name+r"\[256\]\s*=\s*\{(.*?)\};",
                    text,re.S)
    if not match:
        raise SystemExit(f"Failed to locate upstream licensed 256-byte {name}")
    data=bytes(int(value,16) for value in re.findall(r"0x([0-9A-Fa-f]{2})",match.group(1)))
    assert len(data)==256, (name,len(data))
    checks[name]=zlib.crc32(data)&0xFFFFFFFF
    if len(sys.argv)==4:
        out=Path(sys.argv[3])
        out.mkdir(parents=True,exist_ok=True)
        (out/(name+".bin")).write_bytes(data)
    print(f"IKCORE_LICENSED_SGB_BOOT {name} CRC32={checks[name]:08x} size={len(data)}")

path=mgba/"src/gb/gb.c"
code=path.read_text()
old="""bool GBIsCompatibleBIOS(struct VFile* vf, enum GBModel model) {
	switch (_GBBiosCRC32(vf)) {"""
new=f"""bool GBIsCompatibleBIOS(struct VFile* vf, enum GBModel model) {{
    /* Experimental Ik Core: pinned SameBoy/Expat SGB boot ROMs only.
     * Reject every other unknown BIOS; normal upstream checks unchanged.
     * GBModel values are not merged or assumed compatible with CGB.
     */
    const uint32_t ik_crc=_GBBiosCRC32(vf);
    if ((model == GB_MODEL_SGB && ik_crc == 0x{checks["kSgbBootRom"]:08X}u) ||
        (model == GB_MODEL_SGB2 && ik_crc == 0x{checks["kSgb2BootRom"]:08X}u))
        return true;
	switch (ik_crc) {{"""
if code.count(old)!=1:raise SystemExit("Pinned mGBA GBIsCompatibleBIOS signature drifted")
path.write_text(code.replace(old,new,1))
print("IKCORE_PHASE5_SGB_BOOT_WHITELIST pinned SGB1/SGB2 SameBoy/Expat CRC only")
