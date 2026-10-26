# Ik Core NES Mini — arquitectura híbrida mGBA GB + SPC/DSP Ik Core

**Estado:** auditoría técnica de viabilidad, no versión ejecutable ni rendimiento demostrado.  
**Base preservada:** Ik Core #43, `cba03acbd04d41fcadcf9c8c7be87126c3b5ce7e`.  
**Problema confirmado:** *Castlevania II: Belmont's Revenge* 22–24 FPS en #43 y v50; 19.9–20.7 FPS en v51; ningún mensaje `IKDISPLAY51` en última prueba.  
**No distribuir ROMs, boot ROMs ni firmware propietario.**

## Decisión

**Sí es técnicamente viable** construir un único lanzador Ik Core que use el núcleo GB de mGBA (CPU SM83, mapa de memoria, MBC, temporizadores, PPU y APU GB) y conserve Ik Core/Snes9x para el subsistema Super Game Boy/SNES (BIOS, audio SPC700/DSP, comandos, marcos, paletas y Clover/Hakchi). **60 FPS reales en NES Mini no están demostrados hasta ejecutar el híbrido en hardware.** No prometer velocidad sin medir el presupuesto completo.

No colocar dos CPU GB ejecutándose al mismo tiempo, ni simular audio SPC con samples estáticos. No ejecutar un `retroarch-clover mgba` adicional debajo de Ik Core; el motor mGBA debe incorporarse como biblioteca con integración de tiempo y comandos, sin frontend ni doble framebuffer.

## Hallazgos sobre las fuentes

1. Ik Core/SuperSnes9x `sgb/sgb.cpp`: `Emulator::RunCycles` llama `impl_->cpu.Step(impl_->mem)` y este hace interleaving de máquina con `MemTick` -> `TimerStep`, `PpuStep`, `ApuStep`. Hay optimizaciones previas, pero el diseño aún exige gestión de estado por ciclo de máquina y render PPU propio.
2. mGBA `src/gb/core.c`: `_GBCoreRunFrame` llama `SM83Run` hasta avanzar el contador de cuadros. `src/gb/gb.c` emplea el programador `mTiming` y `GBProcessEvents`; `src/gb/video.c` programa eventos de modos PPU (OAM, transferencia, HBlank, VBlank), con dibujo por rangos. No atribuir toda la diferencia de FPS a esto sin perfilar.
3. mGBA `src/gb/video.c` implementa paletas y comandos SGB, pero otros comandos de SNES SOUND son tratados como no implementados en la ruta de vídeo actual. Ik Core conserva las llamadas SNES `S9xSGBPerfSoundCommand`, `S9xSGBPerfSouTrn` y el audio SPC700/DSP con cola de trabajos; **eso se preserva**.
4. En versiones experimentales #50/#51 no aparece telemetría de la ruta rápida para *Belmont's Revenge*. Los FPS han empeorado; no se deben hacer más parches ciegos del compositor.

## Componentes y propiedad de estado

| Subsistema | Motor responsable | Regla |
| --- | --- | --- |
| SM83 / WRAM / VRAM / MBC / cartucho / DMA | mGBA GB | Única fuente de verdad en ejecución |
| LCD GB, framebuffer y máscaras de sprite/capa | mGBA GB | Exportación del frame 160x144 y atributos necesarios |
| APU Game Boy (cuatro canales) | mGBA GB | PCM mezclado posteriormente, no duplicado por Ik Core |
| BIOS Super Game Boy y protocolo SNES/ICD2 | Ik Core SGB | Mantener comportamiento y secuencia de inicialización |
| SGB PAL/ATTR/CHR/PCT, marcos, paletas, MASK_EN | Adaptador y estado SGB de Ik Core | Comandos con ciclo/orden original, sin renderizadores superpuestos simultáneamente |
| SNES SOUND / SOU_TRN / SPC700 / DSP | Ik Core/Snes9x | Continuidad del hilo SPC, FIFO, ritmo y audio fiel |
| Video 256x224, Clover, joystick y guardados | Ik Core | Una sola salida y un solo control de sincronización |

## Puente que hay que implementar

