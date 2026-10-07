# Ik Core Native — NES Mini

## Estado

- N0: valida SGBPACK1.
- N1: framebuffer directo.
- N1.1: blitter optimizado; ~60 FPS confirmados en hardware real.
- N1.2: segunda pagina del framebuffer + Clovercon exclusivo; ~60 FPS confirmados, pero Clover siguio repintando.
- **N1.3 (actual): fullscreen exclusivo**
  - detecta solo el renderizador de interfaz Clover (ReedPlayer-Clover-nes / clover-ui-nes)
  - lo pausa con SIGSTOP durante la prueba
  - usa la segunda pagina del framebuffer
  - toma Clovercon con EVIOCGRAB
  - al terminar restaura y envia SIGCONT a Clover
  - Ctrl+C/SIGTERM salen por ruta de limpieza normal

No mata Clover, no modifica firmware y no toca kernel/bootloader/particiones.

## Uso

```sh
chmod +x sgbpack-native
./sgbpack-native KOF96_SGBPACK_v1_REUPLOAD.sfc
```

Durante 10 segundos pulsa botones.

Pasa estas lineas:

```text
Clover STOP : ...
Clover UI   : procesos suspendidos=...
pan display : ...
NATIVE FPS  : ...
input events: ...
Clover CONT : ...
```

Lo importante: confirmar si ahora desaparece completamente el menu mientras corre.
