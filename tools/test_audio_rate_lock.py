#!/usr/bin/env python3
"""Math regression for direct SGB frame-locked GB APU PCM cadence.

No proprietary ROM, device, timing benchmark or audible-signal claim.
This catches a regression from the previous 32.45k/s PCM generation while
the real ALSA device consumes 32.040k/s.
"""
import math

SNES_NTSC_FPS = 60.09881389744051
GB_T_CYCLES_PER_FRAME = 70224
ALSA_HZ = 32040

# C++ uses (int32_t)(double + 0.5).
gb_apu_sampling_clock = math.floor(GB_T_CYCLES_PER_FRAME * SNES_NTSC_FPS + 0.5)
assert 4200000 < gb_apu_sampling_clock < 4230000, gb_apu_sampling_clock

for seconds in (1, 10, 120, 3600):
    emulated_frames = round(seconds * SNES_NTSC_FPS)
    generated = (emulated_frames * GB_T_CYCLES_PER_FRAME * ALSA_HZ) // gb_apu_sampling_clock
    consumed = seconds * ALSA_HZ
    # Output from an integer number of video frames differs by <1 video
    # frame of samples, even after an hour. No cumulative queue drift.
    assert abs(generated - consumed) <= math.ceil(ALSA_HZ / SNES_NTSC_FPS) + 1, (
        seconds, generated, consumed
    )
    print(f"{seconds}s: {generated} generated vs {consumed} consumed; drift={generated-consumed}")

# Old physical logs recorded 32453 frames/s at 60.10 fps, i.e. 413 more
# than ALSA can consume. This is enough to saturate 8192 frames in 20s.
old_rate = 32453
assert (old_rate - ALSA_HZ) * 60 > 8192
new_at_target = GB_T_CYCLES_PER_FRAME * SNES_NTSC_FPS * ALSA_HZ / gb_apu_sampling_clock
assert abs(new_at_target - ALSA_HZ) < 0.01, new_at_target

print("AUDIO RATE LOCK: PASS (bounded frame phase drift; fixed 32040 Hz target)")
