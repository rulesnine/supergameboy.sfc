# Ik Core — contrato de integración del audio SGB/SNES

## Evidencia física de KOF '96

En la NES Mini, HMOD experimental SGB Preview #26:
- Juego, marco SGB y paletas propias **correctos** según prueba visual del usuario.
- `play FPS: 59.73`, capacidad calculada ~240 FPS de trabajo (no rendimiento híbrido).
- Audio normal Game Boy **audible**; `written` ALSA ~31–32K muestras/s; sin `recover`.
- `SOUND=79` es un contador histórico que **agrupa** paquetes 0x08 (SOUND) y 0x09 (SOU_TRN), no 79 reproducciones DSP. Sin audio SNES mejorado.
- El objetivo final requiere SGBPACK1, sonido N-SPC, marcos, transiciones y ~60 FPS para GB monocromáticos y compatibles SGB; no otro mGBA sin SNES.

## Fuente existente reutilizable

La construcción Ik Core #117 incluye `tools/apply_sgbpack.py`, que modifica el núcleo Snes9x y aporta:
- `S9xSGBPerfAudioEnable`: conserva el DSP/SMP inicializado por la BIOS/firmware.
- `S9xSGBPerfSoundCommand(data,len)`: mapea `SOUND` a los cuatro puertos SNES APU: *port1 = data[1], port2 = data[2], port3 = data[3], port0 = data[4]*.
- `S9xSGBPerfSouTrn(data_4kb)`: carga bloques de sonido en APU RAM desde transferencia **de 4096 bytes**, no desde el paquete de 16 bytes.
- `S9xSGBPerfAudioFrame()`: avanza el reloj SMP/DSP de forma independiente del motor GB en modo directo.
- La variante paralela del código incluye una cola FIFO de comandos, confirmación de eco de puertos y fase de reposo para permitir repetir efectos idénticos (sonido de máquina de escribir de KOF '96).
- Estas funciones son parte del Snes9x modificado, **no del mGBA actual**. No están inicializadas ni conectadas en el HMOD #26.

## Fronteras de responsabilidad

**mGBA:** único CPU GB, Game Boy APU, PPU/framebuffer 256×224 SGB ya validado, temporización de controles y contador. Emite paquetes JOYP mediante `ikcore_mgba_sgb_packet`.

**Puente:** `ik_sgb_bridge`, `ik_sgb_mgba_telemetry` y `ik_sgb_spc_route` conservan bytes y orden; distinguen `0x08 SOUND` de `0x09 SOU_TRN`. El callback del backend debe copiar contenido o procesarlo de forma segura sin bloquear el hilo mGBA. Si falta inicialización SPC, **no se debe afirmar reproducción**, duplicar GB audio ni fabricar efectos artificiales. Para `SOU_TRN`, mGBA debe facilitar el contenido LCD completo 4 KiB con su timestamp.

**Backend SNES:** inicializa realmente N-SPC con el firmware/pack aportado por el usuario, deja el GB interno de la ruta Snes9x fuera de la ejecución normal, entrega SOUND/SOU_TRN, avanza el reloj SPC y proporciona exclusivamente PCM SPC al mezclador. No lanzar dos CPUs GB a la vez ni confundir audios.

**Mezcla:** sumar GB APU (mGBA) y SPC700/DSP SNES con formato/rate compatible y limitación saturada, conservando audio físico ya estable; controlar overflow, drift, transición y handshake. Un simple `S9xMixSamples` del core antiguo puede incluir audio GB duplicado: verificar antes de usarlo.

## Criterios verificables para un HMOD híbrido

1. `SPC initialized=1` registrado **después del boot firmware**, no supuesto.
2. `SOUND received` y `SOUND delivered` por separado; para KOF '96 confirmar comandos re-disparados y eco/ack.
3. `SOU_TRN` 4 KiB capturados/entregados, con rechazo si incompletos.
4. Sonido SNES realmente audible y fiel, especialmente voz/sonido de escritura.
5. El marco, paletas y transiciones del juego siguen igual que en #26.
6. `play FPS` cerca de 60 en hardware con audio GB + SNES y sin `ALSA recover`.
7. `SGBPACK1` y juegos GB sin mejoras compatibles en el mismo lanzador, sin comprometer GBC exclusivos que el SGB original no ejecuta.
8. Sin reemplazo de HMOD #43 ni dependencia de RetroArch.

## Estado actual

Se añadieron interfaces y pruebas `experimental/fase5/ik_sgb_spc_route.{h,c}` y `test_ik_sgb_spc_route.c`: prueban el paso exacto de SOUND al callback y que SOU_TRN exige 4096 bytes. **Esto no inicializa el DSP ni constituye el backend de audio SNES**. La próxima compilación física deberá incluir backend iniciado realmente y mezcla PCM; no distribuir otro HMOD solo de contadores.
