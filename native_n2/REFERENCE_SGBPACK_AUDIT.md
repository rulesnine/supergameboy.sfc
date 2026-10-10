# SGBPACK reference — verified from the user's Library (2026-10-10)

Original file: `KOF96_SGBPACK_v1_REUPLOAD.sfc` (user-supplied; binary remains in private Library, **never committed to repository**).

Overall SHA-256: `67bd27a135cefbe8815281dce085342d72cf9d06dfa251d54ded8dbaf0001f09`

Length: **1,311,232 bytes**; footer at `0x140100`; `SGBPACK1` version 1; flags `0x00000001`.

The following values were extracted from the actual footer and independently verified using Python `zlib.crc32` against the corresponding byte ranges:

| Region | Offset | Size | Stored CRC32 | Computed CRC32 | Result |
|---|---:|---:|---|---|---|
| Super Game Boy program | `0x000000` | 262144 | `8a4a174f` | `8a4a174f` | match |
| GB cartridge | `0x040000` | 1048576 | `78a3cc60` | `78a3cc60` | match |
| GB boot ROM | `0x140000` | 256 | `ec8a83b9` | `ec8a83b9` | match |
| Concatenated payload | `0x000000` | 1310976 | `9dd3d1a1` | `9dd3d1a1` | match |

GB header title: `NETTOU KOF 96`. GB SGB support flag at `0x146`: `03`.

## Audio validation implication

This proves the offline pack is structurally sound and its constituent ROM/BIOS sections match their embedded CRCs; **it does not demonstrate** that the existing PERF2 SPC700/DSP emulation, `SOUND`, `SOU_TRN`, `DATA_SND` mapping or audio timing is correct. To validate that, the same embedded program and boot ROM must be executed against a known-good reference and their CPU/APU port traces compared.

In the absence of such dynamic equivalence tests, keep PERF1 untouched and treat the PERF2 audio branch as experimental. Do not ship this private copyrighted ROM or boot image in a public HMOD/repository.

## Auditoría específica de comandos de KOF96 (banco GB 04)

Verificado desde el contenido original (no por búsqueda imprecisa de bytes sueltos):

* ROM offset `0x10000` y `0x10010`: `MASK_EN` ($17).
* ROM offset `0x10020`, `0x10030`, `0x10040`: `MLT_REQ` ($11).
* ROM offsets `0x10050` a `0x100C0`, a pasos de 16: ocho `DATA_SND` ($0F), 11 bytes cada uno, dirigidos al banco SNES 00 y direcciones descendentes $085D, $0852, $0847, $083C, $0831, $0826, $081B, $0810.
* ROM offsets `0x103C8` y `0x103DA`: `CHR_TRN` ($13).
* ROM offset `0x103EC`: `PCT_TRN` ($14).

**Importante:** estas ocho transferencias `DATA_SND` coinciden con los paquetes genéricos de inicialización del SGB publicados en el *Game Boy Programming Manual* (bloques INIT1–INIT8). El nombre `DATA_SND` no significa que esos ocho bytes/payloads sean música o muestras del SPC: aquí parchean código del lado SNES. No confundirlos con `SOU_TRN`, que sí carga memoria de audio SPC700.

En la tabla de inicialización anterior **no aparecen paquetes `SOUND` o `SOU_TRN`**. Eso no demuestra que el juego jamás los genere dinámicamente: para afirmar tal cosa se necesita registro de comandos en ejecución.

El manual describe que `SOU_TRN` completa su transferencia **seis cuadros después** del cuadro del comando; se corrigió la espera anterior de un cuadro. También se corrigió la decodificación de `DATA_SND`/`DATA_TRN`: bytes 1–2 = dirección SNES LE, byte 3 = banco. Fuente externa: Nintendo *Game Boy Programming Manual*, capítulo 6, entradas DATA_SND y SOU_TRN.

Los cambios de sincronización SPC quedan con ajuste de frecuencia limitado a ±0.5 % (no a variaciones enormes del ritmo del juego). Esto sigue siendo una hipótesis de corrección acústica, no una medición de calidad real.
