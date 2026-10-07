# Ik Core Native — NES Mini

Rama experimental para ejecutar SGBPACK directamente sobre Linux ARMv7 de NES Mini, sin RetroArch ni libretro.

## Estado

- N0: valida SGBPACK1.
- N1: primer framebuffer directo.
- N1.1: blitter optimizado; hardware real midio ~60 FPS.
- N1.2 (actual): prueba de pantalla exclusiva sin detener Clover.
  - usa la segunda pagina del framebuffer 1280x720 cuando existe
  - hace `FBIOPAN_DISPLAY` hacia esa pagina
  - limpia esa pagina a negro antes de mostrarla
  - dibuja SGB 256x224 a 3x (768x672)
  - restaura el yoffset original al terminar
  - identifica `Nintendo Clovercon - controller1`
  - intenta `EVIOCGRAB` para leer el mando en exclusiva
  - muestra codigos reales del control
- N2: integrar el motor SGB completo en este frontend nativo.
- N3: perfilado/optimizacion Cortex-A7 conservando las funciones SGB.

## Uso N1.2

```sh
chmod +x sgbpack-native
./sgbpack-native KOF96_SGBPACK_v1_REUPLOAD.sfc
```

Durante los 10 segundos pulsa D-pad, A, B, Start y Select.

Copiar al final:

```text
pan display : ...
NATIVE FPS  : xx.xx
input events: n
```

y todas las lineas `pad event`.

Si la pantalla sigue mezclandose con Clover aun usando la segunda pagina, el siguiente paso sera suspender temporalmente el proceso de Clover durante la ejecucion y reanudarlo al salir.
