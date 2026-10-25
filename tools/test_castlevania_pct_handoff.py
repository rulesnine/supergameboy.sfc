#!/usr/bin/env python3
"""Isolated BIOS->direct handoff timing diagnostic, Castlevania Legends only.
Runs after apply_sgbpack.py, fix_sgb_lcd_palette_transfers.py, and
optimize_sgb_compositor.py. All PPU, audio, color, and BIOS code unchanged.
Delay *only* the Castlevania handoff until its first PCT_TRN has committed.
Other games, including KOF96, retain #43 behavior and exact handoff point.
"""
from pathlib import Path

sgb=Path("supersnes9x/sgb/sgb.cpp")
h=Path("supersnes9x/sgb/sgb.h")
cpu=Path("supersnes9x/cpuexec.cpp")

def once(text, old, new, label):
    count=text.count(old)
    if count!=1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old,new,1)

c=sgb.read_text(encoding="utf-8")
before="""bool S9xSGBScreenVisible(void)
{
\treturn SGB::Instance().IsScreenVisible();
}
"""
after=before+"""
#ifdef IKCORE_CASTLEVANIA_PCT_HANDOFF
bool S9xSGBDelayDirectModeUntilPct(void)
{
    SGB::Emulator &emu = SGB::Instance();
    const uint8_t *rom = emu.GetROMData();
    if (!rom || emu.GetROMSize() != 0x40000 ||
        std::memcmp(rom + 0x134, "CASTLEVANIA", 11) != 0)
        return false;
    // For this cart only, run the real SGB BIOS until the game's first
    // full PCT_TRN commit. Do not defer music or rendering in other games.
    return emu.BorderPctCount() == 0;
}
#endif
"""
c=once(c,before,after,"facade handoff check")
sgb.write_text(c,encoding="utf-8")

d=h.read_text(encoding="utf-8")
header_old="bool          S9xSGBScreenVisible (void);"
d=once(d,header_old,header_old+"""
#ifdef IKCORE_CASTLEVANIA_PCT_HANDOFF
bool          S9xSGBDelayDirectModeUntilPct(void);
#endif""","header facade declaration")
h.write_text(d,encoding="utf-8")

q=cpu.read_text(encoding="utf-8")
pred_old="""\t    S9xSGBBootSetupComplete() &&
\t    S9xSGBScreenVisible())"""
pred_new="""\t    S9xSGBBootSetupComplete() &&
\t    S9xSGBScreenVisible()
#ifdef IKCORE_CASTLEVANIA_PCT_HANDOFF
\t    && !S9xSGBDelayDirectModeUntilPct()
#endif
\t    )"""
q=once(q,pred_old,pred_new,"PERF2 handoff predicate")
cpu.write_text(q,encoding="utf-8")
print("IKCORE Castlevania-specific PCT handoff gate installed; other games unchanged.")
