/* Ik Core RC8: original user-owned SGB1 BIOS audiovisual replay.
 * Cold boot runs the *real* SNES BIOS, saves losslessly delta-encoded frames
 * and 32040 Hz stereo PCM; warm launch restores SNES/SPC then presents the
 * same firmware-generated intro at video cadence ~60.0988Hz.
 * No copyrighted firmware assets shipped. Separate from savestate/SRAM.
 */
#define _POSIX_C_SOURCE 200809L
#include "ik_sgb_boot_av.h"
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#include <errno.h>
#ifndef IK_BOOT_DIR
#define IK_BOOT_DIR "/var/lib/hakchi/sgb-native-test/ikcore-sgb-quick-cache-v4"
#endif
#define IK_BOOT_PIXELS (256u*224u)
#define IK_BOOT_LIMIT (32u*1024u*1024u)
#define IK_BOOT_MAGIC "IKAV0001"
#define IK_BOOT_MAXREC (4800u*4u)
typedef struct {
    char magic[8];
    uint64_t fingerprint;
    uint32_t version,video_frames,audio_frames,records,bytes,checksum;
} IkBootHeader;
typedef struct {
    uint32_t type,size,frame;
} IkBootRec;
typedef struct {
    FILE *file;
    uint64_t hash;
    char temp[260], final[260];
    uint16_t prev[IK_BOOT_PIXELS];
    uint8_t changed[IK_BOOT_PIXELS*4u];
    unsigned video_frames,audio_frames,records,bytes;
    uint32_t checksum;
    int aborted;
} IkBootState;
static IkBootState g_av;
static void ikboot_path(char *dst,size_t n,uint64_t hash) {
    snprintf(dst,n,IK_BOOT_DIR "/boot-%016llx.bootav",
             (unsigned long long)hash);
}
static uint32_t ikboot_check(uint32_t h,const void *data,size_t n) {
    const uint8_t *p=(const uint8_t*)data;
    size_t i;
    for(i=0;i<n;++i){h^=p[i];h*=16777619u;}
    return h;
}
static int ikboot_header(FILE *f,uint64_t hash,IkBootHeader *h) {
    struct stat st;
    if(!f||fread(h,1,sizeof(*h),f)!=sizeof(*h))return 0;
    if(memcmp(h->magic,IK_BOOT_MAGIC,8)||h->version!=1u||
       h->fingerprint!=hash||h->video_frames<30u||
       h->video_frames>4800u||h->records<h->video_frames||
       h->records>IK_BOOT_MAXREC||h->bytes>IK_BOOT_LIMIT)
       return 0;
    if(fstat(fileno(f),&st)!=0 || !S_ISREG(st.st_mode) ||
       st.st_size!=(off_t)(sizeof(*h)+(size_t)h->bytes))return 0;
    return 1;
}
int ikboot_has(uint64_t hash) {
    char path[260];IkBootHeader h;
    FILE *f;
    if(!hash)return 0;
    ikboot_path(path,sizeof path,hash);
    f=fopen(path,"rb");
    if(!f)return 0;
    int ok=ikboot_header(f,hash,&h);
    fclose(f);return ok;
}
void ikboot_begin(uint64_t hash) {
    IkBootHeader empty;
    memset(&g_av,0,sizeof(g_av));
    if(!hash)return;
    if(mkdir(IK_BOOT_DIR,0700)!=0 && errno!=EEXIST)return;
    ikboot_path(g_av.final,sizeof(g_av.final),hash);
    snprintf(g_av.temp,sizeof(g_av.temp),IK_BOOT_DIR "/record-%016llx-%ld.tmp",
             (unsigned long long)hash,(long)getpid());
    g_av.file=fopen(g_av.temp,"wb+");
    if(!g_av.file)return;
    g_av.hash=hash;g_av.checksum=2166136261u;
    memset(&empty,0,sizeof empty);
    if(fwrite(&empty,1,sizeof empty,g_av.file)!=sizeof empty) {
        g_av.aborted=1;
    }
}
static int ikboot_record(unsigned type,unsigned frame,const uint8_t *p,size_t n) {
    IkBootRec r;
    if(!g_av.file||g_av.aborted)return 0;
    if(n>IK_BOOT_LIMIT || g_av.bytes>IK_BOOT_LIMIT-sizeof r-n ||
       g_av.records>=IK_BOOT_MAXREC) {
        g_av.aborted=1;return 0;
    }
    r.type=type;r.size=(uint32_t)n;r.frame=frame;
    if(fwrite(&r,1,sizeof r,g_av.file)!=sizeof r ||
       (n && fwrite(p,1,n,g_av.file)!=n)) {
        g_av.aborted=1;return 0;
    }
    g_av.checksum=ikboot_check(g_av.checksum,&r,sizeof r);
    g_av.checksum=ikboot_check(g_av.checksum,p,n);
    g_av.bytes+=(unsigned)(sizeof r+n);
    ++g_av.records;
    return 1;
}
void ikboot_video(const uint16_t *pixels,unsigned frame) {
    uint8_t *out=g_av.changed;
    size_t pos=0,used=0;
    if(!g_av.file||g_av.aborted||!pixels)return;
    while(pos<IK_BOOT_PIXELS) {
        size_t skip=0,len=0,head;
        while(pos+skip<IK_BOOT_PIXELS &&
              pixels[pos+skip]==g_av.prev[pos+skip] && skip<65535u)
            ++skip;
        pos+=skip;
        head=pos;
        while(pos<IK_BOOT_PIXELS && pixels[pos]!=g_av.prev[pos] &&
              len<65535u){++pos;++len;}
        if(!len && pos>=IK_BOOT_PIXELS)break;
        if(!len && skip==65535u) {
            /* A zero-length patch advances over an all-unchanged span. */
            if(used+4u>sizeof g_av.changed){g_av.aborted=1;return;}
            out[used++]=(uint8_t)skip;out[used++]=(uint8_t)(skip>>8);
            out[used++]=0;out[used++]=0;
            continue;
        }
        if(used+4u+len*2u>sizeof g_av.changed) {
            g_av.aborted=1;return;
        }
        out[used++]=(uint8_t)skip;out[used++]=(uint8_t)(skip>>8);
        out[used++]=(uint8_t)len;out[used++]=(uint8_t)(len>>8);
        for(size_t i=0;i<len;++i) {
            uint16_t px=pixels[head+i];
            out[used++]=(uint8_t)px;out[used++]=(uint8_t)(px>>8);
        }
    }
    if(ikboot_record(1u,frame,out,used)) {
        memcpy(g_av.prev,pixels,sizeof g_av.prev);
        ++g_av.video_frames;
    }
}
void ikboot_audio(const int16_t *stereo,size_t frames) {
    if(!stereo||!g_av.file||g_av.aborted)return;
    while(frames) {
        size_t n=frames>8192u?8192u:frames;
        if(!ikboot_record(2u,g_av.video_frames,
                          (const uint8_t *)stereo,n*4u))return;
        g_av.audio_frames+=(unsigned)n;
        stereo+=n*2u;frames-=n;
    }
}
void ikboot_end(int successful) {
    IkBootHeader h;
    if(!g_av.file)return;
    if(successful&&!g_av.aborted&&g_av.video_frames>=30u &&
       g_av.audio_frames>=256u && g_av.hash) {
        memset(&h,0,sizeof h);
        memcpy(h.magic,IK_BOOT_MAGIC,8);
        h.fingerprint=g_av.hash;h.version=1u;
        h.video_frames=g_av.video_frames;
        h.audio_frames=g_av.audio_frames;
        h.records=g_av.records;h.bytes=g_av.bytes;h.checksum=g_av.checksum;
        if(fseek(g_av.file,0,SEEK_SET)==0 &&
           fwrite(&h,1,sizeof h,g_av.file)==sizeof h &&
           fflush(g_av.file)==0 && fsync(fileno(g_av.file))==0 &&
           fclose(g_av.file)==0) {
            g_av.file=NULL;
            if(rename(g_av.temp,g_av.final)==0)return;
        }else g_av.file=NULL;
    }
    if(g_av.file)fclose(g_av.file);
    g_av.file=NULL;
    unlink(g_av.temp);
}
static double ikboot_secs(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC,&t);
    return t.tv_sec+t.tv_nsec*1e-9;
}
static void ikboot_until(double end,int (*cancel)(void)) {
    while(!cancel||!cancel()) {
        double left=end-ikboot_secs();
        if(left<=0.0)break;
        if(left>0.03)left=0.03;
        struct timespec t={(time_t)left,(long)((left-(time_t)left)*1e9)};
        nanosleep(&t,NULL);
    }
}
int ikboot_play(uint64_t hash,
                void (*video)(const uint16_t *,unsigned),
                size_t (*audio)(const int16_t *,size_t),
                int (*cancel)(void),
                void (*log)(const char *,...)) {
    char path[260];IkBootHeader h;
    IkBootRec r;uint8_t *buffer=NULL;
    uint16_t *frame=NULL;uint32_t check=2166136261u;
    unsigned played=0,pcm=0;
    int valid=0;
    FILE *f=NULL;
    if(!video||!audio||!ikboot_has(hash))return 0;
    ikboot_path(path,sizeof path,hash);
    f=fopen(path,"rb");
    if(!ikboot_header(f,hash,&h))goto done;
    buffer=(uint8_t*)malloc(256u*1024u);
    frame=(uint16_t*)calloc(IK_BOOT_PIXELS,sizeof(uint16_t));
    if(!buffer||!frame)goto done;
    double start=ikboot_secs();
    for(unsigned rec=0;rec<h.records;++rec) {
        if(cancel&&cancel())goto done;
        if(fread(&r,1,sizeof r,f)!=sizeof r ||
           r.size>256u*1024u ||
           (r.type!=1u&&r.type!=2u) ||
           fread(buffer,1,r.size,f)!=r.size)goto done;
        check=ikboot_check(check,&r,sizeof r);
        check=ikboot_check(check,buffer,r.size);
        if(r.type==1u) {
            size_t index=0,k=0;
            while(k<r.size) {
                unsigned skip,len;
                if(r.size-k<4u)goto done;
                skip=(unsigned)buffer[k] | ((unsigned)buffer[k+1u]<<8);
                len=(unsigned)buffer[k+2u] | ((unsigned)buffer[k+3u]<<8);
                k+=4u;
                if(index+skip+len>IK_BOOT_PIXELS ||
                   r.size-k<(size_t)len*2u)goto done;
                index+=skip;
                for(unsigned i=0;i<len;++i) {
                    frame[index++]=(uint16_t)((unsigned)buffer[k]|
                                              ((unsigned)buffer[k+1u]<<8));
                    k+=2u;
                }
            }
            if(played>=h.video_frames)goto done;
            ikboot_until(start+(double)played/60.0988,cancel);
            if(cancel&&cancel())goto done;
            video(frame,r.frame);
            ++played;
        }else {
            if(r.size%4u||pcm+r.size/4u>h.audio_frames)goto done;
            audio((const int16_t*)(const void*)buffer,r.size/4u);
            pcm+=r.size/4u;
        }
    }
    valid=(played==h.video_frames && pcm==h.audio_frames &&
           check==h.checksum);
    if(log)log("IKSPC BOOT AV: REPLAY result=%s frames=%u PCM=%u measured_fps=%.2f\n",
               valid?"SUCCESS":"INVALID",played,pcm,
               played/(ikboot_secs()-start+0.001));
done:
    if(f)fclose(f);
    free(buffer);free(frame);
    return valid;
}
