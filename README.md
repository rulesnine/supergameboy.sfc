# Ik Core — SGBPACK Runtime for Windows

**Ik Core** es un fork no oficial e independiente para Windows, derivado de **SuperSnes9x / Snes9x**, adaptado para cargar sesiones Super Game Boy empaquetadas en un único archivo **SGBPACK1**.

## Qué hace

```text
Programa Super Game Boy (.sfc)
+ ROM Game Boy (.gb/.gbc)
+ boot ROM SGB (256 bytes)
        ↓
Ik Core SGBPACK Builder
        ↓
archivo SGBPACK1
        ↓
Ik Core
```

Ik Core detecta la firma `SGBPACK1`, valida el contenedor, separa internamente sus componentes y monta la sesión Super Game Boy sin pedir al usuario que cargue cada archivo por separado.

## Plataforma oficial

- **Windows x64:** plataforma oficial y soportada.
- **NES Mini:** únicamente prueba de concepto histórica. Se consiguió arranque real en hardware, pero el rendimiento fue insuficiente para uso práctico; no forma parte de las builds oficiales ni de la distribución del proyecto.

## Base técnica

La compilación usa una base fija y reproducible:

```text
shanytc/snes9x
commit 183e03e5efed3b6d450385c98e2ccffb194153c3
```

Sobre esa base se aplica la integración SGBPACK y la identidad de Ik Core durante la compilación.

## Identidad

Nombre del producto: **Ik Core**  
Subtítulo: **SGBPACK Runtime for Windows**  
Formato: **SGBPACK1**

El ejecutable oficial se distribuye como `IkCore.exe`. El icono de Ik Core es propio del fork y no utiliza logotipos de Nintendo ni de los proyectos base.

## Aviso legal

Ik Core es un proyecto **no oficial, independiente y no afiliado, autorizado, patrocinado ni respaldado por Nintendo Co., Ltd.** Tampoco pretende atribuirse la autoría del código original de Snes9x o SuperSnes9x.

Este repositorio **no incluye ni descarga ROMs comerciales, BIOS de Nintendo ni boot ROMs protegidas**. El usuario debe aportar sus propios archivos obtenidos lícitamente.

La licencia y los avisos de copyright de Snes9x permanecen aplicables a las partes derivadas. Consulta `LICENSE` y `CREDITS.md`.

## Builds

GitHub Actions genera:

- `IkCore.exe` — aplicación Windows x64.
- `ikcore_sgbpack_libretro-x64.dll` — core libretro Windows x64 opcional.
- `IkCore.ico`
- README, créditos, licencia y hashes SHA-256.

El formato SGBPACK1 y el Builder no convierten una ROM Game Boy en una ROM SNES universal: los archivos SGBPACK1 requieren un cargador compatible como Ik Core.
