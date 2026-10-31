#!/usr/bin/env python3
"""Recover Ik Core #25 Clover suspend + GB battery SRAM for RC5 mGBA.
No change to BIOS/SPC cache, SGB video, SNES audio or libretro API.
Generates ONE frontend from existing project files; stable RC4 untouched.
"""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]

def once(s,a,b,tag):
    n=s.count(a)
    if n!=1: raise RuntimeError(f"{tag}: expected 1 anchor got {n}: {a[:72]!r}")
    return s.replace(a,b,1)

def adapted_suspend():
    # Reuse the validated PNG encoder, per-Clover explicit path handling,
    # atomic state writes, CRC checking and screen ownership from NES Mini #25.
    s=(root/"native_n2/ikcore_suspend.inc").read_text()
    s=s.replace("IKCSUSP1","IKCSUSP2")
    s=once(s,"ik_susp_get32(h+12)!=1","ik_susp_get32(h+12)!=2","state version load")
    s=once(s,"ik_susp_le32(h+12,1);","ik_susp_le32(h+12,2);","state version save")
    # mGBA provides its own savestate format; an Snes9x SGB! state must NEVER
    # be sent to the mGBA core. Old IKCSUSP1 files are preserved unmodified.
    at=s.index('    /* The #137 PERF2 core starts in the SNES-side Super Game Boy BIOS.')
    end=s.index('static void ik_suspend_finish(void)',at)
    block=r'''    /* The new ROM snapshot is mGBA-specific, not a Snes9x SGB! blob.
     * Defer restore until the first mGBA frame, after its save RAM setup.
     */
    ik_suspend_pending=snapshot;
    ik_suspend_pending_size=size;
    log_printf("IKSAVE SUSP PENDING: %zu bytes (mGBA format)\n",size);
}
static void ik_suspend_maybe_restore(void) {
    size_t expected;
    if(!ik_suspend_pending)return;
    expected=core_retro_serialize_size();
    if(expected==ik_suspend_pending_size &&
       core_retro_unserialize(ik_suspend_pending,ik_suspend_pending_size)) {
        ik_prod_sram_rebase();
        log_printf("IKSAVE SUSP LOAD OK: %zu bytes\n",ik_suspend_pending_size);
    } else {
        log_printf("IKSAVE SUSP LOAD REJECTED: expected=%zu got=%zu; original retained\n",
                   expected,ik_suspend_pending_size);
    }
    free(ik_suspend_pending);
    ik_suspend_pending=NULL;
    ik_suspend_pending_size=0;
}
'''
    s=s[:at]+block+s[end:]
    # Preserve prior #25 states; don't overwrite a file from an older ABI,
    # a third-party core, or an unrecognized format.
    a="    total=size+sizeof h;\n"
    b=r'''    {
        FILE *previous=fopen(path,"rb");
        if(previous) {
            uint8_t old[8];
            int compatible=fread(old,1,sizeof old,previous)==sizeof old &&
                            memcmp(old,"IKCSUSP2",8)==0;
            fclose(previous);
            if(!compatible) {
                log_printf("IKSAVE SUSP: existing legacy/unknown file protected: %s\n",path);
                return 0;
            }
        } else if(errno!=ENOENT) {
            return 0;
        }
    }
    total=size+sizeof h;
'''
    s=once(s,a,b,"protect older state on save")
    # Keep original PNG implementation and its RGB555/RGB565 handling.
    # Accept memory-identical mGBA serialized snapshots, not only SGB! v11.
    first=s.index("    /* Never generate a misleading Clover point during the preliminary BIOS")
    last=s.index("    if(ik_susp_save_file(ik_suspend_output,data,n)) {",first)
    s=s[:first]+r'''    /* mGBA's serialized state is kept opaque; header v2 + CRC + ROM
     * fingerprint protect the resume file. No Snes9x-only signature check. */
'''+s[last:]
    # Original routine requires an 11-char CLV ID; prefer explicit Clover
    # arguments, then the original archive, then content-derived fallback.
    mark="    if(!ik_suspend_clv[0] || !core_retro_serialize_size ||"
    add=r'''    if(!ik_suspend_clv[0]) {
        const char *original=getenv("IKF6_ORIGINAL_ARCHIVE");
        if(original) (void)ikcore_extract_clv_id(original,ik_suspend_clv);
    }
    if(!ik_suspend_clv[0]) {
        uint64_t hash=ik_susp_hash_pack(pack_path);
        if(hash)snprintf(ik_suspend_clv,sizeof ik_suspend_clv,
                         "GB-%08x",(unsigned)(hash^(hash>>32)));
    }
'''
    s=once(s,mark,add+mark,"extract original archive or fallback ID")
    # SGBPACK1 filename may be temporary but its hash is stable byte-wise.
    # no direct access to the BIOS firmware cache, kept wholly separate.
    return s

