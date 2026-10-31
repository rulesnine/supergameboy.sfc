# Ik Core SGB — Producción RC1, NES Mini ARMv7

**Objetivo**: ejecutar cartuchos clásicos de Game Boy compatibles con SGB con su color y marco; mantener el marco SGB predeterminado cuando el juego no incluya su propio marco. Distribución separada del emulador experimental Fase 6 #40.

## Arquitectura retenida

- **Base congelada:** commit `6afcfcba59f3f72471a3a8ce8aac932044fc5ecc` (Fase 6 #40; funcionamiento a 59.73 FPS y sonido SNES SPC700 validado físicamente con KOF '96).
- mGBA 0.10.5 — CPU, PPU, APU y parser de SGB; Snes9x #117 aislado para los efectos SPC700/DSP.
- Se mantienen los 3 mecanismos presentes en #40: forzar SGB solamente para ROMs compatibles DMG; dibujar el marco genérico incluido en mGBA al reset; respetar los paquetes PALxx/ATTR/CHR_TRN/PCT_TRN enviados por la ROM sin recolor ni reemplazo.
- **Paletas predeterminadas de Super Game Boy:** opción nativa de mGBA 0.10.5 `mgba_gb_colors_preset=2`, exclusivamente presets SGB conocidos por título, no de GBC; si un cartucho envía sus propias instrucciones PAL, estas conservan la prioridad. Sin preset del título, permanece la paleta base.
- **Sin alteración del renderizador:** RGB565 hardware, `GL_NEAREST` para evitar interpolación y paletas originales de SGB de 15 bits provenientes del cartucho.
- Instrumentación de producción pasiva: `IKSGB VISUAL` identifica paquetes de paleta y confirma si llegó `PCT_TRN`; el SGB sigue aplicando los paquetes originales de mGBA sin filtrarlos.
- Si la ROM no envía PCT_TRN, el marco genérico de mGBA permanece. Una ROM que solo envía PALETAS, sin marco, mantiene ese marco genérico y aplica los colores de la ROM.
- Los cartuchos exclusivos de Game Boy Color **no son compatibles con la consola Super Game Boy original** y este perfil no debe anunciar equivalencia SGB para ellos. Compatibilidad completa juego por juego requiere validación física y no se garantiza universalmente.

## Instalación y línea de comando

Paquete independiente: `IkCore-SGB-Production-RC1-N.hmod`.

Hakchi CE, para juegos GB comprimidos por Hakchi:

```sh
/bin/ikcore-sgb-prod-7z "/var/lib/hakchi/games/.storage/CLV-.../MiJuego.gb.7z"
```

ROM sin comprimir:

```sh
/bin/ikcore-sgb-prod "/ruta/MiJuego.gb"
```

Una sola ROM SGBPACK1 `.sfc.7z`:

```sh
/bin/ikcore-sgb-prod-7z "/var/lib/hakchi/games/.storage/CLV-.../MiJuego.sfc.7z"
```

- Otros formatos: `.gb`, `.gbc` compatibles DMG, `.dmg`, `.gb.7z`, `.gbc.7z`, `.sfc`, `.sfc.7z`.
- Para audio SNES SGB con una ROM GB autónoma, se requiere un SGBPACK1 proporcionado por el usuario. Por compatibilidad con la instalación física actual, el valor por defecto permanece en `/var/lib/hakchi/sgb-native-test/KOF96_SGBPACK_v1_REUPLOAD.sfc`, o se puede pasar como segundo argumento a la ruta sin compresión.
- No se incluyen imágenes de BIOS, firmware o juegos comerciales.
- El HMOD no instala filtros de Clover, controladores HDMI ni ajustes globales de audio. Se recomienda un arranque normal tras instalar módulos en Hakchi CE.

## Verificación

```sh
f=$(ls -t /var/lib/hakchi/sgb-native-test/ikcore-sgb-prod-*.log | head -n 1)
grep -E 'IKSGB VISUAL|IKSGB MAILBOX|play FPS|audio drop' "$f" | tail -n 25
```

Casos obligatorios en NES Mini para liberar final:

1. **Game Boy normal**: dibuja marco SGB genérico y conserva sus cuatro tonos base; `PCT_TRN=0`, `border=SGB_DEFAULT`.
2. **Game Boy SGB con paleta propia**: muestra colores de la ROM y mantiene el marco genérico si no hay transferencia de arte; `SGB_pal>0` con `PCT_TRN=0`.
3. **SGB con marco propio**: `PCT_TRN>0` y `border=ROM_CUSTOM`; inspect visualmente diseño, color y marcos tras transiciones.
4. **KOF '96**: sound mailbox sin fallas, `audio drop=0`, velocidad cercana a 59.73 FPS en NES Mini, sin regresión de la máquina de escribir.

La instrumentación de comandos de borde NO prueba por sí sola fidelidad pixel por pixel ni cobertura de toda la biblioteca. De no haber pruebas físicas multisistema, etiquetar esta build RC1 y no versión final certificada.

## Producción RC2 — tres correcciones solicitadas

- **Eliminado cierre de test a los 120 segundos:** el bucle principal de producción ya no contiene condición de salida por tiempo. Solo salidas solicitadas (SELECT+START), de Clover/retro core o error grave de EGL.
- **Marco BIOS original para juegos GB sin PCT_TRN:** en el arranque del firmware SGB1 que el usuario proporcionó, Snes9x captura la imagen SNES 256×224 antes de que el cartucho SGBPACK1 transfiera su propio PCT_TRN; convierte a RGB565 si el backend entrega RGB555. El front-end muestra únicamente sus márgenes SGB (x=0–47, 208–255, y=0–39,184–223); el área de juego 160×144 y los colores enviados por la ROM siguen inalterados. Si un juego envía su propio PCT_TRN, el marco de ese juego prevalece. Si el firmware no permite capturar el borde estándar antes de PCT_TRN, se conserva el marco de mGBA y se registra FALLBACK; no reemplazarlo con arte inventado.
- **Cache de arranque:** el estado de Snes9x tras inicializar N-SPC y el marco capturado se guardan de forma privada en la NES Mini, identificados por hash FNV64 de los bytes del SGBPACK1 original, bajo `/var/lib/hakchi/sgb-native-test/ikcore-sgb-prod-cache/`. Solo se reutiliza si coinciden hash, formato, firma, tamaño y se puede restaurar el save state. El primer inicio o uno con pack distinto aún deberá ejecutar el BIOS completo. No se incluye ni distribuye ninguna imagen de BIOS/ROM en el HMOD. Se registra `IKSPC FASTBOOT hit=... startup_ms=...`.
- No se modificaron el core mGBA del juego, el mailbox SPC700 de #40, las paletas SGB ni el filtro GL_NEAREST; continúa aislado de la instalación Fase6 #40.

**Validación necesaria en NES Mini**: (a) primera ejecución con firmware/pack actual y segunda (cache=HIT, startup_ms menor); (b) marco y paleta con un GB normal sin PCT_TRN y otro con PCT_TRN propio; (c) KOF96 y efectos de máquina de escribir; (d) continuar jugando más de dos minutos. Sin estas verificaciones, RC2 no debe anunciarse como producto final ni prometer 3 segundos en primera ejecución.

## Producción RC3 — pantalla de carga y cambio de marco sin intermedios

- **Pantalla visual**: tras inicializar la superficie EGL/Mali, el frontend muestra un Game Boy clásico ilustrado por píxeles RGB565 con «CARGANDO» centrado. El indicador de puntos cambia con el avance de los cuadros de arranque del firmware (cada 120 cuadros SNES) y con los cuadros GB mientras permanece oculto el juego. Es presentación en el mismo hilo, sin proceso secundario ni alteración del núcleo de audio o sus direcciones de comunicación SNES.
- **Sin borde temporal de mGBA**: el núcleo emula normalmente, pero el callback de video no muestra sus frames provisionales mientras la pantalla de carga está visible. Los paquetes PAL, ATTR, CHR_TRN y PCT_TRN siguen procesándose.
- **Cambio directo al marco de juego**: si hay PCT_TRN de la ROM, el video se revela tras 30 cuadros sin nuevas transferencias, para permitir completar el mapeo y evitar el marco provisional. Si la ROM no tiene mejoras SGB, se revela tras cuatro cuadros con el borde original predeterminado. Para juegos SGB que no emitan PCT_TRN hay un límite de 480 cuadros GB (~8 s), para evitar una pantalla de carga permanente; un cartucho con transferencias muy posteriores podría aun cambiar de borde más tarde.
- **Resguardo**: no altera la emulación ni el audio validado de KOF '96, los presets PAL, el filtro GL_NEAREST, ni el fin de sesión manual SELECT+START. El límite de 120 segundos permanece eliminado.
- **Resultado pendiente**: verificación física visual en NES Mini con KOF '96, un juego GB sin SGB y otro con su propio borde, además de confirmar que la imagen de carga aparece durante el bootstrap prolongado. CI prueba lógica de visibilidad y compilación ARMv7, no sustituye la inspección en pantalla real.
