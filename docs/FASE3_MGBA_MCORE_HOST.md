# Ik Core híbrido — Fase 3: ejecutor único Game Boy mGBA (`mCore`)

**Estado:** fase 3 **parcial y funcional en entorno de pruebas x86**; biblioteca ARMv7 compilada; NO es un emulador combinado con SNES/SPC ejecutándose en NES Mini y NO es una HMOD.  
**Base estable preservada:** Ik Core #43 (`cba03acbd04d41fcadcf9c8c7be87126c3b5ce7e`).  
**Fuente mGBA fijada:** `1509d86028c7df2d844b590723a80b2978f49e7c` (MPL-2.0).  
**CI de fase 3:** [GitHub Actions](https://github.com/rulesnine/supergameboy.sfc/actions/workflows/ikcore-mgba-mcore-phase3.yml).

## Implementaciones

1. `native_mgba/ikcore_mgba_gb_host.c/.h` — host ABI en C que ejecuta **UNA SOLA CPU Game Boy: SM83 de mGBA**. Abre la ROM en memoria, ofrece modo DMG y modo SGB, ejecuta `mCore::runFrame`, exporta framebuffer 160×144 o 256×224 cuando corresponde, controles Game Boy, audio PCM estéreo, contador de cuadros y duración del trabajo.
2. `ikcore_mgba_clone_sram` / `ikcore_mgba_restore_sram` — adaptadores a la API SRAM de mGBA. El fixture automatizado no usa batería ni SRAM y por ello solo demuestra que la operación de consulta no falla; las restauraciones reales permanecen pendientes.
3. `native_mgba/ikcore_sgb_packet_bus.c`, `native_mgba/ikcore_sou_trn_capture.c`, `native_mgba/ikcore_sgb_audio_fifo.c` — conserva los comandos de sonido y los datos LCD SGB de 4096 bytes de la fase 2; no reinterpreta ni cambia el firmware.
4. `native_mgba/ikcore_spc_sink.cpp` — puente preparado para llamar a `S9xSGBPerfSoundCommand` y `S9xSGBPerfSouTrn` **reales de Ik Core #43**, todavía pendiente de enlazar en el ejecutable híbrido Snes9x definitivo.
5. CMake mGBA GB-only cross-compilado con `-DCMAKE_POSITION_INDEPENDENT_CODE=ON`, para habilitar el enlace del núcleo GB a una biblioteca compartida de Ik Core sin relocalizaciones inválidas en ARM.
6. **Corrección crucial de ABI:** el primer ejecutor se cerraba durante `mCoreConfigInit` porque la estructura `struct mCore` cambia según `ENABLE_VFS`, `ENABLE_DIRECTORIES`, `MINIMAL_CORE`, etc. Los archivos del host se compilan ahora **con todas las `C_DEFINES` del mismo objetivo mGBA**, extraídas del `flags.make` generado por CMake. El fallo desapareció tanto en la prueba DMG como en la SGB.

## Pruebas x86 verificadas

| Validación | Resultado |
| --- | --- |
| ROM sintética GBX original, sin logo ni boot ROM propietario | Aprobada |
| `mCore` Game Boy clásico, sin procesador duplicado | 240 fotogramas ejecutados |
| `mCore` en modo Super Game Boy | 24 fotogramas ejecutados |
| Captura de vídeo y audio PCM GB del mismo motor | Aprobada |
| Apertura y cierre repetidos de motor, sin cierre inesperado | Aprobada |
| Simulación SGB de transferencia `SOU_TRN` 4096 B a través de LCD | Tests sintéticos aprobados |
| FIFO ordenado SOUND y SOU_TRN + puente de firmas C++ | Tests sintéticos aprobados |
| ROM sintética con instrucciones SM83 y señales JOYP que envían `SOUND` | `general=1, audioEvents=1, dispatched=1`, una sola entrega |
| Sonido audible SPC700/DSP con firmware SNES original | **NO probado** |
| Emulador SGBPACK híbrido completo y juego comercial | **NO implementado aún** |
| Rendimiento NES Mini en Belmont's Revenge | **No medido** |

La prueba de `SOUND` es distinta a las pruebas de unidad anteriores: realmente ejecuta código Game Boy que escribe bits en JOYP (registro FF00) con el modelo SGB, mGBA reúne los 16 bytes, y la cola Ik Core recibe exactamente un evento. Es un avance real de integración, pero **el test consume el evento mediante una función simulada, no mediante la APU SNES real**.

## Compatibilidad y rendimiento

- La compilación para ARMv7 usa un sysroot Xenial/GLIBC 2.23 y toolchain ARMhf compatible con las bibliotecas antiguas de la NES Mini. Un contenedor `libmgba` de prueba demuestra el ABI ARM, pero el motor previsto para producción es **`libmgba.a` GB-only**, sin el código GBA ni la interfaz libretro.
- El `ikcore_mgba_gb_host_armhf.o` también queda archivado como biblioteca compilada PIC; esto **no prueba la velocidad real ARM en NES Mini**.
- El resultado de 0.14–0.24 ms por cuadro sintético en un runner x86 puede variar con carga del CI. No extrapolarlo a la NES Mini ni a juegos comerciales.
- La frecuencia de audio PCM Game Boy de mGBA se obtiene del propio núcleo, normalmente 131072 Hz. Todavía falta remuestrearlo y mezclarlo con los ~32 kHz del SPC/DSP existente de Ik Core manteniendo pitch y sincronización.

## Lo que sigue dentro de la fase 3

1. **Unión ejecutable SNES/GB**: enlazar el `mCore` GB-only y los tres componentes SGB de fase 2 a una sola biblioteca del frontend Ik Core, sin ejecutar en paralelo el GB CPU original del Snes9x. Integrar la lectura de ROM Game Boy extraída de SGBPACK1 preservando datos.
2. **Conexión SNES/SPC real**: inicializar el firmware y la APU SNES originales con la arquitectura ya validada; despachar el FIFO de SOUND/SOU_TRN al worker SPC, mientras se mezcla el PCM mGBA sin duplicarlo.
3. **Vídeo completo**: integrar paletas/ATTR/CHR/PCT/MASK_EN y marcos SGB, usando una sola fuente del estado SGB y sin dobles compositores. El modo DMG no debe depender de que la ROM contenga paletas SGB.
4. **Control y guardados**: reutilizar entradas Hakchi y rutas SRAM compatibles, migrar estados de forma versionada (no son compatibles automáticamente con los del núcleo antiguo).
5. **Pruebas fuera de la NES Mini primero**: confirmar audio SPC mediante las bibliotecas reales, boot, paquetes SGB, salida completa 256×224 y perfiles CPU+PPU/mezcla/render. Solo después preparar **una única HMOD experimental** separada de #43.
6. **Aceptación en NES Mini**: *Castlevania II: Belmont's Revenge* sin SGB, *Castlevania Legends* con mejoras SGB, *KOF '96* (marcos, fondos y efectos SNES), 59.7 FPS Game Boy nominales sostenidos y audio fiel. No publicar como estable hasta demostrarlo.

**Precaución:** no se deben incorporar aquí ROMs comerciales, BIOS ni firmware de propiedad de Nintendo. La combinación de mGBA (MPL-2.0) y código derivado de Snes9x requiere conservar licencias y revisar compatibilidad de distribución.

## Fuentes

- [Rama de desarrollo Fase 3](https://github.com/rulesnine/supergameboy.sfc/tree/integracion/mgba-mcore-host-fase3)
- [Flujo CI Fase 3](https://github.com/rulesnine/supergameboy.sfc/blob/integracion/mgba-mcore-host-fase3/.github/workflows/ikcore-mgba-mcore-phase3.yml)
- [Documentación y resultados Fase 2](https://github.com/rulesnine/supergameboy.sfc/blob/integracion/mgba-sgb-audio-fase2/docs/FASE2_MGBA_SGB_SPC.md)
