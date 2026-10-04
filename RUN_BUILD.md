# Cómo iniciar la compilación

GitHub no ejecuta automáticamente workflows generados por la misma integración.

1. Abre este repositorio en GitHub.
2. Pulsa **Actions**.
3. En la columna izquierda selecciona **Build SuperSnes9x SGBPACK**.
4. Pulsa **Run workflow**.
5. Deja la rama en **main** y pulsa el botón verde **Run workflow**.
6. Espera a que termine.
7. Abre la ejecución y descarga el artifact **SuperSnes9x-SGBPACK-Windows-x64**.

El ZIP generado debe contener:
- SuperSnes9x-SGBPACK-x64.exe
- supersnes9x_sgbpack_libretro-x64.dll
- README-SGBPACK.txt
- hashes SHA-256

Si la compilación falla, no cambies nada: copia el enlace de la ejecución o dime que falló y revisaré los logs.