- **GB host API:** `load_rom`, `reset`, `run_until_vblank`, `framebuffer`, `audio_samples`, `read_sram`, `save_state`. Adaptar `mCore` de mGBA en una biblioteca separada; no traer su UI.
- **Intercepción SGB:** Capturar paquetes completos en mGBA antes de su procesado normal (punto `GBVideoWriteSGBPacket`). Reenviar PAL_SET, PAL_TRN, ATTR_*, CHR_TRN, PCT_TRN y MASK_EN con sus transferencias 4 KiB y momento de VBlank correctos. Dejar una sola copia del estado final SGB (evitar double apply).
- **Audio SGB:** reenviar SOUND y SOU_TRN completos y en orden al sistema Ik Core existente, que alimenta SPC700/DSP. Mezclar el PCM GB de mGBA con el PCM SNES después de producir cada bloque, con control de niveles y tasa y sin audio extra duplicado.
- **Boot SGB:** no hacer hot-swap ciego entre dos motores a mitad de un juego. Diseñar el adaptador para un solo GB core desde arranque y dejar que el firmware SGB y su SNES reciban la señal/paquetes que esperan; emular ICD2 con sincronización comprobada. Conservar la implementación de boot de #43 como referencia comparativa.
- **Clocking:** transportar eventos en ciclos GB, sincronizados al reloj del SGB1/SNES (la velocidad SGB1 difiere de GB ordinario). No igualar falsamente un frame GB a 60.000 fps ni sacrificar frames/audio para exhibir un contador de 60.
- **Guardados:** almacenamiento SRAM original se conserva. Los save states tendrán identificación de nuevo motor y versionado; los estados nativos de #43 no son compatibles automáticamente.
- **Legalidad:** código mGBA bajo MPL-2.0; conservar avisos, fuentes correspondientes y separación de archivos. Verificar distribución combinada con licencia Snes9x, que puede imponer condiciones adicionales. No incluir dumps ni BIOS cerrados.

## Orden de construcción y pruebas — minimizar ciclos en la NES Mini

1. **Prueba automática sin audio SNES:** compilar sólo el GB core mGBA para ARMv7 con entrada ROM propia/fixture permitido, salida mínima 160x144 y audio GB. Comparar hashes de frames, SRAM, controles y tiempo de ejecución con la versión actual. Correr ensayos sintéticos y perfiles de CPU en CI antes de pedir pruebas en hardware.
2. **Integración del puente:** incorporar motor mGBA como módulo interno con trazas de paquetes, frame, estado, tiempo y sonido. Deben pasar tests de orden PAL_SET/ATTR/PCT/CHR y compatibilidad con datos autorizados por el usuario.
3. **Integración SPC/DSP:** un único hilo de audio SNES existente y muestras GB de mGBA, comprobando SOU_TRN, SOUND, fading, continuidad, velocidad de reproducción y 0 duplicaciones.
4. **ÚNICA prueba de aceptación en NES Mini:** distribuir un HMOD experimental separado, con un sólo nombre de versión (sin número de build confundible), sin tocar #43. Recoger mediciones automáticas desglosadas `GB CPU+PPU`, `SPC/DSP`, `composición`, `presentación`, `audio`, `frame wall time` y `FPS real`; no pedir múltiples instalaciones para ajustar una sola condición booleana.
5. **Regresión:** Belmont's Revenge (GB clásico), Castlevania Legends (SGB), KOF96 (SGB + SOUND), marcos, transiciones, botones, SRAM, salida a Clover. **No publicar como estable** sin comprobar todos y sin ver tiempo completo de audio y vídeo a velocidad del hardware original.

## Criterio de éxito

- 100 % de velocidad emulada respecto a la consola objetivo, sin repetir ni saltar fotogramas como mecanismo para esconder falta de potencia.
- El audio GB y los efectos SPC/DSP SNES fieles, sincronizados, sin cortes y sin perder comandos SGB.
- Compatibilidad con entradas SGBPACK existentes sin ROM alteradas.
- Capacidad de trabajo con margen suficiente para el compositor y sonido dentro del presupuesto de NES Mini; 60 FPS indicados sólo si la medición real lo confirma.
- #43 permanece instalada e intacta durante toda la integración.

## Referencias de código

- mGBA: `https://github.com/mgba-emu/mgba/blob/master/src/gb/core.c`, `src/gb/gb.c`, `src/gb/video.c`; `https://github.com/mgba-emu/mgba/blob/master/LICENSE`.
- Ik Core: `https://github.com/rulesnine/supergameboy.sfc/tree/optimizacion/castlevania-compositor-audio-43` (estable de pruebas #43). Basado en SuperSnes9x/Snes9x.
- mGBA issue audio mejorado: `https://github.com/mgba-emu/mgba/issues/3492`.
