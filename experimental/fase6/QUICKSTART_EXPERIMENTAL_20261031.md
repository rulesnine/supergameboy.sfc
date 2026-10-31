# Ik Core RC4: QuickStart visual experimental (31 Oct 2026)
BASE: 67babc668606fa7df6c8acc490cfb85bd44825c7

Change: Original RC4 waits 480 GB frames (8s) for SGB enhanced games without PCT, 4 DMG frames, 16 when renderer not full-size. New gate: 120 SGB frames (2s) ONLY if PCT count is still zero, 2 DMG frames (~33ms), 8 non-full frames. If PCT has begun, preserve original 30 quiet frames to prevent half-formed custom border. No changes to SPC700/DSP, firmware handoff, ROM PCT/CHR, audio, FPS, 120s exit behavior, loading art, or game CPU.

Separate long startup: Snes9x firmware boot is synchronous and may cost ~35s for an uncached SGBPACK1. Fastboot cache already existed; this branch adds cache ABSENT diagnostics but does NOT claim to make first firmware boot 3s or guarantee warm-cache hits. Never disable the real SPC firmware bootstrap to claim speed gains.

NOTE: Branch has source-only changes. Not compiled into ARMv7 HMOD or hardware-tested in NES Mini. Build on pinned production workflow then validate startup log IKSPC FASTBOOT cache=HIT and startup_ms; test KOF96 custom border; GB no PCT; SNES typing SFX; 60fps; no premature exit; compare with RC4. Never deploy over working #40.

Readiness conditions: no generic GBA border; full ROM custom PCT after 30 quiet frames; cold boot and cache hit both work with genuine SNES effects; do not claim success without hardware log.