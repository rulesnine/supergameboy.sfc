#!/usr/bin/env python3
"""F6 one-file Super Game Boy pack support, applied to the generated frontend.
A single verified SGBPACK1 .sfc supplies both the mGBA GB cart (in memory)
and the original SGB #117 firmware. Raw .gb + .sfc remains supported.
"""
from pathlib import Path
import sys
def replace_once(s,old,new,label):
    n=s.count(old)
    if n!=1:raise ValueError(f"{label}: wanted one anchor, found {n}")
    return s.replace(old,new,1)
def patch(s):
    s=replace_once(s,'#include "ik_spc_host.h"\n',
        '#include "ik_spc_host.h"\n#include "ik_sgbpack_rom.h"\n',
        'SGBPACK GB loader header')
    s=replace_once(s, 'int main(int argc, char **argv)\n{',
        r'''static const char *ik_f6_select_gb(int argc,char **argv) {
    int i;
    for(i=1;i<argc;i++){
        const char *ext;
        if(!argv[i] || argv[i][0]=='-')continue;
        ext=strrchr(argv[i],'.');
        if(ext && (!strcasecmp(ext,".gb") ||
                   !strcasecmp(ext,".gbc") ||
                   !strcasecmp(ext,".dmg")))return argv[i];
    }
    return NULL;
}
int main(int argc, char **argv)
{''', 'GB argument parsing')
    s=replace_once(s,'    const char *pack_path;\n',
        '''    const char *pack_path;
    const char *gb_arg=NULL;
    const char *sgb_pack_arg=NULL;
    uint8_t *f6_gb_rom=NULL;
    size_t f6_gb_size=0;
    char f6_pack_result[200]={0};
''','F6 load state')
    s=replace_once(s,'    pack_path = select_pack_path(argc, argv);\n',
        '''    gb_arg=ik_f6_select_gb(argc,argv);
    sgb_pack_arg=ik_f6_select_pack(argc,argv);
    pack_path=gb_arg ? gb_arg : sgb_pack_arg;
''', 'pack and GB path selection')
    s=replace_once(s,'    log_printf("SGBPACK     : %s\\n", pack_path);\n',
        '''    log_printf("GB source   : %s\\n",pack_path);
    log_printf("SGB firmware: %s\\n",sgb_pack_arg);
''', 'correct source label')
    s=replace_once(s,
        '    if (init_egl() != 0) {\n',
        '''    if(!gb_arg) {
        if(!ik_f6_sgbpack_extract_gb(sgb_pack_arg,&f6_gb_rom,&f6_gb_size,
                                     f6_pack_result,sizeof f6_pack_result)) {
            log_printf("IKF6 PACK ERROR: %s | %s\\n",sgb_pack_arg,f6_pack_result);
            goto cleanup;
        }
        log_printf("IKF6 PACK OK: %s | GB bytes=%zu | loaded to memory\\n",
                   f6_pack_result,f6_gb_size);
    }

    if (init_egl() != 0) {
''','embedded ROM extraction')
    s=replace_once(s,'    game.path = pack_path;\n    game.data = NULL;\n    game.size = 0;\n',
        '''    game.path = pack_path;
    game.data = f6_gb_rom;
    game.size = f6_gb_size;
''', 'mGBA in-memory load')
    s=replace_once(s, '    close_core();\n',
        '''    close_core();
    free(f6_gb_rom);
    f6_gb_rom=NULL;
''', 'free ROM after core teardown')
    s=replace_once(s,
        'log_printf("IK CORE FASE6 FIRST REAL SGBPACK1 N-SPC / mGBA HYBRID EXPERIMENT\\n");',
        'log_printf("IK CORE FASE6 SGBPACK1 SINGLE FILE / mGBA + N-SPC EXPERIMENT\\n");',
        'one-file build banner')
    return s
if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("Usage: patch_f6_sgbpack_single_file.py GENERATED_FRONTEND.c")
    path=Path(sys.argv[1])
    path.write_text(patch(path.read_text()))
    print("PASS: SGBPACK1 one-file firmware + GB ROM memory handoff, legacy two-file preserved")
