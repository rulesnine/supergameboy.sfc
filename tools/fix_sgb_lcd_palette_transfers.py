#!/usr/bin/env python3
"""Fix SGB PAL_TRN/ATTR_TRN transfers to capture the LCD's 4KB signal.

For Ik Core NES Mini #25-compatible core. Run after tools/apply_sgbpack.py.
This changes ONLY the decoding of these two SGB VRAM-transfer commands;
CHR_TRN and PCT_TRN keep their existing, already-tested flow. No ROM-specific
checks, no per-frame histogram, no palette injection or audio changes.
"""
from pathlib import Path

p = Path("supersnes9x/sgb/sgb.cpp")
s = p.read_text(encoding="utf-8")
def exactly_once(old, new, label):
    global s
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: wanted 1 matching block; found {n}")
    s = s.replace(old, new, 1)

def in_run_cycles_once(old, new, label):
    global s
    a = s.index("void Emulator::RunCycles(int32_t tcycles)")
    b = s.index("const FrameBuffer &Emulator::GetFrameBuffer()", a)
    region = s[a:b]
    n = region.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: wanted 1 RunCycles match, found {n}")
    s = s[:a] + region.replace(old, new, 1) + s[b:]

# Extend asynchronous LCD transfer types instead of passing VRAM directly.
exactly_once(
    "enum Stage : uint8_t { Idle = 0, ChrTrn = 1, PctTrn = 2 };",
    "enum Stage : uint8_t { Idle = 0, ChrTrn = 1, PctTrn = 2, PalTrn = 3, AttrTrn = 4 };",
    "capture stages")

# Base patch from apply_sgbpack.py has already inserted SOUND / SOU_TRN block.
old = """\tif (cmd == 0x13 || cmd == 0x14)
\t{
\t\timpl_->border_capture.stage = (cmd == 0x13)
\t\t\t? Impl::BorderCapture::ChrTrn
\t\t\t: Impl::BorderCapture::PctTrn;
"""
new = """\t// The SGB transfers palette/attribute memory over the NEXT displayed
\t// GB LCD frame, just like CHR_TRN/PCT_TRN. Passing the unrendered VRAM
\t// array here reads wrong data on games that remap tiles (Castlevania).
\tif (cmd == 0x13 || cmd == 0x14 || cmd == 0x0B || cmd == 0x15)
\t{
\t\timpl_->border_capture.stage = (cmd == 0x13)
\t\t\t? Impl::BorderCapture::ChrTrn
\t\t\t: (cmd == 0x14)
\t\t\t? Impl::BorderCapture::PctTrn
\t\t\t: (cmd == 0x0B)
\t\t\t? Impl::BorderCapture::PalTrn
\t\t\t: Impl::BorderCapture::AttrTrn;
"""
exactly_once(old,new,"stage PAL_TRN + ATTR_TRN")

old="""\t\tconst uint8_t cmd =
\t\t\t(impl_->border_capture.stage == Impl::BorderCapture::ChrTrn)
\t\t\t\t? static_cast<uint8_t>(0x13)
\t\t\t\t: static_cast<uint8_t>(0x14);
"""
new="""\t\tconst uint8_t cmd =
\t\t\t(impl_->border_capture.stage == Impl::BorderCapture::ChrTrn) ? 0x13 :
\t\t\t(impl_->border_capture.stage == Impl::BorderCapture::PctTrn) ? 0x14 :
\t\t\t(impl_->border_capture.stage == Impl::BorderCapture::PalTrn) ? 0x0B : 0x15;
"""
in_run_cycles_once(old,new,"commit decoded LCD transfer by command")

# Tiny event-only telemetry; no scanning 23040 pixels each displayed frame.
old = """\t\tSgbHandleCommand(impl_->sgb_state, cmd,
\t\t                 impl_->border_capture.pkt, 16,
\t\t                 decoded, impl_->ppu.framebuffer);
\t\t++impl_->border_plane;
"""
new = """\t\tSgbHandleCommand(impl_->sgb_state, cmd,
\t\t                 impl_->border_capture.pkt, 16,
\t\t                 decoded, impl_->ppu.framebuffer);
\t\tif (cmd == 0x0B || cmd == 0x15)
\t\t{
\t\t\tunsigned nonzero = 0;
\t\t\tfor (unsigned i = 0; i < 4096; ++i)
\t\t\t\tif (decoded[i] != 0) ++nonzero;
\t\t\tchar msg[256];
\t\t\tstd::snprintf(msg, sizeof msg,
\t\t\t    "IKTRN commit cmd=%02X nonzero=%u first=%02X%02X%02X%02X "
\t\t\t    "palLoaded=%u attrLoaded=%u palWrites=%u",
\t\t\t    (unsigned)cmd, nonzero, decoded[0], decoded[1],
\t\t\t    decoded[2], decoded[3],
\t\t\t    (unsigned)impl_->sgb_state.system_palettes_loaded,
\t\t\t    (unsigned)impl_->sgb_state.attr_files_loaded,
\t\t\t    (unsigned)impl_->sgb_state.palette_writes);
\t\t\tS9xMessage(S9X_INFO, S9X_ROM_INFO, msg);
\t\t}
\t\tif (cmd == 0x13 || cmd == 0x14) ++impl_->border_plane;
"""
in_run_cycles_once(old,new,"commit transfer and trace only on captured commands")

# After PAL_SET, read the resulting 4-shade active palette (event-only).
old = """\tSgbHandleCommand(impl_->sgb_state, cmd, data, len,
\t                 impl_->ppu.vram,
\t                 impl_->ppu.framebuffer);
}
"""
new = """\tSgbHandleCommand(impl_->sgb_state, cmd, data, len,
\t                 impl_->ppu.vram,
\t                 impl_->ppu.framebuffer);
\tif (cmd == 0x0A)
\t{
\t\tconst auto &s = impl_->sgb_state;
\t\tchar msg[256];
\t\tstd::snprintf(msg, sizeof msg,
\t\t    "IKTRN PAL_SET loaded=%u writes=%u pal0=%04X,%04X,%04X,%04X "
\t\t    "pal1=%04X,%04X,%04X,%04X",
\t\t    (unsigned)s.system_palettes_loaded,
\t\t    (unsigned)s.palette_writes,
\t\t    (unsigned)s.active[0].colors[0], (unsigned)s.active[0].colors[1],
\t\t    (unsigned)s.active[0].colors[2], (unsigned)s.active[0].colors[3],
\t\t    (unsigned)s.active[1].colors[0], (unsigned)s.active[1].colors[1],
\t\t    (unsigned)s.active[1].colors[2], (unsigned)s.active[1].colors[3]);
\t\tS9xMessage(S9X_INFO, S9X_ROM_INFO, msg);
\t}
}
"""
exactly_once(old,new,"PAL_SET resulting palette trace")

p.write_text(s,encoding="utf-8")
print("IKTRN: PAL_TRN and ATTR_TRN now use decoded Game Boy LCD 4KB transfer.")
