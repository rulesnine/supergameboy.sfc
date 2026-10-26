# Ik Core híbrido — Fase 1: núcleo mGBA ejecutable y compilación NES Mini

**Resultado:** pruebas de compilación y ejecución automática **aprobadas**.  
**Compilación comprobada:** [GitHub Actions 40264893185](https://github.com/rulesnine/supergameboy.sfc/actions/runs/40264893185).  
**No es una HMOD instalable ni un emulador híbrido terminado.**  
**Base de Ik Core preservada:** #43, `cba03acbd04d41fcadcf9c8c7be87126c3b5ce7e`.

## Objetivo de la fase

Preparar el motor Game Boy eficiente de mGBA para ARMv7, abrir un punto de conexión para los comandos Super Game Boy y probar la entrega de fotogramas y audio GB con una ROM construida íntegramente para la prueba. Todo esto se hace fuera de la NES Mini, sin modificar la #43.

## Evidencia comprobada

| Prueba | Resultado |
| --- | --- |
| Núcleo mGBA vía libretro ejecutado en máquina x86 de CI | **PASÓ** |
| ROM propia de 32 KiB con metadatos GBX (sin logotipo protegido ni BIOS) | **PASÓ** |
| Fotogramas de la prueba x86 | 240 ejecutados y 240 entregados |
| Resolución del núcleo GB | 160×144 |
| Audio Game Boy generado en x86 | 526 336 muestras |
| Tiempo medio por fotograma en x86 sin limitador | 0.249 ms (ROM sintética, hardware de CI) |
| FIFO de paquetes SGB (SOUND=0x08, SOU_TRN=0x09, multipaquete, orden y overflow) | **PASÓ** |
| mGBA libretro compilado para NES Mini ARMv7 hard-float | **PASÓ** |
| Versión ABI de GLIBC del binario ARM (no mayor a 2.23) | **PASÓ** |
| Biblioteca ARMv7 estática exclusiva de Game Boy, sin GBA ni frontend libretro | **PASÓ** |
| HMOD con Game Boy mGBA + SPC700/DSP + BIOS SGB | **PENDIENTE; no implementado** |
| Rendimiento real en NES Mini con Belmont's Revenge | **NO MEDIDO** |

**Interpretación:** la cifra de velocidad x86 **no** demuestra que la NES Mini alcance 60 FPS. Tampoco demuestra fidelidad del audio SNES; el SPC700/DSP aún no recibe los comandos desde mGBA.

## Entregables internos de compilación

- `ikcore_mgba_gb_armhf_phase1.so`: módulo libretro ARMhf para pruebas de ABI; **incluye código GBA inactivo porque el frontend upstream lo requiere al compilar**. No debe convertirse en el núcleo final.
- `ikcore_mgba_gb_only_armhf_phase1.a`: biblioteca ARMhf estática, **solo núcleo Game Boy**, que se utilizará para integrar Ik Core sin llevar código GBA innecesario.
- `native_mgba/ikcore_sgb_packet_bus.c/.h`: FIFO ordenado de paquetes SGB. No reproduce sonidos por sí mismo; conserva los mensajes para un posterior adaptador.
- `tools/patch_mgba_sgb_bridge.py`: injerta una observación débil (`ikcore_sgb_packet_hook`) en el punto donde mGBA ya ensambló el comando. El motor mGBA conserva sus rutas de ejecución.
- `tests/ikcore_sgb_packet_bus_test.c` y `tests/mgba_libretro_smoke.c`: pruebas reproducibles.
- `tools/make_synthetic_gb_rom.py`: genera cartucho de prueba no comercial, NO se incluye el cartucho en los paquetes exportados.

El código de mGBA se toma de un commit fijado (`1509d86028c7df2d844b590723a80b2978f49e7c`) y se somete a su licencia MPL-2.0, con la licencia Snes9x del otro componente todavía por atender en su distribución conjunta.

## Interfaz que falta conectar en la fase 2

1. Construir el **adaptador de arranque** para que Ik Core invoque el nuevo motor GB desde el inicio. No arrancar dos CPUs Game Boy.
2. Enlazar los paquetes SGB a un único estado SGB, sin aplicar PAL/ATTR/CHR/PCT dos veces. Mantener marcos y máscaras.
3. Interceptar `SOU_TRN` después de que mGBA capture los 4096 bytes enviados por la pantalla LCD. Un paquete SOU_TRN por sí solo **no** contiene el audio SNES.
4. Enviar `SOUND` y los 4096 bytes SOU_TRN al hilo **SPC700/DSP ya funcional de Ik Core**, respetando su orden, cola y parámetros.
5. Mezclar PCM GB de mGBA + PCM SNES de Ik Core, manteniendo el reloj SGB1 y sincronización A/V.
6. Probar la entrada SGBPACK, sonidos originales, títulos, paletas, marcos, comandos, SRAM y salida Clover. Usar perfiles completos antes de solicitar una sola prueba final en NES Mini.

**No etiquetar una compilación híbrida como estable** hasta demostrar velocidad y fidelidad de audio en *Castlevania II: Belmont's Revenge*, *Castlevania Legends* y *KOF '96* en la consola real.

## Referencias

- [Fuente completa de esta rama](https://github.com/rulesnine/supergameboy.sfc/tree/integracion/mgba-gb-core-armv7-fase1)
- [Workflow reproducible](https://github.com/rulesnine/supergameboy.sfc/blob/integracion/mgba-gb-core-armv7-fase1/.github/workflows/ikcore-mgba-gb-armv7.yml)
- [Arquitectura de integración](https://github.com/rulesnine/supergameboy.sfc/blob/arquitectura/ikcore-mgba-spc-hibrido/docs/ARQUITECTURA_MGBA_GB_IKCORE_SGB_AUDIO.md)
