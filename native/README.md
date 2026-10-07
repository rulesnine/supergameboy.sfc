# Ik Core Native — NES Mini

## Estado

- N0: valida SGBPACK1.
- N1: framebuffer directo.
- N1.1: blitter optimizado; ~60 FPS confirmado.
- N1.2: segunda pagina + Clovercon exclusivo; ~60 FPS confirmado.
- N1.3: intento de pausar Clover por nombre; no encontro el proceso real.
- **N1.4 (actual): diagnostico del propietario de pantalla**
  - escanea `/proc/*/fd`
  - lista procesos con `/dev/fb0` o `/dev/disp` abiertos
  - imprime PID, comm y cmdline
  - no suspende ningun proceso todavia
  - mantiene la prueba de video a 60 Hz y Clovercon exclusivo

## Uso

```sh
chmod +x sgbpack-native
./sgbpack-native KOF96_SGBPACK_v1_REUPLOAD.sfc
```

Copia especialmente todas las lineas:

```text
display proc: pid=... comm=[...] cmd=[...]
display proc count: ...
```

Con esos nombres/PIDs se prepara N1.5 para pausar solo el renderer correcto, sin tocar procesos críticos.
