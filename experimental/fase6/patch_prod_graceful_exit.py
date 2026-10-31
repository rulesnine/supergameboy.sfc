#!/usr/bin/env python3
"""RC6: ensure Clover RESET -> normal save/deinit/ALSA/EGL shutdown.

Only the native frontend is changed. Signal handlers NEVER call emulation,
file I/O or graphics APIs. The 7z launcher separately forwards termination.
"""
from pathlib import Path
import sys

def once(s,old,new,label):
    n=s.count(old)
    if n!=1: raise ValueError(f"{label}: expected one anchor got {n}")
    return s.replace(old,new,1)

def patch(s):
    s=once(s,"#include <errno.h>","#include <errno.h>\n#include <signal.h>","signal header")
    helper=r"""
/* Restore #25 Clover signal lifecycle to the independent mGBA launcher.
 * A handler sets only an atomic flag; normal cleanup writes SRAM/suspend. */
static volatile sig_atomic_t ik_rc6_exit_signal=0;
static void ik_rc6_on_signal(int sig) {
    if(!ik_rc6_exit_signal)ik_rc6_exit_signal=(sig_atomic_t)sig;
}
static int ik_rc6_install_signal_handlers(void) {
    struct sigaction sa;
    memset(&sa,0,sizeof sa);
    sa.sa_handler=ik_rc6_on_signal;
    sigemptyset(&sa.sa_mask);
    if(sigaction(SIGTERM,&sa,NULL))return 0;
    if(sigaction(SIGINT,&sa,NULL))return 0;
    if(sigaction(SIGHUP,&sa,NULL))return 0;
    if(sigaction(SIGQUIT,&sa,NULL))return 0;
    return 1;
}
"""
    s=once(s,"int main(int argc, char **argv)\n{",helper+"\nint main(int argc, char **argv)\n{","signal handler")
    s=once(s,"    log_open();\n    pack_path = select_pack_path(argc, argv);",
           """    log_open();
    if(!ik_rc6_install_signal_handlers())
        log_printf("IKEXIT ERROR: no se instalaron todas las senales de cierre\\n");
    else
        log_printf("IKEXIT handlers=SIGTERM,SIGINT,SIGHUP,SIGQUIT\\n");
    pack_path = select_pack_path(argc, argv);""","install before launching cores")
    s=once(s,"    while (!g_shutdown_requested && !g_swap_failed) {",
           "    while (!g_shutdown_requested && !g_swap_failed && !ik_rc6_exit_signal) {",
           "exit loop")
    s=once(s,"cleanup:\n    if(game_loaded)ik_suspend_save();",
           """cleanup:
    if(ik_rc6_exit_signal)
        log_printf("IKEXIT signal=%d graceful_persistence=1\\n",
                   (int)ik_rc6_exit_signal);
    if(game_loaded)ik_suspend_save();""","shutdown before persistence")
    s=once(s,'    log_printf("exit reason : %s\\n",\n               g_user_exit ? "SELECT+START" :',
          '    log_printf("exit reason : %s\\n",\n               ik_rc6_exit_signal ? "CLOVER_SIGNAL" :\n               g_user_exit ? "SELECT+START" :',
          "signal exit reason")
    return s

if __name__=="__main__":
    if len(sys.argv)!=2: raise SystemExit("usage: patch_prod_graceful_exit.py FRONTEND.c")
    p=Path(sys.argv[1]);p.write_text(patch(p.read_text()))
    print("PASS: RC6 graceful SIGTERM/RESET exit with save before unload")
