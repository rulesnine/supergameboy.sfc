#!/usr/bin/env python3
"""Patch only generated mGBA SGB preview frontend for experimental dual-libretro
SGBPACK1 BIOS boot and audio-only SPC handoff. #26 and #43 not touched.
"""
from pathlib import Path
import sys

def once(s,a,b,tag):
    n=s.count(a)
    if n!=1:raise ValueError(f"{tag}: expected one anchor, got {n}")
    return s.replace(a,b,1)
def patch(s):
    s=once(s,'#include "libretro.h"\n',
      '#include "libretro.h"\n#include "ik_spc_host.h"\n#include "ik_sgb_spc_route.h"\n#include "ik_sgb_bridge.h"\n','includes')
    s=once(s,'#define IKCORE_CORE_PATH "/usr/lib/ikcore-fase5-sgb/mgba_libretro.so"',
      '#define IKCORE_CORE_PATH "/usr/lib/ikcore-fase6/mgba_libretro.so"','mGBA core path')
    s=once(s,'#define IKCORE_LOG_PATH IKCORE_STATE_DIR "/ikcore-fase5-sgb-__IKCORE_RUN_NUMBER__.log"',
      '#define IKCORE_LOG_PATH IKCORE_STATE_DIR "/ikcore-fase6-hybrid-__IKCORE_RUN_NUMBER__.log"\n'
      '#define IKCORE_F6_SPC_CORE "/usr/lib/ikcore-fase6/ikcore_spc_libretro.so"\n'
      '#define IKCORE_F6_DEFAULT_PACK IKCORE_STATE_DIR "/KOF96_SGBPACK_v1_REUPLOAD.sfc"','log and SNES path')
    s=once(s,'static void (*ikcore_fase5_stats)(uint64_t *,uint64_t *,uint64_t *,uint64_t *);',
      'static IkF6SpcHost g_f6_spc;\n'
      'static IkSgbSpcRoute g_f6_route;\n'
      'static int g_f6_ready;\n'
      'static int (*ikcore_f6_pop)(IkSgbPacket *);\n'
      'static int (*ikcore_f6_sou_pop)(uint8_t *,size_t,uint64_t *);\n'
      'static void (*ikcore_fase5_stats)(uint64_t *,uint64_t *,uint64_t *,uint64_t *);','SPC state')
    s=once(s,'    if (!ikcore_fase5_sgb_status) log_printf("WARN: SGB mode status not present\\n");',
      '    if (!ikcore_fase5_sgb_status) log_printf("WARN: SGB mode status not present\\n");\n'
      '    *(void **)(&ikcore_f6_pop) = dlsym(g_libcore, "ikcore_fase5_sgb_pop_packet");\n'
      '    if (!ikcore_f6_pop) log_printf("IKSPC ERROR: mGBA SGB queue unavailable\\n");\n'
      '    *(void **)(&ikcore_f6_sou_pop) = dlsym(g_libcore, "ikcore_fase6_sou_trn_pop");\n'
      '    if (!ikcore_f6_sou_pop) log_printf("IKSPC ERROR: mGBA SOU_TRN transfer capture unavailable\\n");',
      'mGBA packet symbol')
    s=once(s,'    for (i = 0; i < frames; ++i) {\n'
      '        g_audio_ring[g_audio_ring_write * 2u + 0u] = data[i * 2u + 0u];\n'
      '        g_audio_ring[g_audio_ring_write * 2u + 1u] = data[i * 2u + 1u];',
      '    for (i = 0; i < frames; ++i) {\n'
      '        int16_t l = data[i * 2u + 0u], r = data[i * 2u + 1u];\n'
      '        if (g_f6_ready) ik_f6_spc_mix_one(&g_f6_spc, &l, &r);\n'
      '        g_audio_ring[g_audio_ring_write * 2u + 0u] = l;\n'
      '        g_audio_ring[g_audio_ring_write * 2u + 1u] = r;',
      'GB+SPC ALSA mix')
    s=once(s,'int main(int argc, char **argv)\n{',
      '''static int ik_f6_sound_sink(const uint8_t packet[16],uint64_t cycle,void *ctx)
{
    (void)cycle;
    return ik_f6_spc_sound((IkF6SpcHost*)ctx,packet);
}
static int ik_f6_transfer_sink(const uint8_t bytes[4096],uint64_t cycle,void *ctx)
{
    (void)cycle;
    return ik_f6_spc_transfer((IkF6SpcHost*)ctx,bytes,4096);
}
static const char *ik_f6_select_pack(int argc,char **argv)
{
    int i;
    for(i=1;i<argc;++i){
        const char *ext;
        if (!argv[i] || argv[i][0]=='-') continue;
        ext=strrchr(argv[i],'.');
        if(ext && (!strcasecmp(ext,".sfc") || !strcasecmp(ext,".smc")))
            return argv[i];
    }
    return IKCORE_F6_DEFAULT_PACK;
}
int main(int argc, char **argv)
{''', 'F6 callbacks/pack parser')
    s=once(s,'log_printf("IK CORE FASE5 SGB PREVIEW - mGBA + automatic SGB border, SNES SPC not connected\\n");',
      'log_printf("IK CORE FASE6 FIRST REAL SGBPACK1 N-SPC / mGBA HYBRID EXPERIMENT\\n");',
      'F6 title')
    s=once(s,'    log_printf("video path  : RGB565 Mali; borde SGB atomico, fade visual desactivado\\n");',
      '''    /* Start the independently initialized N-SPC program from the user's
       * own SGBPACK1. Never run a second GB CPU during gameplay.
       * If firmware is absent, preserve GB audio/video and emit a hard
       * diagnostic rather than synthesizing fake SNES effects. */
    ik_sgb_spc_route_init(&g_f6_route,ik_f6_sound_sink,ik_f6_transfer_sink,&g_f6_spc);
    log_printf("IKSPC SGBPACK1 requested: %s\\n",ik_f6_select_pack(argc,argv));
    g_f6_ready=ik_f6_spc_start(&g_f6_spc,IKCORE_F6_SPC_CORE,
                               ik_f6_select_pack(argc,argv),g_audio_rate,log_printf);
    if(!g_f6_ready) log_printf("IKSPC initialized=0; SNES audio not available\\n");
    log_printf("video path  : RGB565 Mali; borde SGB atomico, fade visual desactivado\\n");''',
      'SPC startup after ALSA')
    s=once(s,'        core_retro_run();\n',
      '''        if(g_f6_ready) ik_f6_spc_frame(&g_f6_spc);
        core_retro_run();
        if(ikcore_f6_pop) {
            IkSgbPacket msg;
            unsigned consumed=0;
            while(consumed<64 && ikcore_f6_pop(&msg)) {
                ik_sgb_spc_route_packet(&g_f6_route,&msg);
                ++consumed;
            }
        }
        if(ikcore_f6_sou_pop) {
            uint8_t payload[IK_SGB_TRANSFER_SIZE];
            uint64_t completed_frame=0;
            while(ikcore_f6_sou_pop(payload,sizeof(payload),&completed_frame)) {
                IkSgbTransfer transfer;
                if(ik_sgb_transfer_capture(&transfer,0x09,payload,
                                           sizeof(payload),completed_frame))
                    (void)ik_sgb_spc_route_transfer(&g_f6_route,&transfer);
            }
        }
''','SPC advance and packet routing on one emulation thread')
    s=once(s,'            if (g_f6_ready && g_f6_spc.mailbox_stats) {
                uint64_t mb[9]={0};
                if (g_f6_spc.mailbox_stats(mb,9))
                    log_printf("IKSGB MAILBOX rx=%llu dispatched=%llu idle=%llu"
                               " ack=%llu retries=%llu timeout=%llu"
                               " pending=%llu maxwait=%llu rejected=%llu\\n",
                               (unsigned long long)mb[0],
                               (unsigned long long)mb[1],
                               (unsigned long long)mb[2],
                               (unsigned long long)mb[3],
                               (unsigned long long)mb[4],
                               (unsigned long long)mb[5],
                               (unsigned long long)mb[6],
                               (unsigned long long)mb[7],
                               (unsigned long long)mb[8]);
            }
            last_run_frames = run_frames;',
      '''            log_printf("IKSPC initialized=%d SOUND received=%llu sent=%llu"
                       " undelivered=%llu SOU_TRN=%llu transfer_done=%llu"
                       " SNES_PCM_mixed=%llu silent=%llu FIFO=%zu"
                       " SPC_frames=%llu clip=%llu\\n",
                g_f6_ready,
                (unsigned long long)g_f6_route.sound_packets,
                (unsigned long long)g_f6_route.sound_delivered,
                (unsigned long long)g_f6_route.sound_no_backend,
                (unsigned long long)g_f6_route.transfer_requested,
                (unsigned long long)g_f6_route.transfer_delivered,
                (unsigned long long)g_f6_spc.mixed,
                (unsigned long long)g_f6_spc.silence,
                g_f6_spc.fifo_count,
                (unsigned long long)g_f6_spc.frames_advanced,
                (unsigned long long)g_f6_spc.clipped);
            last_run_frames = run_frames;''','one-second SNES log')
    s=once(s,'cleanup:\n    if (game_loaded', 
      'cleanup:\n    ik_f6_spc_stop(&g_f6_spc);\n    if (game_loaded',
      'SPC deinit')
    return s
if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit('Usage: patch_mgba_f6_hybrid.py GENERATED_FRONTEND.c')
    f=Path(sys.argv[1]);f.write_text(patch(f.read_text()))
    print('PASS: F6 dual-library SPC bootstrap, GB+SPC ALSA mixing, packet routing')
