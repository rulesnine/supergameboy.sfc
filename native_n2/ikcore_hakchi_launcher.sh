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
trap 'exit 130' 1 2 15

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
"$CORE" "$rom" "$@"
result=$?
echo "Ik Core salió con código $result" >> "$LOG"
exit "$result"
