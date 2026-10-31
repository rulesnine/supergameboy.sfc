# Ik Core SGB — Producción RC1, NES Mini ARMv7

**Objetivo**: ejecutar cartuchos clásicos de Game Boy compatibles con SGB con su color y marco; mantener el marco SGB predeterminado cuando el juego no incluya su propio marco. Distribución separada del emulador experimental Fase 6 #40.

## Arquitectura retenida

- **Base congelada:** commit `6afcfcba59f3f72471a3a8ce8aac932044fc5ecc` (Fase 6 #40; funcionamiento a 59.73 FPS y sonido SNES SPC700 validado físicamente con KOF '96).
- mGBA 0.10.5 — CPU, PPU, APU y parser de SGB; Snes9x #117 aislado para los efectos SPC700/DSP.
- Se mantienen los 3 mecanismos presentes en #40: forzar SGB solamente para ROMs compatibles DMG; dibujar el marco genérico incluido en mGBA al reset; respetar los paquetes PALxx/ATTR/CHR_TRN/PCT_TRN enviados por la ROM sin recolor ni reemplazo.
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
