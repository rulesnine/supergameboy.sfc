#!/usr/bin/env python3
"""Graceful NES Mini reset path for Ik Core Standalone, preserving #4 SRAM.

Only the native frontend receives the patch. Reset-button action by Clover is
not assumed: we handle the normal process termination signals, flush SRAM
using the existing #4 function, and release ALSA/EGL/control in cleanup.
Hardware RESET -> signal delivery still requires validation on a real NES Mini.
"""
from pathlib import Path
import sys

p = Path(sys.argv[1])
src = p.read_text("utf-8")

def once(before, after):
    global src
    count = src.count(before)
    if count != 1:
        raise SystemExit(f"RESET anchor count={count}: {before[:130]!r}")
    src = src.replace(before, after, 1)

once("#include <errno.h>\n", "#include <errno.h>\n#include <signal.h>\n")

# A signal handler MUST only set a sig_atomic_t: all file I/O, SRAM copy,
# libretro deinit, ALSA/EGL shutdown, and log printing are done in cleanup.
helper = r'''
/* Clover may terminate a running custom emulator when the console RESET
 * button is pressed. This is a *graceful signal exit path*, not an emulator
 * reset command and not a Hakchi suspend/save-state implementation.
 */
static volatile sig_atomic_t ik_exit_signal = 0;

static void ik_exit_signal_handler(int signo)
{
    if (ik_exit_signal == 0) ik_exit_signal = (sig_atomic_t)signo;
}

static int ik_exit_handlers_install(void)
{
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = ik_exit_signal_handler;
    sigemptyset(&sa.sa_mask);
    if (sigaction(SIGTERM, &sa, NULL) != 0) return 0;
    if (sigaction(SIGINT,  &sa, NULL) != 0) return 0;
    if (sigaction(SIGHUP,  &sa, NULL) != 0) return 0;
    if (sigaction(SIGQUIT, &sa, NULL) != 0) return 0;
    return 1;
}

static const char *ik_exit_signal_name(int sig)
{
    switch (sig) {
    case SIGTERM: return "SIGTERM";
    case SIGINT:  return "SIGINT";
    case SIGHUP:  return "SIGHUP";
    case SIGQUIT: return "SIGQUIT";
    default:      return "desconocida";
    }
}
'''
once('int main(int argc, char **argv)\n{\n', helper+'\nint main(int argc, char **argv)\n{\n')

once('    log_open();\n    pack_path = select_pack_path(argc, argv);',
     '    log_open();\n'
     '    if (!ik_exit_handlers_install())\n'
     '        log_printf("RESET WARN   : no se instalaron todas las señales de cierre.\\n");\n'
     '    else\n'
     '        log_printf("RESET        : cierre por SIGTERM/SIGINT/SIGHUP/SIGQUIT activado.\\n");\n'
     '    pack_path = select_pack_path(argc, argv);')

once('    while (!g_shutdown_requested && !g_swap_failed) {',
     '    while (!g_shutdown_requested && !g_swap_failed && !ik_exit_signal) {')

once('    if (game_loaded) ik_sram_flush(1);\n',
     '    if (ik_exit_signal)\n'
     '        log_printf("RESET        : señal %s (%d), cierre ordenado.\\n",\n'
     '                   ik_exit_signal_name((int)ik_exit_signal), (int)ik_exit_signal);\n'
     '    if (game_loaded) ik_sram_flush(1);\n')

once('    log_printf("exit reason : %s\\n",\n'
     '               g_user_exit ? "SELECT+START" :',
     '    log_printf("exit reason : %s\\n",\n'
     '               ik_exit_signal ? ik_exit_signal_name((int)ik_exit_signal) :\n'
     '               g_user_exit ? "SELECT+START" :')

p.write_text(src, encoding="utf-8")
print("IK CORE RESET: native frontend signal handling + existing SRAM flush on cleanup.")
