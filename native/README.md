# Ik Core Native — NES Mini

Rama experimental para ejecutar **SGBPACK directamente sobre Linux ARMv7 de NES Mini**, sin RetroArch ni libretro.

## Estado

- **N0:** validacion directa de SGBPACK1 — completada.
- **N1:** primer acceso directo a framebuffer/input — completada; detecto 1280x720/32 bpp en hardware real, pero el escalador de diagnostico era demasiado costoso.
- **N1.1 (actual):** benchmark de video corregido.
  - limpia toda la pantalla a negro
  - usa escala entera 3x: 256x224 -> 768x672
  - centra la imagen
  - elimina divisiones por pixel
  - convierte color una sola vez por pixel fuente
  - replica lineas con memcpy
  - mide por separado RAW framebuffer y blitter SGB
  - enumera nombres de dispositivos evdev y registra EV_KEY/EV_ABS
  - restaura el framebuffer al terminar
- **N2:** integrar el motor SGB completo de SuperSnes9x/SGBPACK sobre el frontend nativo validado.
- **N3:** perfilado y optimizacion Cortex-A7 conservando funciones SGB completas.

## Uso N1.1

```sh
chmod +x sgbpack-native
./sgbpack-native KOF96_SGBPACK_v1_REUPLOAD.sfc
```

La prueba dura aproximadamente 10 segundos. Durante ese tiempo pulsa varios botones del control.

Al terminar, copiar estas lineas:

```text
RAW FPS     : xx.xx
SGB BLIT FPS: xx.xx
input events: n
```

Si `SGB BLIT FPS` queda cerca de 60, el camino de video nativo ya no sera el cuello de botella y se puede pasar a N2.
