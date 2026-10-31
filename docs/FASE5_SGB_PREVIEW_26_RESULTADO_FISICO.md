# Ik Core Fase 5 — resultado físico SGB Preview #26

**Fuente:** salida de terminal aportada por el usuario (30-10-2026, zona horaria Ciudad de México). Estas métricas son de un único juego y no representan todos los títulos.

| Métrica | Observación |
|---|---|
| Frame pacing | 59.73 FPS constantes |
| Capacidad calculada | 241.53 → 240.64 FPS de trabajo, no de presentación |
| SGB packets | 119 |
| SOUND | 79 |
| TRN | 5 |
| gb_cycles | 321015498 (valor no nulo) |
| GB audio gen | aprox. 31894–32394 muestras/s |
| ALSA written | aprox. 31485–32629 muestras/s |
| ALSA recover | 0 |
| Ring final | aprox. 3202–3613 muestras |

## Significado exacto de contadores

El código del HMOD #26 cuenta `SOUND` cuando `cmd==0x08` **o** `cmd==0x09`. Son, respectivamente, comandos de disparo `SOUND` y `SOU_TRN`. Los 79 eventos **no equivalen a 79 efectos SNES reproducidos**; el firmware SPC700/DSP aún no se conecta en esta rama.

El contador `TRN` agrupa comandos `0x09,0x0B,0x13,0x14,0x15,0x18`: también cuenta `SOU_TRN`. No prueba la transferencia de todos los 4KiB gráficos ni confirma visualmente un marco correcto.

La medición `59.73` es la tasa de frames ejecutados/presentados con el limitador activo. La `capacidad trabajo` es una estimación de la velocidad del trabajo medido en el loop (no la velocidad del emulador híbrido una vez añadido el DSP SNES).

La salida ALSA es activa y continua; `written` != 0, confirmando el transporte de audio Game Boy. Esto no mide ni garantiza ausencia de latencia ni fidelidad del sonido SNES.

## Próximo puente de ingeniería

- La cola ya desarrollada en `experimental/fase5/ik_sgb_bridge.c` ahora se enlaza a `ik_sgb_mgba_telemetry.c`. El callback de mGBA copia cada paquete y expone `ikcore_fase5_sgb_pop_packet` (C ABI, hilo de emulación).
- El frontend/ICD2 deberá drenar la cola **cada frame**; si se llena a 64, no se inventarán paquetes ni se reproducirán efectos falsos. En esta etapa el reproductor SNES **no** está conectado.
- El observador distingue `SOUND` (0x08) de `SOU_TRN` (0x09) mediante contadores adicionales.
- Conservar la vía del motor GB mGBA y ALSA, y la versión estable #43. La ruta SGBPACK1 y sonido SNES original son próximos objetivos, no hechos cumplidos.

## Validación visual necesaria

El registro suministrado no contiene la línea inicial `IKSGB model=... border=... geometry=...`, ni captura de la imagen mostrada. Se desconoce si el marco y las paletas se representan correctamente en la pantalla física. Esa comprobación es independiente de los contadores SGB.

## Confirmación visual posterior del usuario (KOF '96)

El usuario confirmó explícitamente que en KOF '96 **el juego, las paletas SGB y el marco cargan correctamente**, que **el audio normal de Game Boy sí se escucha** y que **no se oyen los efectos ni el audio mejorado del SNES**. Esto cierra la revisión visual de KOF '96 para el HMOD #26, **no** constituye una validación de compatibilidad universal para otros juegos.

Por tanto no se necesitan más cambios de paleta/marco para este juego en la rama experimental; la prioridad es conectar el audio SPC700/DSP a partir del camino N-SPC que ya existía en la implementación #117. El contador `SOUND=79` agrupaba `SOUND` (0x08) y `SOU_TRN` (0x09) y no prueba que se hayan reproducido sonidos SNES.

Se añadieron `experimental/fase5/ik_sgb_spc_route.{h,c}` y sus pruebas unitarias: adaptan los paquetes `SOUND` exactos y solicitudes `SOU_TRN` a callbacks para un futuro motor SPC inicializado, pero **sin un backend conectado no generan audio SNES ni son un HMOD híbrido**. Para `SOU_TRN` hace falta captura íntegra del transfer LCD de 4096 bytes y no basta el paquete de 16 bytes.

