# Ik Core — PERF2 parallel SNES audio candidate (not yet device-validated)

## User-approved baseline

**Do not alter the visual border transition, original boot/fade, gameplay logic, RGB565 compositor, SGB PCT_TRN/CHR_TRN atomic handoff or GB frame renderer.** The user approved the appearance of PERF2 Audio Repair #109, reporting better SNES audio and noticeably better game performance, but audible cuts.

Known observations on NES Mini:
- PERF1: 59.99 fps average, work cost 14.582 ms/frame; no SNES enhanced audio.
- PERF2 Audio Repair #109: 45.22 fps average including real SGB BIOS startup, work cost 21.554 ms/frame; direct gameplay about 50–54 fps, **212 ALSA recoveries** during 120 seconds.
- SPC700/DSP standalone measurement: ~2.944 ms/frame (peak ~3.475). PERF1 remaining budget was only ~2.06 ms/frame.
- SNES `SOUND` commands are being issued; physical listening says the quality improved but stutters.

## Implementation

Dedicated *persistent* Linux pthread in the hybrid SGB core:

1. On the existing BIOS-to-direct handoff, preserve the real initialised SPC700/DSP state and initialize one worker.
2. At the start of each direct GB video frame, hand the queued audio commands to the worker, which alone can manipulate SNES CPU ports, SMP, DSP and their resampler.
3. GB CPU/PPU and RGB565 compositor run concurrently on the normal thread, with the original border transition code **unchanged**.
4. Before audio mixing and ALSA callbacks, wait until the sound worker finishes. There is no concurrent buffer read/write.
5. `SOUND` packets and `SOU_TRN` payloads are queued FIFO and applied by the worker on the following audio frame (up to one emulated frame of extra command latency). The validated SOU_TRN transaction and protections remain unchanged.
6. If worker initialization fails, fall back to the prior sequential SPC frame path; on reset/unload, join worker before releasing resources.

With this architecture, ~2.94 ms of SPC work may overlap GB emulation on a second CPU core instead of being added to every frame. This **does not guarantee** 58–60 FPS or fidelity: memory bandwidth, CPU contention and scheduling will affect results. The full SNES BIOS startup path is intentionally unchanged to preserve the fade/transitions.

## ALSA diagnostics (passive, no audio manipulation)

Separate log: `/var/lib/hakchi/sgb-native-test/ikcore-perf2-parallel.log`.

`audio/sec` shows produced stereo frames per second, accepted ALSA frames per second, and incremental/total recoveries with current ring occupancy. Once the handoff completes, the critical acceptance criterion is approximately 32040 stereo frames/sec with no ongoing recoveries in steady-state gameplay. The 60.099 FPS objective corresponds to ~533 audio frames per emulated frame.

## Validation gates

- CI: ARM hard-float build for GLIBC <=2.23, pthread linkage, HMOD packaging, synthetic private-ROM parser tests. Green build == **build success only**.
- Expected device acceptance, *not yet performed*: >=58 FPS sustained in normal gameplay, audio free of cuts/pitch corruption, zero new ALSA recoveries after warm-up, coherent original frame transitions. All visible graphics and SGB palette secrets must remain the same.
- Rollback: uninstall this candidate and restore #109 or PERF1 if any change causes regressions. No code is merged into `main` or `ikcore/perf2-audio-repair` automatically.

No private user's SGBPACK or SGB BIOS bytes are included in this repository or artifacts. The code remains a modified Snes9x-based hybrid and is **not** clean-room SNES emulation or mGBA.
