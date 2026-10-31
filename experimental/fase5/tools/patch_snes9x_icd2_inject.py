#!/usr/bin/env python3
"""Expose a safe raw-packet injection seam in pinned SuperSnes9x.
Invocation: AFTER tools/apply_sgbpack.py; BEFORE compiling Snes9x.
An actual mGBA runtime + video/VRAM bridge is still required.
"""
import sys
from pathlib import Path

def exactly_once(text, needle, replacement, label):
    n = text.count(needle)
    if n != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {n}")
    return text.replace(needle, replacement, 1)

def patch_header(src):
    src = exactly_once(src,
        '\tvoid  OnSgbCommandInternal(uint8_t cmd, const uint8_t *data, uint32_t len);',
        '\tvoid  OnSgbCommandInternal(uint8_t cmd, const uint8_t *data, uint32_t len);\n'
        '\tbool  InjectRawMGBAPacket(const uint8_t packet[16]);',
        'emulator method')
    src = exactly_once(src,
        'void S9xSGBRunFrame(void);',
        'void S9xSGBRunFrame(void);\n'
        'bool S9xSGBInjectRawMGBAPacket(const uint8_t packet[16]);',
        'C facade declaration')
    return src

METHOD = r'''
#ifdef IKCORE_MGBA_ICD2_EXPERIMENTAL
bool Emulator::InjectRawMGBAPacket(const uint8_t packet[16])
{
    if (!packet || !impl_->has_rom) return false;
    if (impl_->BiosMode())
    {
        // Do not silently discard the oldest packet when the BIOS lags.
        // Underlying IcdPushQueue() overwrites on saturation, so reject.
        if (impl_->icd2.queue_count >= 64) return false;
        IcdPushQueue(impl_->icd2, packet);
        return true;
    }
    // Direct SGB path: reuse existing chained-packet decoder/callback,
    // rather than reimplement SGB command and chain semantics here.
    // This does NOT supply the mGBA framebuffer or transfer VRAM yet.
    PacketFeed(impl_->sgb_pkt, 0x00);
    PacketFeed(impl_->sgb_pkt, 0x30);
    for (int bit = 0; bit < 128; ++bit)
    {
        PacketFeed(impl_->sgb_pkt,
                   (packet[bit >> 3] & (1u << (bit & 7))) ? 0x10 : 0x20);
        PacketFeed(impl_->sgb_pkt, 0x30);
    }
    return true;
}
#endif

'''

FACADE = r'''
#ifdef IKCORE_MGBA_ICD2_EXPERIMENTAL
bool S9xSGBInjectRawMGBAPacket(const uint8_t packet[16])
{
    return SGB::Instance().InjectRawMGBAPacket(packet);
}
#endif
'''

def patch_cpp(src):
    needle = 'void Emulator::OnSgbCommandInternal(uint8_t cmd, const uint8_t *data, uint32_t len)\n{'
    src = exactly_once(src, needle, METHOD + needle, 'icd2 method')
    needle = 'void S9xSGBRunFrame(void)'
    # This anchor appears once in pinned Snes9x before profile transformations.
    src = exactly_once(src, needle, FACADE + needle, 'facade implementation')
    return src

if __name__ == '__main__':
    if len(sys.argv) != 2: raise SystemExit('Usage: patch_snes9x_icd2_inject.py SUPERSNES9X_ROOT')
    root = Path(sys.argv[1])
    h, c = root/'sgb/sgb.h', root/'sgb/sgb.cpp'
    hh, cc = h.read_text(), c.read_text()
    if 'IKCORE_MGBA_ICD2_EXPERIMENTAL' in cc:
        raise RuntimeError('already patched')
    h.write_text(patch_header(hh))
    c.write_text(patch_cpp(cc))
    print('PASS: SGB packet injection seam patched (not full hybrid)')
