# Ik Core PERF2 — auditoría de audio (candidato, NO probado en NES Mini)

## Estado y límites

**PERF1 continúa siendo la referencia de rendimiento:** 59.99 FPS, 14.582 ms por cuadro, 68.58 FPS de capacidad. No se ha modificado ni sustituido el HMOD validado.

La prueba física PERF2 ya consumió la quinta comprobación acordada: 36.75 FPS promedio, 26.644 ms/cuadro, 238 recuperaciones ALSA. El BIOS completo funcionó alrededor de 20–22 FPS durante más de 1,200 cuadros emulados, y el cambio a SGB directo sólo mejoró el ritmo a alrededor de 41–47 FPS.

## Cambios en esta rama

1. Se recompila el PERF2 híbrido con `IKCORE_SGB_LAZY_APU`, la optimización usada por PERF1. El APU GB conserva el avance de ciclos acumulado, descargado antes de registros audibles y al concluir cada cuadro. **Esto requiere comparar fidelidad de audio**, no equivale a emulación dot-exact de cada escritura.
2. El resampler SPC700 deja de usar el controlador PI amplio después del cambio a modo directo. Ese controlador podía ajustar la velocidad de producción hasta ±50 %, con efectos de tono; el modo híbrido adopta el ratio nominal fijo.
3. Se mide el coste real del SPC700/DSP aislado cada 300 cuadros: promedio y máximo, cuántos SOUND/SOU_TRN llegaron y cuántas muestras SPC están listas. No se infiere velocidad real de la compilación.
4. Se conserva la presentación atómica del marco introducida en PERF2; el fade experimental permanece apagado.

## Riesgos pendientes

* La entrada a modo directo sigue dependiendo de terminar la secuencia de arranque BIOS/SGB. No se debe declarar corregida la carga de arranque.
* La ruta de puertos SOUND/SOU_TRN del PERF2 previo necesita una prueba de equivalencia con la ROM de BIOS y el N-SPC. El formato de los comandos GB **no prueba por sí solo** cómo los consume el programa SNES. No se incluye una solución afirmada para esta incertidumbre.
* El audio degradado no se considera resuelto sin escuchar y comparar una reproducción verificable; cero muestras descartadas en el contador no equivale a sonido sin fallos.
* No se dispone en CI del SGBPACK real del usuario; GitHub Actions valida compilación, arquitectura/ABI y estas invariantes, no fidelidad sonora ni FPS físicos.

## Aceptación futura (sin solicitarla ahora)

Sólo aprobar para NES Mini después de un banco de pruebas automatizado con datos legítimos del propio proyecto que demuestre: ejecución del BIOS completada, mezcla GB + SPC correcta, sin saltos de tono ni underflows, marco íntegro tras transferencias y presupuesto menor de ~16.64 ms/cuadro.

**No instalar esta rama como sustitución de PERF1 hasta superar esas comprobaciones.**
