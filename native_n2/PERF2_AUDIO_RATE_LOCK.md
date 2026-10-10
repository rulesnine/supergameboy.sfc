# PERF2: corrección del desbordamiento de audio / Rate Lock

## Origen: segunda prueba real de PERF2 Parallel

Registro físico (2026-10-10), 120.01 s:

- 49.92 FPS promedio **incluye el arranque mediante BIOS**, que corre a ~23–25 FPS.
- Una vez entra el modo SGB directo, ~58–60 FPS.
- La reproducción de audio sigue mostrando ~32,450 cuadros estéreo/s generados para un ALSA de **32,040 Hz**.
- Al final: **14,575 cuadros de audio descartados**, 98 recuperaciones ALSA y 4,105 cuadros de vídeo tardíos (incluyendo el arranque).
- Los fallos de ALSA son mayoritarios durante el BIOS; en modo directo quedan pocos, pero crece la cola hasta casi llenar sus 8,192 cuadros.

### Causa identificada en el código

El `RunFrame()` GB del fork fijaba un cuadro completo de `70224` T-cycles por cuadro SGB. El controlador DRC de producción PCM utilizaba el llenado interno del APU **antes** de `S9xLandSamples()`. En el modo directo la salida drena ese búfer entero cada cuadro, de modo que el error contra el objetivo fijo del 12.5 % del búfer no mide el desfase real frente a ALSA. El integrador puede desplazar el reloj de muestreo hasta ±3 %, generando un exceso sostenido de muestras y saturando la cola externa.

### Corrección implementada (solo rama experimental)

- Con `IKCORE_SGB_PERF_AUDIO_RATE_LOCK`, sustituir esa realimentación interna por el reloj efectivo de muestreo:
  `pcm_clock_hz = round(70224 × 60.09881389744051) = 4,220,379`.
- El APU GB recibe **32,040 cuadros estéreo de PCM por segundo de emulación a 60.0988 FPS**; es el mismo valor que consume el ALSA real.
- Esto cambia **solo la temporización de salida PCM**, no los ciclos de las voces APU, los comandos SNES `SOUND`, el DSP SPC700, los estados del luchador, las paletas, el compositor RGB565 ni los cambios de marco.
- Durante el arranque **BIOS completo** permanece exactamente el comportamiento visual validado: no hay salto/recorte de fade ni modificación de su transición, y las recuperaciones ALSA de esa etapa aún pueden ocurrir.
- El hilo SPC700/DSP, su cola segura y el mezclador existente permanecen como estaban en PERF2 Parallel.
- Se sigue usando el búfer ALSA de 8,192 cuadros y su lógica de descarte solo como salvaguarda extrema; la corrección impide su saturación sostenida por una fuente PCM artificialmente acelerada, pero **no elimina todos los posibles descartes causados por picos**.

### Verificación

`python3 tools/test_audio_rate_lock.py` compara matemáticamente la producción de PCM y el consumo ALSA durante 1 s, 10 s, 120 s y 1 h; exige error acotado a aproximadamente un cuadro de vídeo incluso a 1 h. GitHub Actions compila el núcleo ARMv7, comprueba GLIBC 2.23 y empaqueta el HMOD.

**No es una medición de sonido ni de FPS de NES Mini.** Se requiere registro y escucha reales, sin confundir compilación con fidelidad SNES. Se conserva intacto el último candidato PERF2 Parallel #113 y la rama de audio anterior.

### Registro exclusivo

`/var/lib/hakchi/sgb-native-test/ikcore-perf2-ratelock.log`

Interpretación: comparar `audio/sec gen` contra `32040/s`, y `audio drop`/ocupación `ring` después del cambio a modo directo. La fidelidad final de instrumentos SPC y tiempo de comandos no queda automáticamente certificada al arreglar el desbordamiento.
