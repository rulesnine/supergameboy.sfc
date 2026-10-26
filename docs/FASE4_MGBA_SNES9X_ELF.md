# Ik Core híbrido — Fase 4: enlazar mGBA y el SNES/SPC700 real

## Objetivo

Crear **un mismo núcleo libretro ARMv7 ELF de Snes9x/SuperSnes9x** con:
- el arranque original SGB/SNES de Ik Core;
- su CPU y APU SNES ya validadas, incluidos SPC700/DSP, BRR y resampler;
- el motor mGBA **solo GB**, compilado para la misma ABI ARMhf/GLIBC 2.23;
- el puente SOUND/SOU_TRN hacia las funciones `S9xSGBPerfSoundCommand` y `S9xSGBPerfSouTrn` existentes;
- una API de ejecución Game Boy mGBA, **desactivada por defecto**.

Esta etapa no debe generar una HMOD hasta probar que la SNES Mini/NES Mini ejecuta correctamente el núcleo completo con audio.

## Fuentes y compatibilidad

- Ik Core/SuperSnes9x a partir de `shanytc/snes9x`, commit `183e03e5efed3b6d450385c98e2ccffb194153c3`, aplicando las mismas tres transformaciones que la compilación estable #43: `apply_sgbpack.py`, `fix_sgb_lcd_palette_transfers.py` y `optimize_sgb_compositor.py`.
- mGBA: `mgba-emu/mgba` commit `1509d86028c7df2d844b590723a80b2978f49e7c`, bajo MPL 2.0. El paquete no debe incorporar código ni BIOS propietarios.
- mGBA se compila mediante `LIBMGBA_ONLY=ON`, `M_CORE_GB=ON`, `M_CORE_GBA=OFF`, `CMAKE_POSITION_INDEPENDENT_CODE=ON` y ARMhf hard-float para cortex-a7.
- `ikcore_mgba_gb_host.c` se compila usando **exactamente las definiciones `C_DEFINES` de mGBA generadas por CMake**. Sin este requisito, `mCore::config` tiene un desplazamiento incorrecto y se produce un cierre inesperado, ya diagnosticado y corregido en la fase 3.

## Módulos incorporados al mismo ejecutable

`native_mgba/ikcore_mgba_combined_phase4.cpp` se enlaza dentro de `supersnes9x_libretro.so`, junto a la biblioteca estática GB-only y el puente SGB/SPC. Define:
- `ikcore_mgba_phase4_link_probe()`: valida la presencia básica de ABI sin arrancar una segunda CPU.
- `ikcore_mgba_phase4_prepare(rom,bytes)`: abre una copia de la ROM en el único núcleo GB de mGBA, **solo bajo llamada explícita**.
- `ikcore_mgba_phase4_run_one_frame(pad)`: avanza ese núcleo **una vez**; mapea el control SNES a GB conforme al mismo `SetJoypad` de Ik Core #43 y despacha los comandos SGB al SPC real **solo cuando este está activo**.
- `ikcore_mgba_phase4_latest_frame()`: presenta puntero y metadatos del último framebuffer y PCM, aún sin reemplazar el renderizador actual.
- `ikcore_mgba_phase4_stop()`: destruye el núcleo GB experimental y limpia el FIFO antes de descargar la biblioteca.

`tools/patch_ikcore_mgba_combined_phase4.py` incorpora este puente a las fuentes parcheadas de Snes9x, agrega el objeto al Makefile de libretro y conserva el ABI `retro_*`. Se exportan únicamente los símbolos opcionales `ikcore_mgba_phase4_*`, necesarios para las siguientes pruebas.

## Punto técnico pendiente: migración de estado de la CPU Game Boy

**No es seguro reemplazar la CPU GB original una vez que el BIOS SNES haya terminado.**

El juego Game Boy ya habría ejecutado instrucciones: si arrancamos mGBA desde la dirección inicial en ese momento, se reinician su CPU, RAM, VRAM, mapper, temporizador y sonido mientras el marco y el SPC del SNES están en otro estado. Esto produciría secuencias repetidas y posibles fallos, incluso si la biblioteca está correctamente enlazada.

Para evitar esta discrepancia hay dos enfoques correctos. El preferible es usar **mGBA como única CPU GB desde antes del arranque**, con el BIOS SGB libre y el adaptador ICD2 suministrando los paquetes al BIOS SNES. La alternativa es implementar una transferencia exacta del estado completo de la CPU original al mGBA en el momento del handoff; resulta sustancialmente más compleja y requiere reconciliar estructuras de memoria y temporización.

No se habilita el cambio hasta escoger e implementar una de esas rutas y pasar las pruebas reproducibles.

## Otra integración pendiente

- Vídeo: un único estado SGB para `PAL/ATTR/CHR/PCT/MASK_EN`; no mezclar simultáneamente el compositor viejo con el nuevo. Preservar el marco de 256×224, el viewport 160×144 y la paleta original.
- Audio GB: mGBA produce PCM a su frecuencia interna (131072 Hz en la configuración actual); necesita un remuestreador de fase estable para la salida SNES alrededor de 32040 Hz, mezclado sin saturaciones con el SPC700/DSP. El audio SNES mejorado debe continuar exactamente desde el estado del firmware.
- SRAM y RTC: no trasplantar automáticamente savestates de CPU distintas; preservar la SRAM existente mediante migración validada.
- Cronometría: comparar trabajo por cuadro, render, sonido SNES, GB APU, sincronización y repetición real en Castlevania II: Belmont's Revenge, Castlevania Legends y KOF '96.

## Criterios de validación y límites

- [ ] Un único ELF ARMhf con funciones mGBA y Snes9x/SPC resueltas y ABI GLIBC <=2.23.
- [ ] Arranque nativo Game Boy y SGBPACK1 en el mismo núcleo sin segundo emulador GB.
- [ ] Comandos JOYP y transferencias de audio originales a la APU SNES real.
- [ ] Border, fade, color, menús y salida 256×224 equivalentes a la versión estable.
- [ ] Audio completo GB+SNES a velocidad y tono correctos.
- [ ] FPS medidos en la NES Mini sin degradación ni pérdida de sonido.

**Mientras no se cumplan estas etapas, fase 4 es un build técnico, NO una versión estable, y #43 debe permanecer intacta.**

Código: [rama fase 4](https://github.com/rulesnine/supergameboy.sfc/tree/integracion/mgba-snes9x-enlace-fase4).  
CI: [flujo ARMv7 combinado](https://github.com/rulesnine/supergameboy.sfc/actions/workflows/ikcore-mgba-combined-phase4.yml).
