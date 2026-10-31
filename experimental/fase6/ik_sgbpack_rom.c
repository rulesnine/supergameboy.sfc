#include "ik_sgbpack_rom.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdarg.h>

static uint32_t le32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1]<<8) |
           ((uint32_t)p[2]<<16) | ((uint32_t)p[3]<<24);
}
static uint32_t crc32_checked(const uint8_t *data,size_t len) {
    uint32_t crc=0xFFFFFFFFu;
    size_t i;
    unsigned b;
    for(i=0;i<len;i++) {
        crc ^= data[i];
        for(b=0;b<8;b++) {
            uint32_t mask=-(crc&1u);
            crc=(crc>>1) ^ (0xEDB88320u & mask);
        }
    }
    return ~crc;
}
static int fail(char *why,size_t cap,const char *msg) {
    if(why && cap) snprintf(why,cap,"%s",msg);
    return 0;
}
int ik_f6_sgbpack_extract_gb(const char *path,uint8_t **rom,size_t *sz,
                            char *why,size_t cap) {
    FILE *fp=NULL;
    uint8_t *all=NULL,*gb=NULL;
    uint8_t *f;
    uint32_t offsets[3],lengths[3],crcs[3],whole;
    size_t size,payload;
    int result=0;
    unsigned k;
    long file_length;
    if(rom) *rom=NULL;
    if(sz) *sz=0;
    if(!path || !rom || !sz) return fail(why,cap,"invalid argument");
    fp=fopen(path,"rb");
    if(!fp) return fail(why,cap,"SGBPACK1 file inaccessible");
    if(fseek(fp,0,SEEK_END)!=0) goto close;
    file_length=ftell(fp);
    if(file_length<512 || file_length>32*1024*1024L) goto close;
    size=(size_t)file_length;
    if(fseek(fp,0,SEEK_SET)!=0) goto close;
    all=(uint8_t*)malloc(size);
    if(!all)goto close;
    if(fread(all,1,size,fp)!=size)goto close;
    payload=size-256u;f=all+payload;
    if(memcmp(f,"SGBPACK1",8)!=0) {
        fail(why,cap,"SGBPACK1 footer magic missing");
        goto close;
    }
    if(le32(f+8)!=1) {
        fail(why,cap,"SGBPACK1 unsupported version");
        goto close;
    }
    offsets[0]=le32(f+0x10);lengths[0]=le32(f+0x14);crcs[0]=le32(f+0x28);
    offsets[1]=le32(f+0x18);lengths[1]=le32(f+0x1c);crcs[1]=le32(f+0x2c);
    offsets[2]=le32(f+0x20);lengths[2]=le32(f+0x24);crcs[2]=le32(f+0x30);
    if(offsets[0]!=0 || lengths[0]<0x10000u ||
       offsets[1]!=(uint64_t)offsets[0]+lengths[0] ||
       offsets[2]!=(uint64_t)offsets[1]+lengths[1] ||
       (uint64_t)offsets[2]+lengths[2]!=payload ||
       lengths[2]!=256u ||
       lengths[1]<0x150u || lengths[1]>8u*1024u*1024u ||
       lengths[1]%0x4000u!=0) {
        fail(why,cap,"SGBPACK1 invalid segment layout");
        goto close;
    }
    whole=crc32_checked(all,payload);
    if(whole!=le32(f+0xa8)) {
        fail(why,cap,"SGBPACK1 payload CRC mismatch");
        goto close;
    }
    for(k=0;k<3;k++) {
        if(crc32_checked(all+offsets[k],lengths[k])!=crcs[k]) {
            fail(why,cap,"SGBPACK1 segment CRC mismatch");
            goto close;
        }
    }
    /* The GB core checks ROM title/header too; make sure this is at least
       a legitimate Game Boy cartridge header before starting the emulator. */
    if(all[offsets[1]+0x104]!=0xCE ||
       all[offsets[1]+0x105]!=0xED) {
        fail(why,cap,"SGBPACK1 GB cartridge header not recognized");
        goto close;
    }
    gb=(uint8_t*)malloc(lengths[1]);
    if(!gb) {fail(why,cap,"GB ROM allocation failed");goto close;}
    memcpy(gb,all+offsets[1],lengths[1]);
    *rom=gb;*sz=lengths[1];result=1;
    if(why && cap) snprintf(why,cap,"SGBPACK1 GB embedded ROM validated (size=%u)",lengths[1]);
close:
    if(!result && why && cap && !why[0])
        snprintf(why,cap,"SGBPACK1 read failed or not a v1 container");
    free(all);
    fclose(fp);
    return result;
}
