# Ik Core híbrido — Fase 5: arranque SGB auténtico de CPU Game Boy mGBA

**Alcance:** módulo de arranque GB-side dentro del ejecutable combinado ARMhf Snes9x+mGBA, con prueba funcional x86 y compilación ARM. **NO es una HMOD ni demuestra arranque completo con BIOS SNES.** La base #43 sigue intacta.

## Problema resuelto parcialmente

La Fase 4 colocó mGBA y Snes9x en un mismo ELF, pero el motor GB de mGBA se mantenía dormido. Arrancarlo *después* de que el emulador GB original haya ejecutado la BIOS SGB causa una regresión de estado: la CPU del cartucho, VRAM, WRAM, temporizadores y MBC de mGBA se reiniciarían mientras el firmware SNES/SGB conserva otro estado.

La nueva API permite crear **mGBA desde el primer ciclo Game Boy**, iniciando la ROM de arranque SGB1 con **PC=$0000**, sin trasplantar arbitrariamente estados entre emuladores.

## Cambios implementados

- `native_mgba/ikcore_mgba_gb_host.h/.c`: nueva función `ikcore_mgba_open_sgb_boot(rom,rom_len,boot_256,256)`; copia internamente ROM y bootstrap. Configura modo SGB, carga la BIOS mediante `mCore::loadBIOS`, desactiva `skipBios` y exige que el primer PC sea cero. Si falta la BIOS, tiene longitud incorrecta o no es compatible, la ruta **falla sin pasar silenciosamente a DMG**.
- `native_mgba/ikcore_mgba_combined_phase4.cpp`: exporta `ikcore_mgba_phase5_prepare_boot` y `ikcore_mgba_phase5_boot_pc`. La nueva entrada opera sobre el mismo núcleo GB mGBA que la fase 4 y preserva el audio de Snes9x; **no hay activación automática dentro de la ruta SGB de Hakchi**.
- `tools/patch_mgba_sameboy_sgb_boot.py`: acepta *únicamente* la BIOS SGB1/SGB2 de reemplazo libre incluida en la versión fijada de Snes9x (derivada de SameBoy, licencia Expat/MIT); comprueba tamaño y CRC32 de 256 bytes. No relaja los controles de otros firmwares y mantiene intacta la ruta de BIOS estándar de mGBA. Para pruebas, la BIOS se extrae temporalmente a archivos locales que **no se incluyen en los paquetes distribuidos**.
- `tests/ikcore_mgba_sgb_boot_test.c`: ejecuta la BIOS SGB1 real en una ROM GBX sintética. Verifica el primer PC, el tamaño estricto de la BIOS, la ejecución de 30 fotogramas y que la CPU abandona PC cero.
- `.github/workflows/ikcore-mgba-sgb-boot-phase5.yml`: compila el motor GB-only mGBA para ARMv7/GLIBC 2.23, valida la secuencia de arranque en x86 y crea el ELF combinado SNES/mGBA. Comprueba los dos símbolos exportados de fase 5.

## Qué sí valida la prueba

1. La ROM SGB1 libre de SameBoy es aceptada por la ruta de BIOS mGBA expresamente aprobada.
2. La CPU GB de mGBA inicia en `PC=0x0000`, en lugar de comenzar el cartucho en `PC=0x0100`.
3. El núcleo procesa 30 frames de CPU/video/audio sin excepción.
4. El ELF ARMv7 contiene Snes9x + mGBA + API de arranque SGB (validación de ELF/ABI, sin consola).

**Qué NO se ha probado todavía:** el handshake ICD2 con el BIOS SNES; finalización efectiva de la secuencia de arranque hasta el cartucho; captura y ejecución del programa SOU_TRN por la APU SNES real; fidelidad 100 % de los efectos SNES; sincronización audio+video; velocidad en Belmont's Revenge/KOF '96/Castlevania Legends; SRAM migrada y suspensión. No inferir éxito por el mero hecho de procesar 30 frames.

## Siguiente integración segura

La fase siguiente debe conectar las lecturas/escrituras **ICD2** entre mGBA y el sistema SGB del SNES durante el mismo reloj, sin hacer avanzar la CPU original Snes9x/GB. El BIOS SNES depende de recibir el protocolo de inicio y de que su respuesta llegue al GB de mGBA. Se verificará primero mediante trazas deterministas y ROM sintética, después con firmware proporcionado legalmente por el usuario y sin distribuirlo.

Una vez terminado el protocolo ICD2, se deberá integrar el framebuffer, el estado de paletas/marco en un único dueño y la mezcla PCM de GB + SPC700/DSP, conservando estrictamente la versión #43. Solo entonces elaborar una HMOD experimental separada para pruebas físicas.

**Licencias:** mGBA/MPL-2.0, Snes9x/licencia del proyecto, SameBoy/Expat-MIT. Los archivos ROM/BIOS propietarios y los 256 bytes libres de prueba no se publican en este SDK.

[Consultar rama Fase 5](https://github.com/rulesnine/supergameboy.sfc/tree/integracion/mgba-arranque-sgb-fase5) · [Consultar CI Fase 5](https://github.com/rulesnine/supergameboy.sfc/actions/workflows/ikcore-mgba-sgb-boot-phase5.yml).
