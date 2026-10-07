# Ik Core Native — NES Mini

## N1.7 — Clover EGL lifecycle

La N1.6 se descarta: entraba en negro, terminaba con C8 y dejaba el audio del sistema sin restaurar correctamente.

N1.7 cambia el frontend:

- no escribe video directamente en /dev/fb0
- no usa /dev/disp
- no envia SIGSTOP/SIGKILL
- no abre ALSA
- crea una superficie EGL/OpenGL ES 2 como una aplicacion nativa de Clover
- toma Clovercon con EVIOCGRAB
- renderiza un patron fullscreen 10 segundos
- libera input, contexto, superficie y display EGL de forma ordenada

El objetivo de esta version NO es emular SGB todavia. Solo valida el ciclo:

Clover -> Ik Core -> Clover

sin C8 y sin romper audio.

## Prueba

Instala el HMOD y usa el mismo acceso que ya llama:

```sh
/bin/sgbpack-native /var/lib/hakchi/sgb-native-test/KOF96_SGBPACK_v1_REUPLOAD.sfc
```

El argumento SGBPACK se conserva por compatibilidad con el acceso actual, aunque N1.7 aun no carga el motor SGB.

Esperado:
1. desaparece Clover
2. aparece patron fullscreen
3. dura 10 segundos
4. vuelve a Clover
5. audio del menu sigue funcionando
6. sin error C8
