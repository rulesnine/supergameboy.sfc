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

## Corrección después del primer lanzamiento fallido (compilación #15)

En la consola se intentó `/bin/ikcore-fase6-hybrid "/ruta/KOF96.gb" ...`: `/ruta/KOF96.gb` era **texto de ejemplo**, no una ruta existente. El módulo #10a salió antes de inicializar cualquier motor (`runs=0`, `video frames=0`). No constituye un resultado de emulación ni una regresión de audio.

El contenedor SGBPACK1 **ya incluye la ROM Game Boy**. Desde la compilación F6 **#15**, el lanzador acepta **un solo archivo**:

```sh
ls -lh /var/lib/hakchi/sgb-native-test/KOF96_SGBPACK_v1_REUPLOAD.sfc
/bin/ikcore-fase6-hybrid "/var/lib/hakchi/sgb-native-test/KOF96_SGBPACK_v1_REUPLOAD.sfc"
```

Internamente el frontend valida magic/version/layout y CRC32 de las tres secciones y del conjunto, copia únicamente el contenido Game Boy en memoria y lo entrega al núcleo mGBA mediante el campo `retro_game_info.data`. La ruta SGBPACK1 original se utiliza también como fuente del firmware y del sonido SNES. **No crea ni distribuye una copia permanente de la ROM.** La ruta dual `.gb + .sfc` permanece soportada.

Se añadieron `experimental/fase6/ik_sgbpack_rom.c` y pruebas de contenedor sintético con rechazo por CRC, aprobadas en GitHub Actions run `41172685411`. Esto valida compilación e integridad del parser, pero todavía **no** comprueba la inicialización de N-SPC en hardware.

El ejecutable todavía incluye una línea heredada `core mode: mGBA ... no SNES SPC/DSP`, que describe solo el motor GB y no el backend separado. Para conocer el estado real del híbrido usar `IKSPC initialized` y `SNES_PCM_mixed`.


## Prueba física de KOF '96 — HMOD #21 (120 segundos)

Registro real facilitado por el usuario:
- \`play avg: 59.73 FPS\`, 7168 cuadros, \`work cap: 126.53 FPS\`, \`late frames: 0\`, resolución 256×224: mantiene ritmo de vídeo sin perder frames.
- \`IKSPC initialized=1\`: boot SGB firmware completado, backend N-SPC activo.
- \`SOUND received=318 sent=318 undelivered=0\`: comandos de efecto recibidos por la interfaz SPC; **no prueba que se escucharon**.
- \`SPC_frames=7140\`, \`FIFO=16384\` (capacidad): SPC tenía muestras acumuladas.
- \`SNES_PCM_mixed=0 silent=0\`, \`audio gen=3934720 audio write=0 audio drop=3934720\`: **ruta de mezcla no ejecutada** y audio físico ausente.
- Tres dispositivos ALSA dieron \`Device or resource busy\`; el host descartaba samples antes de entrar en el bucle de mezcla. \`recover=0\` no contradice esto porque nunca consiguió abrir un PCM.
- La ruta del archivo comprimido original no se registraba en el log principal, por lo que este registro solo valida el SGBPACK1 de respaldo, no la procedencia del archivo \`.7z\`.

### Corrección de software para #26 experimental

- Mover \`ik_f6_spc_mix_one\` del escritor ALSA al callback de entrada mGBA (ANTES de comprobar \`g_alsa_ready\`), por lo que las muestras SNES se consumen y se mezclarán tanto con dispositivo ocupado como con dispositivo disponible. La condición \`audio write=0\` sigue reflejando honestamente el resultado físico si ALSA está ocupado.
- Crear PCM SPC a 32768 Hz de entrada de mGBA, **no** a la frecuencia del hardware que puede ser 32040/32000/48000 (o quedar en valor por defecto si ALSA falló). La adaptación a la frecuencia ALSA sucede **después** de sumar GB+SPC, en un único resampler final.
- Contar \`SPC_nonzero\` para comprobar si la salida N-SPC contiene alguna muestra distinta de cero. Aunque esté activo el backend, los comandos \`SOUND\` no garantizan contenido audible.
- Probar apertura no exclusiva \`plug:dmix\` y \`dmix\` entre dispositivos y volver a intentar abrir ALSA solamente tres veces (GB frames 120,600,1800), sin matar servicios ni modificar Clover.
- Registrar \`IKF6 ARCHIVE source\` en el log nativo para identificar la ruta \`.sfc.7z\` original.

El **único** siguiente test de campo de esta iteración debe hacerse con el juego previamente ubicado en \`/var/lib/hakchi/games/.storage/CLV-U-TQUUY/NETTOU_KOF_96_prueba_SGBPACK_v1.sfc.7z\`. El usuario ejecuta el emulador y luego un \`tail -n 80\` de log; no debe investigar el audio del sistema ni repetir comandos de diagnóstico específicos.

## Prueba física Fase 6 #26 y corrección #33

Registro de #26 desde Hakchi/Clover (120.01 segundos):
- 7168 cuadros, **59.73 FPS**, capacidad **135.71 FPS**, `late frames=0`.
- ALSA correcto: `audio write=3,843,412`, `audio drop=0`, `ALSA recover=0`.
- SGB inicializado: `IKSPC initialized=1`, `SOUND received=187 sent=187`, `SPC_nonzero=1,583,624`, `SNES_PCM_mixed=3,887,791`.
- `silent=32,593`: underruns del FIFO SPC. Concuerda aproximadamente con el desacople del reloj por cuadro SNES 60.0988 Hz frente a mGBA ~59.7275 Hz. El usuario observó sonido de máquina de escribir/texto entrecortado; la correlación no demuestra la causa completa.

La compilación experimental **#33** (GitHub Actions run `41176717270` aprobado) incorpora:
- Un parche aislado `experimental/fase6/patch_f6_spc_cadence.py` que hace avanzar los ciclos SPC700 a `1024000 / fps_gameboy` por cuadro en lugar de `1024000 / 60.09881389744051`; preserva reloj real de SPC y tono.
- Exportación privada `ikcore_spc_set_frame_fps` y configuración a partir de `avinfo.timing.fps` del GB, sin modificar los ejecutables estables.
- `IKSPC boot_CPU_ms` para observar coste de inicio de firmware original (no aceleración de boot demostrada).

CI verificó ARMv7 hard float, ABI GLIBC <= 2.23, exportaciones SPC, extracción `.sfc.7z`, tar HMOD y SHA256. **Pendiente validación física** de mejora de la máquina de escribir y reducción de bajo flujo de PCM; no declarar audio fiel ni arranque acelerado todavía.
