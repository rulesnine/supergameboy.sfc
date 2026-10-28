# Ik Core híbrido — Fase 6: vinculación de paquetes mGBA con ICD2 original

**Estado:** trabajo de integración experimental. La base estable #43 no ha cambiado. **No es HMOD**, ni demuestra ejecución híbrida completa en la NES Mini.

## Investigación y decisión de arquitectura

La Fase 5 consiguió ejecutar el boot Game Boy libre del SGB en mGBA desde `PC=0000`, pero eso no garantiza que el BIOS SNES reciba sus comandos.

En el árbol original de SuperSnes9x existe una implementación ICD2 probada que controla los registros del cartucho SGB en la CPU 65816. Por ello, no se implementa un segundo ICD2. La ruta nueva introduce paquetes mGBA en el **mismo FIFO de hasta 64 paquetes de 16 bytes** que el firmware SNES lee por:

- `$6002`: consulta/consume *un* paquete de la cola hacia el latch.
- `$7000–$700F`: lee los 16 bytes del paquete latcheado.
- `$6003`: escritura de reset/liberación de la CPU Game Boy (bit 7).
- `$7800–$780F`: ventana de captura LCD/transferencias gráficas. **Todavía pendiente de alimentar con los píxeles generados por mGBA**.

El motor GB original de Snes9x conserva internamente otros mecanismos que, en una futura integración, habrá que deshabilitar como productores cuando mGBA sea la única CPU GB, sin interrumpir las lecturas del BIOS.

## Implementaciones de la fase

1. `tools/patch_ikcore_mgba_icd2_phase6.py`: inserta `SGB::Emulator::ReceiveMGBAPackets` tras el productor existente `IcdPushQueue` y expone la función Snes9x `S9xSGBReceiveMGBAPackets`. Esta función es optativa y solo opera en modo BIOS auténtico, con CPU GB liberada.
2. Los paquetes multiparte se aceptan **de forma atómica**. Si la longitud es inválida, la cabecera contradice el número de bloques o faltan slots, no se modifica la cola. Cuando son válidos se preservan los 16 bytes exactos por bloque en el orden en que llegaron.
3. Se reutiliza la caché de hasta seis paquetes de handshake para las comprobaciones del firmware SGB, sin sintetizar mensajes arbitrarios. No sustituye la necesidad de sincronización.
4. `native_mgba/ikcore_sgb_packet_bus.c`: primero intenta depositar cada mensaje completo de mGBA en ICD2. Respuesta `0` = sesión BIOS no activada (comportamiento anterior); `1` = aceptado en ICD2; `-1` = rechazado, sin envío duplicado al audio directo.
5. `native_mgba/ikcore_sgb_audio_fifo.c`: cuando el BIOS SNES es dueño del tráfico, el comando `SOU_TRN` deja de producir una segunda transferencia directa a SPC700/DSP. El firmware debe ser la fuente de verdad de sonido.
6. `native_mgba/ikcore_mgba_combined_phase4.cpp`: incorpora un interruptor **explícito** `ikcore_mgba_phase6_enable_icd2()` que solo funciona después de crear mGBA y cargar el BIOS SNES. `ikcore_mgba_phase6_disable_icd2()` lo apaga. Se mantiene **inactivo en el arranque normal de Hakchi**, para no alterar #43.

## Pruebas y límites

`tests/ikcore_phase6_icd2_route_test.c` inyecta comandos sintéticos en el productor C, con una implementación simulada del receptor, y comprueba:
- Con ICD2 inactivo, el sonido SOUND sigue su cola histórica.
- Con ICD2 activo, un SOUND se entrega **una vez** al receptor ICD2, sin otro SOUND directo al SPC.
- Un comando multipaquete de 32 bytes mantiene orden y longitud.
- Si el receptor ICD2 rechaza el mensaje, la cola de sonido no reproduce un sonido fuera de orden y se contabiliza el rechazo.
- SOU_TRN de 4096 bytes no se duplica cuando el BIOS está activo; sin él, se conserva la ruta anterior.

El enlazador ARM se encarga de comprobar que `S9xSGBReceiveMGBAPackets`, el módulo mGBA y los símbolos del audio SNES realmente están en **el mismo ejecutable ARMhf/GLIBC 2.23**. Esto es una verificación de enlace, **no una prueba funcional de lecturas reales del BIOS SNES**.

## Pendientes imprescindibles antes de una HMOD

1. Activar mGBA desde el comienzo de una sesión SGB, pero **sin ejecutar la CPU Game Boy heredada**. El SNES 65816 debe seguir atendiendo el firmware y el ICD2.
2. Conectar el reset de `$6003` al reset y arranque GB de mGBA; verificar que el handshake de seis paquetes y su repetición coincidan temporalmente con el BIOS real.
3. Sincronizar la línea HBlank/VBlank, el contador de filas/bancos `$6000` y la ventana LCD `$7800` con el PPU de mGBA. No puede alimentarse el firmware con los píxeles/timing del motor GB que se pretende retirar.
4. Mantener un único dueño de las paletas/marco SGB y de la presentación, respetando CHR/PCT/ATTR/PAL/MASK_EN.
5. Completar la mezcla PCM GB+SPC700/DSP y verificar que el firmware produce las mismas voces, efectos, música y fades que la #43.
6. Ejecutar primero pruebas automáticas de *un BIOS SGB completo* sin ROM comercial incluida; después solo una HMOD experimental separada para medir Belmont's Revenge, Castlevania Legends y KOF '96.

El objetivo sigue siendo alcanzar ~59.7 FPS de la máquina Game Boy con sonido SNES SGB fiel. **Ninguna compilación x86 o prueba de enlace ARM permite garantizar hoy ese rendimiento.**

## Referencias

- [Rama Fase 6](https://github.com/rulesnine/supergameboy.sfc/tree/integracion/mgba-icd2-fase6)
- [Compilación CI Fase 6](https://github.com/rulesnine/supergameboy.sfc/actions/workflows/ikcore-mgba-icd2-phase6.yml)
- [Documentación Fase 5](https://github.com/rulesnine/supergameboy.sfc/blob/integracion/mgba-arranque-sgb-fase5/docs/FASE5_MGBA_ARRANQUE_SGB.md)
