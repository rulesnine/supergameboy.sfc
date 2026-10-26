# Ik Core híbrido — Fase 2: puente SOU_TRN/SOUND y enlace SPC700

**Estado:** código integrado al árbol del proyecto y probado con fuentes sintéticas; compilación ARMv7 verificada por CI. **Todavía NO es una HMOD ejecutable, ni prueba de sonido SNES real**.

**Base inalterada:** `Ik Core #43` (`cba03acbd04d41fcadcf9c8c7be87126c3b5ce7e`).  
**Fuente mGBA fijada:** `1509d86028c7df2d844b590723a80b2978f49e7c`.  
**CI:** [Ik Core fase 2](https://github.com/rulesnine/supergameboy.sfc/actions/workflows/ikcore-mgba-sgb-audio-phase2.yml).

## Diagnóstico de código que motivó este cambio

La función `GBVideoWriteSGBPacket()` de mGBA reúne los paquetes SGB completos, pero las órdenes SNES `SOUND` (0x08) y `SOU_TRN` (0x09) no tienen un procesamiento nativo equivalente al de nuestro motor Ik Core. El caso por defecto abandona la función **antes** de notificar al renderizador software. Por ello, capturar SOU_TRN solamente en `GBVideoSoftwareRendererWriteSGBPacket()` hubiera fallado.

Se añadieron puntos de observación débiles a mGBA antes de ese retorno y, para la transferencia LCD, después de cada línea de 160 píxeles y cada fotograma. Así se mantiene la ejecución del núcleo Game Boy tal como la programó mGBA cuando el puente no está conectado.

## Implementaciones verificadas

1. **Reconocimiento de SOU_TRN:** en `GBVideoWriteSGBPacket` mediante `tools/patch_mgba_sou_trn_capture.py`. No altera los paquetes ni las paletas. El audio SNES original no se simula ni se sustituye por WAV.
2. **Captura LCD de 4096 bytes:** `native_mgba/ikcore_sou_trn_capture.c` reconstruye 2 bitplanes de 8 píxeles en el orden de tiles SNES, coherente con la rutina de PAL_TRN de mGBA y el decodificador de Ik Core #43. Utiliza solamente una trama capturada tras saltar seis finales de fotograma, de acuerdo con la solución previa #43; **esto aún debe contrastarse con juegos reales**.
3. **Seguridad:** solo se emite una transferencia al completar los 4096 bytes; evita ejecutar datos parciales, reinicios dobles o contenido residual de otra ROM. El reinicio limpia comandos y audio pendiente.
4. **Mensajes SNES SOUND:** `native_mgba/ikcore_sgb_packet_bus.c` remite órdenes 0x08 completas a una segunda cola independiente. Conserva la secuencia de comandos SGB para gráficos.
5. **FIFO ordenado:** `native_mgba/ikcore_sgb_audio_fifo.c` almacena SOUND (hasta 112 bytes) y SOU_TRN (exactamente 4096) con límite de 16 eventos y contador de rechazos. El orden real observado en test `SOUND → SOU_TRN → SOUND` se mantiene.
6. **Enlace con la API SPC:** `native_mgba/ikcore_spc_sink.cpp` contiene llamadas a **`S9xSGBPerfSoundCommand` y `S9xSGBPerfSouTrn`**, las dos funciones originales de Ik Core #43. El enlace se probó con símbolos simulados en C++, pero **no se ha enlazado todavía a la biblioteca Snes9x de #43 ni se ha reproducido su audio real**.
7. **Build ARMhf:** las fuentes se compilan junto al motor GB-only de mGBA; se archivan como `libikcore_sgb_audio_bridge_armhf_phase2.a` y se entregan como componentes de SDK, **no un paquete instalable**.

## Tests automáticos

- `tests/ikcore_sou_trn_capture_test.c`: espera seis cuadros, captura siguiente, bytes de bitplanes conocidos `55 33`, ocupa 4096, aborta una trama incompleta, reinicia.
- `tests/ikcore_sgb_audio_fifo_test.c`: SOUND/SOU/SOUND en orden; rechaza longitud incorrecta, desbordamientos y destinatario ausente.
- `tests/ikcore_spc_sink_test.cpp`: el adaptador C++ envía SOUND y SOU_TRN una vez y en el orden correspondiente, usando funciones simuladas con firmas del motor #43.
- Pruebas previas de fase 1: cartucho GB sintético (240 cuadros y entrega de muestras GB), compilación de motor GB en x86 y ARMv7, control ABI de GLIBC 2.23.

## Aún no demostrado

- Que el nuevo motor GB reproduzca las mismas órdenes en el instante correcto de un juego comercial; el cartucho automático es sintético.
- Que el SP700/DSP **real** ejecute los bloques SOU_TRN recibidos; falta integrar el despachador a la llamada por fotograma de Ik Core con un solo GB CPU.
- Que el firmware SGB, el arranque y la presentación de marcos respondan fielmente. No hay aún máquina híbrida ejecutándose.
- Que Belmont's Revenge supere los 22–24 FPS de la #43, o que los sonidos SGB sean correctos en NES Mini. No extrapolar los FPS medidos en CI x86 al hardware ARM.

## Próximo trabajo técnico: fase 3

1. Sustituir el objeto GB original de Ik Core por la biblioteca ARMhf GB-only de mGBA sin CPU paralela; adaptar SRAM, controles, LCD 160×144, modelo de reloj SGB1 y comunicaciones del firmware.
2. Enlazar el despachador SPC de fase 2 con las funciones **reales** de Ik Core y su hilo SPC. Un solo productor GB; el hilo SPC recibe copias seguras de los eventos.
3. Reconciliar el estado PAL/ATTR/CHR/PCT y máscaras sin aplicar órdenes dos veces. Garantizar fidelidad en Castlevania Legends y KOF '96.
4. Sólo después compilar HMOD experimental independiente, no reemplazar #43. Un único test físico con métricas de CPU+PPU, render, mezclador GB y SPC700/DSP, audio, FPS y sincronización.

**Criterio de aceptación:** GB y SGB a la velocidad auténtica, audio SNES original sin cortes y con efectos N-SPC, compatibilidad SGBPACK y guardados; el número de HMOD no será incrementado hasta que haya una versión realmente instalable.

Fuentes de código: [rama de integración](https://github.com/rulesnine/supergameboy.sfc/tree/integracion/mgba-sgb-audio-fase2); [documentación fase 1](https://github.com/rulesnine/supergameboy.sfc/blob/integracion/mgba-gb-core-armv7-fase1/docs/FASE1_MGBA_GB_ARM.md); [mGBA MPL-2.0](https://github.com/mgba-emu/mgba/blob/1509d86028c7df2d844b590723a80b2978f49e7c/LICENSE).
