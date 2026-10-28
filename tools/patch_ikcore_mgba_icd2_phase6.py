#!/usr/bin/env python3
"""Attach pinned mGBA's completed SGB packets to Ik Core's EXISTING ICD2 FIFO.

Never emulate a second ICD2, never write SNES APU ports twice. This inserts
an opt-in entry on the Snes9x side; legacy SGB packets still follow their
validated path. The new bridge is inactive without explicit first-cycle mGBA
session activation, which remains separate from normal Hakchi startup.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2: raise SystemExit("usage: patch_ikcore_mgba_icd2_phase6.py /path/to/supersnes9x")
root=Path(sys.argv[1]); hh=root/"sgb/sgb.h"; cc=root/"sgb/sgb.cpp"
h=hh.read_text(encoding="utf-8-sig")
s=cc.read_text(encoding="utf-8-sig")
def once(v,needle,replacement,label):
    found=v.count(needle)
    if found!=1:raise RuntimeError(f"{label}: expected one upstream anchor, got {found}")
    return v.replace(needle,replacement,1)
h=once(h,"uint8_t GetICD2(uint16_t addr);",
    "uint8_t GetICD2(uint16_t addr);\n\t// Opt-in only: mGBA-completed SGB packets enter the same $6002/$7000 FIFO.\n\tbool ReceiveMGBAPackets(const uint8_t *packets, uint32_t size);",
    "Emulator method")
h=once(h,"unsigned char S9xSGBGetICD2 (unsigned short addr);",
    "unsigned char S9xSGBGetICD2 (unsigned short addr);\n// 1 accepted, -1 refused/queue-full. Called only by phase6 active bridge.\nint S9xSGBReceiveMGBAPackets(const unsigned char *packets, unsigned size);",
    "ICD2 facade header")
anchor="static void IcdStageNextSynth(Emulator::Impl::Icd2 &icd)"
method=r'''// FASE6: use the *same* 64-slot FIFO the SNES BIOS $6002 already drains.
// Avoid IcdFeedJoypad: mGBA has assembled complete packets, so parsing bits
// again would duplicate SGB traffic. Do not call SgbHandleCommand a second
// time: authentic SNES BIOS remains the only consumer of the ICD2 FIFO.
bool Emulator::ReceiveMGBAPackets(const uint8_t *packets, uint32_t size)
{
    if (!impl_ || !packets || !impl_->BiosMode() ||
        !IsGBReleased() || size < 16 || size > 112 || (size & 15))
        return false;
    const unsigned blocks=size/16u;
    if ((packets[0] & 7u)!=blocks) return false;
    Emulator::Impl::Icd2 &icd=impl_->icd2;
    // Atomic all-or-nothing: dropping a middle packet breaks the BIOS's
    // SGB command stream. Leave existing FIFO unchanged on overflow.
    if ((unsigned)icd.queue_count + blocks > 64u) return false;
    for (unsigned p=0;p<blocks;++p)
    {
        const uint8_t *pkt=packets+p*16u;
        IcdPushQueue(icd,pkt);
        // Genuine GB SGB boot validates six first-packet bytes across
        // release cycles. Keep the existing validated handshake cache.
        if (impl_->cached_count < 6)
        {
            std::memcpy(impl_->cached_packets[impl_->cached_count],pkt,16);
            impl_->cached_count++;
            if (impl_->cached_count==6) impl_->cache_valid=true;
        }
    }
    return true;
}

'''
s=once(s,anchor,method+anchor,"ICD2 enqueue method")
facade="unsigned char S9xSGBGetICD2(unsigned short addr)\n{"
s=once(s,facade,'''int S9xSGBReceiveMGBAPackets(const unsigned char *packets,unsigned size)
{
    return SGB::Instance().ReceiveMGBAPackets(packets,size)?1:-1;
}

'''+facade,"ICD2 C facade")
hh.write_text(h,encoding="utf-8");cc.write_text(s,encoding="utf-8")
# Fase4/5 version-script is passed with --version-script and -fwhole-program.
# Export these two user-visible opt-in symbols or they disappear under LTO.
version=root/"libretro/link.T"
vs=version.read_text(encoding="utf-8")
head="ikcore_mgba_phase5_*;"
if vs.count(head)!=1:
    raise RuntimeError("Phase5 linker exports changed")
vs=vs.replace(head,"ikcore_mgba_phase5_*; ikcore_mgba_phase6_*;",1)
version.write_text(vs,encoding="utf-8")
print("IKCORE_PHASE6_ICD2_REAL_FIFO connected mGBA completed packets to Snes9x BIOS $6002/$7000")