def patch(src):
    s=src
    s=once(s,'static void (*core_retro_run)(void);',
        '''static void (*core_retro_run)(void);
static size_t (*core_retro_serialize_size)(void);
static bool (*core_retro_serialize)(void *,size_t);
static bool (*core_retro_unserialize)(const void *,size_t);''',"declare state exports")
    s=once(s,'    LOAD_CORE(retro_run);',
        '''    LOAD_CORE(retro_run);
    LOAD_CORE(retro_serialize_size);
    LOAD_CORE(retro_serialize);
    LOAD_CORE(retro_unserialize);
    LOAD_CORE(retro_get_memory_data);
    LOAD_CORE(retro_get_memory_size);''',"load state/ram exports")
    sram=(root/"experimental/fase6/ik_prod_sram.inc").read_text()
    suspend=adapted_suspend()
    start=suspend.index("static const void *ik_suspend_last_frame = NULL;")
    finish=suspend.index("\nstatic void ik_susp_le32",start)
    globals=suspend[start:finish]
    suspend=suspend[:start]+suspend[finish:]
    cap=r'''    if(data && ik_suspend_capture_enabled && width && height &&
       width<=512u && height<=512u && now_s()>=ik_suspend_next_capture) {
        size_t rowbytes=(size_t)width *
            ((g_pixel_format==RETRO_PIXEL_FORMAT_XRGB8888)?4u:2u);
        size_t need=rowbytes*(size_t)height;
        if(pitch>=rowbytes && pitch<=8192u && need<=512u*512u*4u) {
            if(need>ik_suspend_framebuffer_capacity) {
                uint8_t *newbuf=(uint8_t*)realloc(ik_suspend_framebuffer,need);
                if(newbuf) {
                    ik_suspend_framebuffer=newbuf;
                    ik_suspend_framebuffer_capacity=need;
                }
            }
            if(ik_suspend_framebuffer_capacity>=need) {
                unsigned y;
                for(y=0;y<height;y++)
                    memcpy(ik_suspend_framebuffer+(size_t)y*rowbytes,
                           (const uint8_t*)data+(size_t)y*pitch,rowbytes);
                ik_suspend_last_frame=ik_suspend_framebuffer;
                ik_suspend_frame_width=width;
                ik_suspend_frame_height=height;
                ik_suspend_frame_pitch=rowbytes;
                ik_suspend_capture_format=g_pixel_format;
                ik_suspend_next_capture=now_s()+0.5;
            }
        }
    }
'''
    s=once(s,"static void video_cb(const void *data, unsigned width, unsigned height, size_t pitch)\n{",
       globals+"\nstatic void video_cb(const void *data, unsigned width, unsigned height, size_t pitch)\n{\n"+cap,
       "capture screenshot from live video")
    s=once(s,"int main(int argc, char **argv)\n{",
       sram+"\n"+suspend+"\nint main(int argc, char **argv)\n{",
       "inject persistence from validated #25")
    s=once(s,"    game_loaded = 1;",
       '''    game_loaded = 1;
    ik_prod_sram_initialize(argc,argv,pack_path,f6_gb_rom,f6_gb_size);
    ik_suspend_initialize(argc,argv,pack_path);''',
       "load SRAM before first frame, suspend state separately")
    s=once(s,"        core_retro_run();",
       '''        core_retro_run();
        ik_suspend_maybe_restore();
        ik_prod_sram_flush(0);''',
       "restore deferred state and five-second SRAM check")
    s=once(s,"cleanup:\n",
       '''cleanup:
    if(game_loaded)ik_suspend_save();
    if(game_loaded)ik_prod_sram_flush(1);
    ik_suspend_finish();
    ik_prod_sram_finish();
    free(ik_suspend_framebuffer);
    ik_suspend_framebuffer=NULL;
''',
       "exit persistence before unloading mGBA")
    return s

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("usage: patch_prod_persistence.py GENERATED_FRONTEND.c")
    file=Path(sys.argv[1])
    file.write_text(patch(file.read_text()))
    print("PASS: RC5 mGBA SRAM + explicit Clover suspension flags and PNG restored")
