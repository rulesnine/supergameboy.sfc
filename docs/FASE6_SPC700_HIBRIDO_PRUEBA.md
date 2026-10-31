# Ik Core Fase 6: primera integración híbrida real de audio SPC700/DSP

**Estado:** compilación experimental; todavía sin validación física. La ruta SGB #26 (juego, paletas, marco y audio GB) permanece separada.

## Arquitectura

- **mGBA 0.10.5**: único motor de CPU/PPU/APU Game Boy durante gameplay; cuadros de 256×224 y comandos SGB propios.
- **Snes9x modificado por Ik Core #117**: segundo módulo dinámico **exclusivamente para arrancar una vez el SGBPACK1** e inicializar el N-SPC. Después de `IKSPC initialized=1`, su función libretro `retro_run` **ya no se llama**; se avanza únicamente el SPC700/DSP mediante `ikcore_spc_frame`.
- **Puente SOUND**: paquetes JOYP originales de mGBA se encolan y se envían por `ikcore_spc_send_sound` a los cuatro puertos de APU/CPU del #117. `SOUND received` y `sent` deben medirse por separado.
- **SOU_TRN**: captura de los 4096 bytes reales en el renderizador mGBA (tile-major 2bpp) y entrega al código `S9xSGBPerfSouTrn` original; se rechazan capturas incompletas.
- **Mezclador**: muestras GB mGBA + SPC retiradas de `S9xPullSpcOutput` con limitación saturada; una sola salida ALSA. Primeros niveles conservadores GB ×0.8 y SPC ×0.7; habrá que comparar con grabación de referencia.
- **Aislamiento**: `/usr/lib/ikcore-fase6/` y `/bin/ikcore-fase6-hybrid`. NO sobrescribe #26 ni #43, ni el lanzador histórico.

## Requisitos para la prueba física

El HMOD no contiene ningún archivo de juego ni firmware. Deben existir en la NES Mini **dos archivos pertenecientes al mismo juego**:
1. Cartucho GB sin comprimir: `/ruta/KOF96.gb` (motor mGBA).
2. Paquete SGBPACK1 compatible ya validado: `/ruta/KOF96_SGBPACK.sfc` (solo inicialización de firmware/audio SNES).

Lanzamiento:

```sh
/bin/ikcore-fase6-hybrid "/ruta/KOF96.gb" "/ruta/KOF96_SGBPACK.sfc"
```

Se acepta la ruta SGBPACK1 histórica `/var/lib/hakchi/sgb-native-test/KOF96_SGBPACK_v1_REUPLOAD.sfc` si no se da segundo argumento. Es importante usar un paquete válido: un archivo `.sfc` genérico no funciona como SGBPACK1.

Durante el arranque puede haber espera de firmware y mensajes `IKSPC firmware boot frames=...`; el módulo usa hasta 4800 frames de emulación para encontrar la inicialización. Si la inicialización fracasa, el juego GB sigue corriendo con audio GB normal y el registro indica `IKSPC initialized=0`, **no** se inventa sonido SNES.

## Diagnóstico

```sh
f=$(ls -t /var/lib/hakchi/sgb-native-test/ikcore-fase6-hybrid-*.log | head -n 1)
grep -E 'IKSPC|IKMGBA SGB|ALSA|play FPS|audio/sec' "$f" | tail -n 50
```

Los criterios útiles son `IKSPC initialized=1`, `SOUND sent>0`, `SOU_TRN transfer_done>0` cuando el juego envía transferencias, `SNES_PCM_mixed>0`, `ALSA recover=0` y velocidad física cerca de 60 FPS. **La cifra de PCM mezclado no acredita fidelidad sonora por sí sola: escuchar los efectos de KOF '96 es imprescindible.**

## Límites y riesgos

- Es una **primera integración real experimental**: no validada en NES Mini ni afirmada como estable.
- La inicialización del segundo núcleo consume tiempo y memoria adicionales; no se garantiza rendimiento hasta probarla.
- Las transferencias SGB deben comprobarse sobre títulos que las usen; aunque el decodificador mGBA se haya extendido, puede haber diferencias de temporización o filas del LCD en juegos concretos.
- Las transiciones de arranque del firmware siguen siendo de la ruta separada de audio, no se muestran en vídeo mGBA; la unificación visual SGBPACK1 completa queda pendiente.
- La frecuencia SMP por frame proviene de #117 y puede necesitar ajustes finos para el ritmo de 59.73 FPS del Game Boy, sin modificar el reloj del juego.
- Compatibilidad universal de GB/SGB exige más títulos de referencia y no se deduce de KOF '96.
