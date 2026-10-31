# Ik Core Fase 5 — NES Mini física: mGBA ARMv7 #9

Fecha: 2026-10-30 (hora México). Datos procedentes de la salida de terminal aportada por el usuario. No equivale a prueba del híbrido completo.

## Resultado

- 59.73 FPS *medidos en la ejecución limitada por el frontend*, estable en las últimas diez muestras.
- Capacidad de trabajo estimada 155.78 → 156.33 FPS, calculada por `run_frames / g_work_seconds`; **no es velocidad gráfica observada**, ni predicción de velocidad del híbrido SGB/SPC700.
- 27 paquetes SGB observados por el *packet tap* de mGBA 0.10.5.
- 5 paquetes de tipos relacionados con transferencias (`TRN=5`): cuenta eventos, **no** prueba la entrega de 4 KiB ni la calidad del marco SGB.
- `SOUND=0` durante las observaciones: no se capturaron comandos SOUND/SOU_TRN; sin evidencia de los efectos del SNES.
- `cycles=0`: problema de instrumentación en el tap original (`gb->timing.globalCycles` no aporta timestamp válido). Cambiado a `mTimingCurrentTime(&gb->timing)`; verificación física todavía pendiente.
- APU Game Boy producía `gen=32619–33129/s`, pero `written=0/s`, `ring=0` y `recover=0` durante las últimas diez muestras. Esto encaja con `g_alsa_ready=0`, por ejemplo si falló `dlopen` o `snd_pcm_open/set_params` al iniciar; requiere las líneas **ALSA** del *mismo log* para identificar la causa. **No declarar salida de audio funcional**.

## Diagnóstico no intrusivo recomendado

```sh
f=$(ls -t /var/lib/hakchi/sgb-native-test/ikcore-fase5-mgba-*.log | head -n 1)
grep -n -E 'ALSA|asound|snd_pcm|audio path|ERROR' "$f" | head -n 40
```

La rutina existente `init_alsa()` intenta `default` y `hw:0,0`; cualquier otro cambio de rutas, dispositivo o parámetros debe responder al error exacto, no hacerse a ciegas.

## Siguiente objetivo técnico

1. Corregir inicialización y envío de audio GB a ALSA en el HMOD mGBA aislado, *sin alterar el core #43*.
2. Enlazar el tap mGBA con la cola real ICD2/firmware y transferencias de vídeo/VRAM. El seam en Snes9x es experimental y **no está enlazado al mGBA actual**.
3. Integrar efectos SNES N-SPC/SPC700/DSP y validar cadencia/reloj/sincronización.
4. Medir rendimiento y fidelidad bajo carga conjunta, incluida la transición de marco y el juego, sin extrapolar los 156 FPS de la línea base.

## Versiones

El HMOD de la prueba fue `IkCore-Fase5-mGBA-BASELINE-9.hmod`, construido en GitHub Actions run 41164481773. La versión estable #43 se preserva.
