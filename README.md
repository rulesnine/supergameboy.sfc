# SGBPACK / SuperSnes9x

Proyecto experimental para cargar un juego de Game Boy dentro de un único archivo **SGBPACK1** usando el fork SuperSnes9x.

## Objetivo

```
KOF96_SGBPACK_v1.sfc
        ↓
SuperSnes9x modificado
        ↓
SGB BIOS + GB ROM + SGB boot ROM
        ↓
Super Game Boy
```

Este repositorio **no incluye ROMs comerciales ni BIOS de Nintendo**.

La compilación usa como base fija:

```
shanytc/snes9x
commit 183e03e5efed3b6d450385c98e2ccffb194153c3
```

GitHub Actions compila:

- Windows x64 standalone: `super-snes9x-x64.exe`
- Windows x64 libretro: `supersnes9x_libretro-x64.dll`

El archivo SGBPACK se mantiene fuera del repositorio y se carga localmente en el ejecutable resultante.
