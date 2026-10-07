# Ik Core Native — NES Mini

Rama de trabajo para ejecutar SGBPACK directamente sobre el Linux ARMv7 de la NES Mini, sin RetroArch ni libretro.

## Fases

- **N0 (actual):** ejecutable ARMv7 independiente que valida SGBPACK1 directamente desde Linux.
- **N1:** frontend nativo (video/input/audio) y medicion de FPS.
- **N2:** integrar la ruta SGB completa de SuperSnes9x/SGBPACK.
- **N3:** perfilado y optimizacion Cortex-A7 sin recortar funciones SGB.

N0 no modifica kernel, Clover, Kachikachi, bootloader ni particiones. Solo lee el archivo SGBPACK y escribe diagnostico por stdout.

Uso previsto:

```sh
chmod +x sgbpack-native
./sgbpack-native KOF96_SGBPACK_v1_REUPLOAD.sfc
```

Cuando N2 este integrado, el mismo nombre de ejecutable se mantendra para lanzar el emulador completo.
