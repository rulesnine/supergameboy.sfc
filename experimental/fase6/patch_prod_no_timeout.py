#!/usr/bin/env python3
"""Eliminate diagnostic time limit from isolated NES Mini production frontend.
Clover SELECT+START hold and shutdown/failed swap are the only exit paths.
The frozen #40 experimental frontend is unaffected.
"""
from pathlib import Path
import sys
def once(s,a,b,k):
    if s.count(a)!=1:raise ValueError(f"{k} anchors: {s.count(a)}")
    return s.replace(a,b,1)
def patch(s):
    s=once(s, '#define IKCORE_TEST_SECONDS 120.0',
           '#define IKCORE_TEST_SECONDS 0.0 /* production: NO elapsed-time exit */','timeout constant')
    s=once(s, '    end = start + IKCORE_TEST_SECONDS;\n',
           '    end = 0.0; /* no deadline for production */\n','deadline')
    s=once(s, '    while (!g_shutdown_requested && !g_swap_failed && now_s() < end) {',
           '    while (!g_shutdown_requested && !g_swap_failed) {','main event loop')
    s=once(s, '(g_swap_failed ? "EGL swap failure" : "timeout 120 s")',
           '(g_swap_failed ? "EGL swap failure" : "controlled exit")','final reason')
    s=once(s, '    log_printf("salir       : mantener SELECT+START %.1f s\\n", IKCORE_EXIT_HOLD_SECONDS);',
           '    log_printf("salir       : mantener SELECT+START %.1f s; sin limite de tiempo\\n", IKCORE_EXIT_HOLD_SECONDS);','exit hint')
    return s
if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("Usage: patch_prod_no_timeout.py FRONTEND.c")
    p=Path(sys.argv[1]);p.write_text(patch(p.read_text()))
    print("PASS: no automatic 120-second shutdown; SELECT+START and Clover shutdown remain")
