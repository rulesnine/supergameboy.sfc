# Ik Core Native — NES Mini

## Estado confirmado en hardware
- framebuffer directo: 1280x720, doble pagina 1280x1440
- blitter 256x224 -> 768x672: ~60 FPS
- Clovercon directo: /dev/input/event24 + EVIOCGRAB
- clover-mcp NO debe suspenderse
- desde shell, Clover sigue componiendo su menu por encima
- forzar DISP_CMD_LAYER_TOP desde shell devuelve EPERM

## N1.6 — prueba HMOD / ciclo normal de Clover

Esta prueba ya no intenta ganar la pantalla desde una sesion shell. El objetivo es lanzar Ik Core Native como una aplicacion/juego real desde Clover, igual que un emulador normal, para que el propio ciclo de Clover ceda la pantalla.

El HMOD instala:

`/bin/sgbpack-native`

Comando de lanzamiento para el acceso de prueba:

```sh
/bin/sgbpack-native /var/lib/hakchi/sgb-native-test/KOF96_SGBPACK_v1_REUPLOAD.sfc
```

No usa SIGSTOP ni SIGKILL y no modifica kernel, firmware ni particiones.

Si al lanzarlo desde Clover desaparece el menu y queda solo el patron, el frontend nativo queda validado y se pasa a N2: integrar el motor SGB completo.
