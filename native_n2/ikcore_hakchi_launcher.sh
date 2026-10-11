#!/bin/sh
# Hakchi archive-aware Ik Core Standalone launcher.
# The approved #137 SNES/GB/SPC core is never modified.
CORE=/usr/lib/ikcore-standalone/ikcore-standalone-native
P7ZIP=/usr/lib/ikcore-standalone/7za
P7LIB=/usr/lib/ikcore-standalone/lib
TMPBASE=/var/lib/hakchi/sgb-native-test
LOG="$TMPBASE/ikcore-standalone-__IKCORE_RUN_NUMBER__-wrapper.log"
mkdir -p "$TMPBASE" || exit 1

archive=
for arg in "$@"; do
    case "$arg" in
        *.sfc|*.smc|*.SFC|*.SMC)
            if [ -r "$arg" ]; then
                exec "$CORE" "$@"
            fi
            if [ -r "$arg.7z" ]; then
                archive="$arg.7z"
                break
            fi
            ;;
        *.sfc.7z|*.smc.7z|*.SFC.7z|*.SMC.7z)
            if [ -r "$arg" ]; then
                archive="$arg"
                break
            fi
            ;;
    esac
done

# An explicit SGBPACK1 file or an unknown Hakchi layout still uses the
# native resolver and its detailed argv log. No default game or archive scan.
if [ -z "$archive" ]; then
    exec "$CORE" "$@"
fi

{
    echo "Ik Core standalone Hakchi 7z wrapper __IKCORE_RUN_NUMBER__"
    echo "Archivo Hakchi: $archive"
} > "$LOG"

if [ ! -x "$P7ZIP" ]; then
    echo "ERROR: falta extractor 7za en HMOD." >> "$LOG"
    exit 1
fi

tmpdir="$(mktemp -d "$TMPBASE/ikcore-archive.XXXXXXXX")" || {
    echo "ERROR: no puede crear directorio temporal." >> "$LOG"
    exit 1
}

cleanup() {
    rm -rf "$tmpdir"
}
trap 'cleanup' 0
# Forward Clover's TERM request to the native child, then wait until its
# SRAM/ALSA/EGL cleanup has completed. No extra reset emulation is introduced.
child_pid=
term_requested=0
forward_termination() {
    term_requested=1
    echo "RESET wrapper: solicitud de cierre recibida; avisando al núcleo" >> "$LOG"
    if [ -n "$child_pid" ]; then
        kill -TERM "$child_pid" 2>/dev/null || true
    else
        # Interrupted during extraction: no running core or cart SRAM yet.
        exit 143
    fi
}
trap 'forward_termination' 1 2 3 15

# 7za is bundled in the HMOD and isolated from the core's runtime.
if ! LD_LIBRARY_PATH="$P7LIB" "$P7ZIP" e -y "-o$tmpdir" "$archive" > "$tmpdir/7za.log" 2>&1; then
    echo "ERROR: falló descompresión 7z." >> "$LOG"
    cat "$tmpdir/7za.log" >> "$LOG"
    exit 1
fi

rom=
for file in "$tmpdir"/*.sfc "$tmpdir"/*.smc "$tmpdir"/*.SFC "$tmpdir"/*.SMC; do
    [ -f "$file" ] || continue
    # Strictly accept only an SGBPACK1 footer; never pass a plain SNES .sfc.
    magic="$(tail -c 256 "$file" | dd bs=1 count=8 2>/dev/null)"
    if [ "$magic" = "SGBPACK1" ]; then
        if [ -n "$rom" ]; then
            echo "ERROR: el archivo contiene múltiples SGBPACK1." >> "$LOG"
            exit 1
        fi
        rom="$file"
    fi
done

if [ -z "$rom" ]; then
    echo "ERROR: no hay SGBPACK1 válido en el archivo comprimido." >> "$LOG"
    exit 1
fi

echo "SGBPACK1 extraído temporalmente: $rom" >> "$LOG"
# Pass the verified, extracted ROM first: native argv resolver accepts it.
# Retain Clover flags unchanged (saving, screenshot, display options).
"$CORE" "$rom" "$@" &
child_pid=$!
wait "$child_pid"
result=$?
# In BusyBox ash, the first wait can return immediately when the TERM trap
# runs. Do not remove the temp pack until the native child has really exited.
if [ "$term_requested" -eq 1 ]; then
    wait "$child_pid" 2>/dev/null
    child_result=$?
    if [ "$child_result" -ne 127 ]; then
        result=$child_result
    fi
fi
child_pid=
echo "Ik Core salió con código $result; señal-recibida=$term_requested" >> "$LOG"
exit "$result"
