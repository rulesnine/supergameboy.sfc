# Ik Core RC4: QuickStart visual experimental (31 Oct 2026)
BASE: 67babc668606fa7df6c8acc490cfb85bd44825c7

Change: Original RC4 waits 480 GB frames (8s) for SGB enhanced games without PCT, 4 DMG frames, 16 when renderer not full-size. New gate: 120 SGB frames (2s) ONLY if PCT count is still zero, 2 DMG frames (~33ms), 8 non-full frames. If PCT has begun, preserve original 30 quiet frames to prevent half-formed custom border. No changes to SPC700/DSP, firmware handoff, ROM PCT/CHR, audio, FPS, 120s exit behavior, loading art, or game CPU.

Separate long startup: Snes9x firmware boot is synchronous and may cost ~35s for an uncached SGBPACK1. Fastboot cache already existed; this branch adds cache ABSENT diagnostics but does NOT claim to make first firmware boot 3s or guarantee warm-cache hits. Never disable the real SPC firmware bootstrap to claim speed gains.

NOTE: Branch has source-only changes. Not compiled into ARMv7 HMOD or hardware-tested in NES Mini. Build on pinned production workflow then validate startup log IKSPC FASTBOOT cache=HIT and startup_ms; test KOF96 custom border; GB no PCT; SNES typing SFX; 60fps; no premature exit; compare with RC4. Never deploy over working #40.

Readiness conditions: no generic GBA border; full ROM custom PCT after 30 quiet frames; cold boot and cache hit both work with genuine SNES effects; do not claim success without hardware log.
## Diagnóstico nuevo: caché rechazada (logs de NES Mini)
Los registros aportados del hardware muestran: Ik Core #19 KOF96 SGBPACK1 cache=MISSED_OR_INVALID, full boot 36359ms; #28 CASTLEVANIA2_BEL 4800 frames y firmware boot incomplete (SNES audio disabled); #32 CASTLEVANIA_SGBPACK1 cache=MISSED_OR_INVALID, cache=SAVED bytes=215083, hit=0. La versión previa solo imprimía MISSED_OR_INVALID si el archivo de caché ya había sido abierto (un archivo ausente devolvía 0 silenciosamente). Dos rutas independientes: fallo de restauración de caché y firmware no listo para un paquete específico. El nombre aleatorio del directorio temporal no importa: la clave FNV-1a es calculada sobre los bytes completos de SGBPACK1.

Instrumentación de diagnóstico añadida a ik_spc_host.c: cache=ABSENT para archivo inexistente, cache=REJECTED reason=... para HEADER_READ, CACHE_FORMAT, PACK_HASH, STATE_SIZE_RANGE, STATE_SIZE_CHANGED, BORDER_FLAG, NO_MEMORY, STATE_READ, BORDER_READ, UNSERIALIZE, SPC_REACTIVATION; HIT si valida y restaura. Sin cambio al propio estado ni la lógica del arranque. Requiere compilar variante aislada y repetir el mismo paquete SGBPACK1 para verificar HIT. El arreglo definitivo depende del reason medido, no se ha identificado todavía.


## RC5: corrección del origen del falso FASTBOOT (código, sin prueba física aún)
Análisis del upstream fijado shanytc/snes9x commit 183e03e5efed3b6d450385c98e2ccffb194153c3, snapshot.cpp líneas ~1038-1116: con Settings.SuperGameBoy=TRUE, retro_serialize_size() y retro_serialize() guardan exclusivamente el blob Game Boy SGB! mediante S9xSGBStateSize/Save. Los ~215083 bytes registrados en la NES Mini coinciden con esa ruta; NO son una captura del estado completo SPC700/DSP/SNES. La caché anterior identificaba incorrectamente ese archivo como firmware.

Se añadió una API privada ikcore_spc_full_snapshot_size/save/restore en el puente Snes9x. Durante estas tres operaciones se desactivan temporalmente Settings.SuperGameBoy y Settings.SGB_BIOSModeActive para escoger el formato SNES #!s9xsnp incluyendo RAM, APU, DSP y programa N-SPC, sin datos GB. Ambos flags se restauran después de cada operación, incluso si falla. Desactivar el BIOS flag temporalmente evita que S9xFreezeSize() cambie entre BIOS y handoff por el bloque opcional GBE. ik_spc_host.c exige estos tres símbolos exclusivos y valida el prefijo de 9 bytes #!s9xsnp:, checksum FNV32, hash completo del SGBPACK1 y la firma de caché v4. El estado antiguo SGB! ya no es admisible.

Aislamiento: las cachés antiguas en ikcore-sgb-prod-cache permanecen intactas. La nueva ruta ikcore-sgb-quick-cache-v4 es exclusiva de RC5; ejecutables y logs ikcore-sgb-quick no reemplazan RC4 ni #40/#43. Si un S9xUnfreezeGameMem() parcial falla, se descarga y vuelve a cargar el firmware antes de arrancar el BIOS: nunca arranca sobre un estado mutado sin validación.

Pruebas: la prueba mock C++ local g++ -std=c++17 -Wall -Wextra -Werror pasó para comprobar tamaño constante, guardado/restauración y restauración de banderas. El test que extrae las funciones reales del puente se añadió como test_prod_full_spc_snapshot.py al flujo ARMv7, antes de compilar. Primera ejecución sin caché v4 necesita BIOS; la segunda con el MISMO SGBPACK1 debería reutilizar el nuevo estado, pero no se afirma un tiempo ni audio hardware validados. Castlevania II con 4800 frames y SNES audio disabled es un problema independiente que esta corrección no soluciona.

Compilación aislada definida en .github/workflows/build-sgb-quickstart.yml. No afirmar un HMOD publicado sin verificar un artifact compilado y su SHA-256.
