# Ik Core Native — NES Mini

Rama experimental para ejecutar **SGBPACK directamente sobre Linux ARMv7 de NES Mini**, sin RetroArch ni libretro.

## Estado

- **N0:** validacion directa del contenedor SGBPACK1 — compilada correctamente.
- **N1 (actual):** frontend Linux directo de diagnostico.
  - abre `/dev/fb0`
  - detecta formato/resolucion/stride
  - guarda la imagen actual del framebuffer
  - presenta una superficie SGB 256x224 durante 10 segundos
  - intenta mantener 60 presentaciones/s
  - mide FPS reales del camino nativo
  - abre `/dev/input/event*` y registra codigos de botones
  - restaura el framebuffer al terminar
- **N2:** integrar el motor SGB completo de SuperSnes9x/SGBPACK en este frontend.
- **N3:** perfilado/optimizacion Cortex-A7 conservando las funciones SGB completas.

## Seguridad

N1 no flashea ni reemplaza kernel, Clover, Kachikachi, bootloader o particiones. Abre framebuffer/input como dispositivos Linux y restaura el contenido visible al salir.

## Uso N1

Desde una shell de la NES Mini:

```sh
chmod +x sgbpack-native
./sgbpack-native KOF96_SGBPACK_v1_REUPLOAD.sfc
```

La pantalla mostrara un patron de diagnostico durante unos 10 segundos. Al finalizar, la terminal imprimira el promedio `RESULT : xx.xx FPS`.

Ese valor mide **solo video/input nativo**, todavía no la emulacion SGB. Si N1 sostiene ~60 FPS, el framebuffer no es el cuello de botella y N2 podra medir el costo real del motor SGB sin RetroArch.
