# Ik Core — Fase 5: verificación física en NES Mini

**Fecha del informe:** 2026-10-30
**Origen:** salida de consola aportada por quien realizó la prueba en su NES Mini.
**Alcance:** diagnóstico ARMv7 *freestanding*, **NO** emulador.

## Evidencia reportada

```text
# /bin/ikcore-fase5-probe
IK CORE FASE 5 ARMv7 SELFTEST (not an emulator)
armv7l
IKCORE_FASE5_ARM_SELFTEST_PASS
EXIT_CODE=0
```

La consola ejecutó el lanzador y el programa ARMv7. La autoprueba devuelve un resultado de aprobación; el mensaje `EXIT_CODE=0` procede del lanzador. No se adjunta un registro de `echo $?` independiente y no se deducen mediciones de velocidad.

## Qué queda comprobado

- El paquete de diagnóstico se instaló lo suficiente para exponer y ejecutar `/bin/ikcore-fase5-probe`.
- El entorno reporta arquitectura `armv7l`.
- El ejecutable de autoprueba termina con su marcador de aprobación.
- Las pruebas sintéticas de cola/JOYP/tap son compatibles con la ejecución en esa consola.

## Qué NO queda comprobado

- No hay ejecución de mGBA, cartucho ni boot ROM en este binario.
- No hay prueba de transporte real de paquetes SGB desde mGBA a ICD2.
- No se han probado voces SPC700/DSP, transiciones SGB, SRAM ni estados de suspensión.
- No existen mediciones de FPS ni HMOD híbrido jugable.
- La versión #43 no se modifica y debe mantenerse como referencia.

## Auditoría de compilación

El flujo actual `.github/workflows/build-nesmini-native.yml` compila el núcleo SuperSnes9x con modificaciones de `tools/apply_sgbpack.py`, no incluye mGBA en el enlace final. El flujo `verify-ikcore-fase5-bridge.yml` ejercita solamente pruebas de anfitrión y un parche de observación pasiva en mGBA. Ninguno produce el binario híbrido solicitado.

## Próximo hito necesario

1. Integrar mGBA como único motor GB de ejecución en la ruta ARMv7: evitar doble CPU/PPU y doble temporizador GB.
2. Adaptar la entrega de paquetes SGB al receptor concreto de ICD2 y sus convenciones de temporización, además de las transferencias LCD de 4 KiB.
3. Mantener SPC700/DSP y la mezcla GB APU ↔ SNES con tiempos reproducibles.
4. Configurar un nuevo workflow para construir un HMOD **experimental independiente**; no sustituir `/bin/sgbpack-native` ni bibliotecas existentes.
5. Pasar pruebas ROM reales y registrar arranque, integridad gráfica, audio y `FPS` antes de declarar la versión jugable.

## Riesgo bloqueante

La infraestructura de pruebas de Fase 5 está verificada por separado, pero la integración real del runtime sigue ausente. No usar el marcador PASS como evidencia de que la Fase 5 está terminada.
