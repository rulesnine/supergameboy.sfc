#!/bin/sh
# Fase 6 Hakchi: accept original .sfc.7z SGBPACK1 without changing games.
# Self-contained 7zr in /usr/lib/ikcore-fase6; extract to private volatile /tmp.
set -eu
umask 077
CORE=/usr/lib/ikcore-fase6/ikcore-fase6-n2
EXTRACTOR=/usr/lib/ikcore-fase6/7zr
TMP=
finish() {
  if [ -n "$TMP" ] && [ -d "$TMP" ]; then rm -rf "$TMP"; fi
}
trap finish 0
trap 'exit 130' 2
trap 'exit 143' 15

if [ ! -x "$CORE" ]; then
  echo "IKF6 ERROR: falta el ejecutable del emulador: $CORE" >&2
  exit 126
fi
if [ "$#" -eq 0 ]; then
  echo "Uso: ikcore-fase6-hybrid /var/games/.../juego.sfc.7z" >&2
  exit 2
fi

case "$1" in
  *.sfc.7z|*.SFC.7Z|*.gb.7z|*.GB.7Z|*.gbc.7z|*.GBC.7Z)
    ARCHIVE=$1
    IKF6_ORIGINAL_ARCHIVE=$ARCHIVE
    export IKF6_ORIGINAL_ARCHIVE
    if [ ! -f "$ARCHIVE" ]; then
      echo "IKF6 ERROR: no existe el archivo comprimido: $ARCHIVE" >&2
      exit 2
    fi
    if [ ! -x "$EXTRACTOR" ]; then
      echo "IKF6 ERROR: extractor ARMv7 7zr ausente del HMOD" >&2
      exit 126
    fi
    TMP=$(mktemp -d /tmp/ikf6-7z.XXXXXX) || exit 1
    echo "IKF6 ARCHIVE: extrayendo desde $ARCHIVE" >&2
    if ! "$EXTRACTOR" x -y "-o$TMP" "$ARCHIVE" >/dev/null; then
      echo "IKF6 ERROR: el archivo 7z está dañado o usa un códec incompatible" >&2
      exit 3
    fi
    COUNT=$(find "$TMP" -type f | wc -l | tr -d ' ')
    if [ "$COUNT" != 1 ]; then
      echo "IKF6 ERROR: se esperaba un solo juego en 7z; encontrados: $COUNT" >&2
      exit 4
    fi
    GAME=$(find "$TMP" -type f | head -n 1)
    case "$ARCHIVE:$GAME" in
      *.sfc.7z:*.sfc|*.SFC.7Z:*.SFC|*.gb.7z:*.gb|*.GB.7Z:*.GB|*.gbc.7z:*.gbc|*.GBC.7Z:*.GBC)
        ;;
      *)
        echo "IKF6 ERROR: el tipo de archivo interno no coincide con el comprimido" >&2
        exit 5 ;;
    esac
    echo "IKF6 ARCHIVE OK: contenido extraído temporalmente" >&2
    shift
    case "$ARCHIVE" in
      *.sfc.7z|*.SFC.7Z)
        # SGBPACK1 contains BOTH the GB cartridge and SNES firmware.
        # An obsolete second example argument must not override this pack.
        if [ "$#" -gt 0 ]; then
          echo "IKF6 ARCHIVE: usando solo SGBPACK1; segundo argumento omitido" >&2
        fi
        set -- "$GAME"
        ;;
      *)
        # Legacy two-file path: GB archive + uncompressed SGBPACK1.
        if [ "$#" -gt 0 ]; then
          PACK=$1
          set -- "$GAME" "$PACK"
        else
          set -- "$GAME"
        fi
        ;;
    esac
    "$CORE" "$@"
    exit $?
    ;;
  *)
    # Do not alter existing .gb/.sfc invocation behavior.
    exec "$CORE" "$@"
    ;;
esac
