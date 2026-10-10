# Ik Core Native N2 — NES Mini

## Objetivo

N2 integra por primera vez el motor SGB completo con el frontend nativo validado en N1.7.

La arquitectura es:

Clover -> /bin/sgbpack-native -> frontend EGL nativo -> Ik Core SGBPACK libretro -> SGBPACK1

RetroArch no participa en esta ruta.

## Qué conserva de N1.7

N1.7 quedó validada en hardware real:

- EGL inicializa correctamente.
- GPU ARM Mali-400 MP.
- 1280x720.
- Nintendo Clovercon adquirido con EVIOCGRAB.
- ~60 FPS sostenidos en el frontend.
- retorno limpio a Clover.
- sin C7.
- audio del menú restaurado correctamente.

## Qué añade N2

- carga directa del core Ik Core / SuperSnes9x mediante dlopen
- carga del contenedor SGBPACK1 real
- ejecución del motor Super Game Boy completo
- video real del core enviado a una textura GLES2
- escalado con relación de aspecto preservada
- entrada del control NES Mini enviada al core
- benchmark del motor durante 10 segundos sin limitador artificial
- log persistente para diagnóstico

N2 todavía NO abre ALSA. El core recibe video habilitado y audio deshabilitado. Esto permite medir primero el costo real de CPU del motor SGB sin volver a poner en riesgo el audio de Clover.

## Archivos instalados por el HMOD

```text
/bin/sgbpack-native
/usr/lib/ikcore/sgbpack-native-n2
/usr/lib/ikcore/ikcore_sgbpack_libretro.so
```

El acceso de Hakchi existente puede seguir ejecutando:

```sh
/bin/sgbpack-native
```

No es necesario crear otro acceso.

## SGBPACK de prueba

Si no se pasa argumento, N2 usa:

```text
/var/lib/hakchi/sgb-native-test/KOF96_SGBPACK_v1_REUPLOAD.sfc
```

También acepta una ruta explícita:

```sh
/bin/sgbpack-native /ruta/al/juego.sfc
```

## Log

N2 escribe además:

```text
/var/lib/hakchi/sgb-native-test/ikcore-n2.log
```

## Resultado esperado

Durante 10 segundos debe verse el video real del SGBPACK. En consola se informa el rendimiento del motor:

```text
engine FPS  : ...
```

y al final:

```text
FINAL N2
runs        : ...
video frames: ...
engine avg  : ... FPS
last frame  : ...
input events: ...
audio frames: ... descartados / ALSA nunca abierto
EGL         : liberado correctamente
resultado   : VIDEO SGB OK
```

Esta prueba mide el motor SGB completo sin el overhead del frontend de RetroArch. Que N1.7 sostenga ~60 FPS no implica que el motor completo alcance 60 FPS; N2 es la medición decisiva.
