# Ik Core Native — NES Mini

## Estado

- N0: SGBPACK1 validado.
- N1/N1.1: framebuffer nativo y blitter ~60 FPS.
- N1.2: segunda pagina + Clovercon exclusivo ~60 FPS.
- N1.3/N1.4: se descubrio que `clover-mcp` controla `/dev/disp`.
- Pausar `clover-mcp` congela la consola: **esa ruta queda descartada**.
- **N1.5 SAFE (actual):** no suspende procesos. Obtiene el layer handle de `/dev/fb0` y usa el display engine sunxi para mover ese layer al frente con `DISP_CMD_LAYER_TOP`.

## Uso

```sh
chmod +x sgbpack-native
./sgbpack-native KOF96_SGBPACK_v1_REUPLOAD.sfc
```

Pasa estas lineas:

```text
fb layer    : ...
layer prio  : before=...
layer TOP   : ...
pan display : ...
NATIVE FPS  : ...
input events: ...
```

Y confirma visualmente si el menu de Clover deja de verse durante los 10 segundos.

Esta prueba no envia SIGSTOP ni SIGKILL a Clover, clover-mcp o kachikachi.
