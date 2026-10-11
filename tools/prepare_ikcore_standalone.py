#!/usr/bin/env python3
"""Turn the frozen #137 native frontend into a reusable Hakchi ROM launcher.

No SGB CPU/SPC/DSP code, audio processing, video path, or SGBPACK builder
is changed. All changes are scoped to a COPY of the native C frontend.
"""
from pathlib import Path
import sys

project = Path(__file__).resolve().parents[1]
src = project / "native_n2" / "sgbpack_native_n2.c"
dst = Path(sys.argv[1]) if len(sys.argv) > 1 else project / "dist" / "ikcore_standalone.c"
text = src.read_text(encoding="utf-8")

def once(old, new):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"standalone patch mismatch ({count}): {old[:100]!r}")
    text = text.replace(old, new, 1)

once('#define IKCORE_CORE_PATH "/usr/lib/ikcore/ikcore_sgbpack_libretro.so"',
     '#define IKCORE_CORE_PATH "/usr/lib/ikcore-standalone/ikcore_sgbpack_libretro.so"')
once('#define IKCORE_LOG_PATH IKCORE_STATE_DIR "/ikcore-sfx-only-__IKCORE_RUN_NUMBER__.log"',
     '#define IKCORE_LOG_PATH IKCORE_STATE_DIR "/ikcore-standalone-__IKCORE_RUN_NUMBER__.log"')

# No implicit KOF96 ROM: every Hakchi game points to its own SGBPACK1 .sfc.
once('    return IKCORE_DEFAULT_PACK;\n}', '    return NULL;\n}')

once('    pack_path = select_pack_path(argc, argv);\n',
     '    pack_path = select_pack_path(argc, argv);\n'
     '    if (!pack_path) {\n'
     '        log_printf("IK CORE: no SGBPACK1 .sfc/.smc was specified.\\n");\n'
     '        log_printf("Uso: /bin/ikcore /ruta/al/juego.sfc\\n");\n'
     '        goto cleanup;\n'
     '    }\n')

once('    log_printf("play test   : %.0f s a %.3f FPS objetivo\\n", IKCORE_TEST_SECONDS, target_fps);',
     '    log_printf("modo        : ilimitado (Hakchi), %.3f FPS objetivo\\n", target_fps);')
once('    end = start + IKCORE_TEST_SECONDS;',
     '    end = 0.0; /* standalone session never terminates on a benchmark timer */')
once('    while (!g_shutdown_requested && !g_swap_failed && now_s() < end) {',
     '    while (!g_shutdown_requested && !g_swap_failed) {')
once('               (g_swap_failed ? "EGL swap failure" : "timeout 120 s")));',
     '               (g_swap_failed ? "EGL swap failure" : "normal")));')

dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(text, encoding="utf-8")
print(f"IKCORE STANDALONE: ready {dst}, no embedded KOF path, no 120s timeout.")
