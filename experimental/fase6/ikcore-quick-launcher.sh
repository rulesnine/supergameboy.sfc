#!/bin/sh
# Fase 6 Hakchi: accept original .sfc.7z SGBPACK1 without changing games.
# Self-contained 7zr in /usr/lib/ikcore-sgb-quick; extract to private volatile /tmp.
set -eu
umask 077
CORE=/usr/lib/ikcore-sgb-quick/ikcore-sgb-quick-n2
EXTRACTOR=/usr/lib/ikcore-sgb-quick/7zr
TMP=
finish() {
  if [ -n "$TMP" ] && [ -d "$TMP" ]; then rm -rf "$TMP"; fi
}
trap finish 0
trap 'exit 130' 2
trap 'exit 143' 15

if [ ! -x "$CORE" ]; then
  echo "IKQS ERROR: falta el ejecutable del emulador: $CORE" >&2
  exit 126
fi
if [ "$#" -eq 0 ]; then
  echo "Uso: ikcore-sgb-quick-hybrid /var/games/.../juego.sfc.7z" >&2
  exit 2
fi

case "$1" in
  *.sfc.7z|*.SFC.7Z|*.gb.7z|*.GB.7Z|*.gbc.7z|*.GBC.7Z)
    ARCHIVE=$1
    IKF6_ORIGINAL_ARCHIVE=$ARCHIVE
    export IKF6_ORIGINAL_ARCHIVE
    if [ ! -f "$ARCHIVE" ]; then
      echo "IKQS ERROR: no existe el archivo comprimido: $ARCHIVE" >&2
      exit 2
    fi
    if [ ! -x "$EXTRACTOR" ]; then
      echo "IKQS ERROR: extractor ARMv7 7zr ausente del HMOD" >&2
      exit 126
    fi
    TMP=$(mktemp -d /tmp/ikf6-7z.XXXXXX) || exit 1
    echo "IKQS ARCHIVE: extrayendo desde $ARCHIVE" >&2
    if ! "$EXTRACTOR" x -y "-o$TMP" "$ARCHIVE" >/dev/null; then
      echo "IKQS ERROR: el archivo 7z está dañado o usa un códec incompatible" >&2
      exit 3
    fi
    COUNT=$(find "$TMP" -type f | wc -l | tr -d ' ')
    if [ "$COUNT" != 1 ]; then
      echo "IKQS ERROR: se esperaba un solo juego en 7z; encontrados: $COUNT" >&2
      exit 4
    fi
    GAME=$(find "$TMP" -type f | head -n 1)
    case "$ARCHIVE:$GAME" in
      *.sfc.7z:*.sfc|*.SFC.7Z:*.SFC|*.gb.7z:*.gb|*.GB.7Z:*.GB|*.gbc.7z:*.gbc|*.GBC.7Z:*.GBC)
        ;;
      *)
        echo "IKQS ERROR: el tipo de archivo interno no coincide con el comprimido" >&2
        exit 5 ;;
    esac
    echo "IKQS ARCHIVE OK: contenido extraído temporalmente" >&2
    shift
    case "$ARCHIVE" in
      *.sfc.7z|*.SFC.7Z)
        # Preserve Clover --save-on-quit, --load-state-file and
        # --save-screenshot-on-quit. Only discard obsolete second firmware.
        case "${1:-}" in
          *.sfc|*.SFC|*.smc|*.SMC)
            echo "IKQS ARCHIVE: firmware redundante omitido" >&2
            shift ;;
        esac
        set -- "$GAME" "$@"
        ;;
      *)
        # GB archive: preserve optional SGBPACK1 and all Clover args.
        set -- "$GAME" "$@"
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
