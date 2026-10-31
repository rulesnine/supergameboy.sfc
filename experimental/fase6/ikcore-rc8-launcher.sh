#!/bin/sh
# Fase 6 Hakchi: accept original .sfc.7z SGBPACK1 without changing games.
# Self-contained 7zr in /usr/lib/ikcore-sgb-rc8; extract to private volatile /tmp.
set -eu
umask 077
CORE=/usr/lib/ikcore-sgb-rc8/ikcore-sgb-rc8-n2
EXTRACTOR=/usr/lib/ikcore-sgb-rc8/7zr
TMP=
finish() {
  if [ -n "$TMP" ] && [ -d "$TMP" ]; then rm -rf "$TMP"; fi
}
trap finish 0
# Clover may send RESET termination to the shell wrapper rather than
# its child. Relay the signal, allow the child to flush SRAM/suspend PNG,
# and only then remove the temporary extracted .sfc. Never orphan the core.
IK_CHILD=
ik_stop_child() {
  rc=$1
  trap - 1 2 3 15
  if [ -n "$IK_CHILD" ]; then
    # Native process receives Clover exit first; its signal handler saves
    # SRAM and suspend PNG, then releases ALSA/EGL before shell cleanup.
    kill -TERM "$IK_CHILD" 2>/dev/null || :
    (
      sleep 4
      kill -KILL "$IK_CHILD" 2>/dev/null || :
    ) &
    watchdog=$!
    wait "$IK_CHILD" 2>/dev/null || :
    kill "$watchdog" 2>/dev/null || :
    wait "$watchdog" 2>/dev/null || :
    IK_CHILD=
  fi
  echo "IKRC8 EXIT: Clover signal=$rc, status=0, child reaped" >&2
  # Clover's RESET is a normal menu return, not an app crash (143).
  exit 0
}
trap 'ik_stop_child 129' 1
trap 'ik_stop_child 130' 2
trap 'ik_stop_child 131' 3
trap 'ik_stop_child 143' 15

if [ ! -x "$CORE" ]; then
  echo "IKRC8 ERROR: falta el ejecutable del emulador: $CORE" >&2
  exit 126
fi
if [ "$#" -eq 0 ]; then
  echo "Uso: ikcore-sgb-rc8 /var/games/.../juego.sfc.7z" >&2
  exit 2
fi

case "$1" in
  *.sfc.7z|*.SFC.7Z|*.gb.7z|*.GB.7Z|*.gbc.7z|*.GBC.7Z)
    ARCHIVE=$1
    IKF6_ORIGINAL_ARCHIVE=$ARCHIVE
    export IKF6_ORIGINAL_ARCHIVE
    if [ ! -f "$ARCHIVE" ]; then
      echo "IKRC8 ERROR: no existe el archivo comprimido: $ARCHIVE" >&2
      exit 2
    fi
    if [ ! -x "$EXTRACTOR" ]; then
      echo "IKRC8 ERROR: extractor ARMv7 7zr ausente del HMOD" >&2
      exit 126
    fi
    TMP=$(mktemp -d /tmp/ikf6-7z.XXXXXX) || exit 1
    echo "IKRC8 ARCHIVE: extrayendo desde $ARCHIVE" >&2
    if ! "$EXTRACTOR" x -y "-o$TMP" "$ARCHIVE" >/dev/null; then
      echo "IKRC8 ERROR: el archivo 7z está dañado o usa un códec incompatible" >&2
      exit 3
    fi
    COUNT=$(find "$TMP" -type f | wc -l | tr -d ' ')
    if [ "$COUNT" != 1 ]; then
      echo "IKRC8 ERROR: se esperaba un solo juego en 7z; encontrados: $COUNT" >&2
      exit 4
    fi
    GAME=$(find "$TMP" -type f | head -n 1)
    case "$ARCHIVE:$GAME" in
      *.sfc.7z:*.sfc|*.SFC.7Z:*.SFC|*.gb.7z:*.gb|*.GB.7Z:*.GB|*.gbc.7z:*.gbc|*.GBC.7Z:*.GBC)
        ;;
      *)
        echo "IKRC8 ERROR: el tipo de archivo interno no coincide con el comprimido" >&2
        exit 5 ;;
    esac
    echo "IKRC8 ARCHIVE OK: contenido extraído temporalmente" >&2
    shift
    case "$ARCHIVE" in
      *.sfc.7z|*.SFC.7Z)
        # Preserve Clover --save-on-quit, --load-state-file and
        # --save-screenshot-on-quit. Only discard obsolete second firmware.
        case "${1:-}" in
          *.sfc|*.SFC|*.smc|*.SMC)
            echo "IKRC8 ARCHIVE: firmware redundante omitido" >&2
            shift ;;
        esac
        set -- "$GAME" "$@"
        ;;
      *)
        # GB archive: preserve optional SGBPACK1 and all Clover args.
        set -- "$GAME" "$@"
        ;;
    esac
    "$CORE" "$@" &
    IK_CHILD=$!
    rc=0
    wait "$IK_CHILD" || rc=$?
    IK_CHILD=
    case "$rc" in
      129|130|131|143)
        # Clover can signal the native child rather than this wrapper.
        echo "IKRC8 EXIT: child signalled=$rc, returning to Clover cleanly" >&2
        exit 0 ;;
      *) exit "$rc" ;;
    esac
    ;;
  *)
    # Do not alter existing .gb/.sfc invocation behavior.
    exec "$CORE" "$@"
    ;;
esac
