# Ik Core RC4: QuickStart visual experimental (31 Oct 2026)
BASE: 67babc668606fa7df6c8acc490cfb85bd44825c7

Change: Original RC4 waits 480 GB frames (8s) for SGB enhanced games without PCT, 4 DMG frames, 16 when renderer not full-size. New gate: 120 SGB frames (2s) ONLY if PCT count is still zero, 2 DMG frames (~33ms), 8 non-full frames. If PCT has begun, preserve original 30 quiet frames to prevent half-formed custom border. No changes to SPC700/DSP, firmware handoff, ROM PCT/CHR, audio, FPS, 120s exit behavior, loading art, or game CPU.

Separate long startup: Snes9x firmware boot is synchronous and may cost ~35s for an uncached SGBPACK1. Fastboot cache already existed; this branch adds cache ABSENT diagnostics but does NOT claim to make first firmware boot 3s or guarantee warm-cache hits. Never disable the real SPC firmware bootstrap to claim speed gains.

NOTE: Branch has source-only changes. Not compiled into ARMv7 HMOD or hardware-tested in NES Mini. Build on pinned production workflow then validate startup log IKSPC FASTBOOT cache=HIT and startup_ms; test KOF96 custom border; GB no PCT; SNES typing SFX; 60fps; no premature exit; compare with RC4. Never deploy over working #40.

Readiness conditions: no generic GBA border; full ROM custom PCT after 30 quiet frames; cold boot and cache hit both work with genuine SNES effects; do not claim success without hardware log.
## Diagnóstico nuevo: caché rechazada (logs de NES Mini)
Los registros aportados del hardware muestran: Ik Core #19 KOF96 SGBPACK1 cache=MISSED_OR_INVALID, full boot 36359ms; #28 CASTLEVANIA2_BEL 4800 frames y firmware boot incomplete (SNES audio disabled); #32 CASTLEVANIA_SGBPACK1 cache=MISSED_OR_INVALID, cache=SAVED bytes=215083, hit=0. La versión previa solo imprimía MISSED_OR_INVALID si el archivo de caché ya había sido abierto (un archivo ausente devolvía 0 silenciosamente). Dos rutas independientes: fallo de restauración de caché y firmware no listo para un paquete específico. El nombre aleatorio del directorio temporal no importa: la clave FNV-1a es calculada sobre los bytes completos de SGBPACK1.

Instrumentación de diagnóstico añadida a ik_spc_host.c: cache=ABSENT para archivo inexistente, cache=REJECTED reason=... para HEADER_READ, CACHE_FORMAT, PACK_HASH, STATE_SIZE_RANGE, STATE_SIZE_CHANGED, BORDER_FLAG, NO_MEMORY, STATE_READ, BORDER_READ, UNSERIALIZE, SPC_REACTIVATION; HIT si valida y restaura. Sin cambio al propio estado ni la lógica del arranque. Requiere compilar variante aislada y repetir el mismo paquete SGBPACK1 para verificar HIT. El arreglo definitivo depende del reason medido, no se ha identificado todavía.
