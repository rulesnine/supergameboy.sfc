#include "ik_sgbpack_rom.h"
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
static void put32(uint8_t *p,uint32_t x){p[0]=x;p[1]=x>>8;p[2]=x>>16;p[3]=x>>24;}
static uint32_t checksum(const uint8_t *p,size_t n){
    uint32_t c=~0u;size_t i;unsigned j;
    for(i=0;i<n;i++){c^=p[i];for(j=0;j<8;j++)c=(c>>1)^((c&1u)?0xEDB88320u:0);}
    return ~c;
}
int main(void){
    uint8_t sgb[0x10000],gb[0x8000],boot[256],footer[256]={0},*out=NULL;
    FILE *fp;
    size_t out_size=0;
    char why[200]={0};
    const char *name="/tmp/ikcore-f6-synthetic-pack.sfc";
    memset(sgb,0x6D,sizeof sgb);memset(gb,0x32,sizeof gb);memset(boot,0xE7,sizeof boot);
    gb[0x104]=0xCE;gb[0x105]=0xED;
    memcpy(footer,"SGBPACK1",8);put32(footer+8,1);
    put32(footer+0x10,0);put32(footer+0x14,sizeof sgb);
    put32(footer+0x18,sizeof sgb);put32(footer+0x1c,sizeof gb);
    put32(footer+0x20,sizeof sgb+sizeof gb);put32(footer+0x24,sizeof boot);
    put32(footer+0x28,checksum(sgb,sizeof sgb));
    put32(footer+0x2c,checksum(gb,sizeof gb));
    put32(footer+0x30,checksum(boot,sizeof boot));
    uint8_t whole[sizeof sgb+sizeof gb+sizeof boot];
    memcpy(whole,sgb,sizeof sgb);memcpy(whole+sizeof sgb,gb,sizeof gb);
    memcpy(whole+sizeof sgb+sizeof gb,boot,sizeof boot);
    put32(footer+0xa8,checksum(whole,sizeof whole));
    fp=fopen(name,"wb"); assert(fp);
    assert(fwrite(whole,1,sizeof whole,fp)==sizeof whole);
    assert(fwrite(footer,1,sizeof footer,fp)==sizeof footer);
    fclose(fp);
    assert(ik_f6_sgbpack_extract_gb(name,&out,&out_size,why,sizeof why));
    assert(out_size==sizeof gb && !memcmp(out,gb,sizeof gb));
    free(out);out=NULL;out_size=0;
    fp=fopen(name,"rb+");assert(fp);fseek(fp,5,SEEK_SET);fputc(0,fp);fclose(fp);
    why[0]=0;
    assert(!ik_f6_sgbpack_extract_gb(name,&out,&out_size,why,sizeof why));
    assert(strstr(why,"CRC mismatch") && out==NULL && out_size==0);
    remove(name);
    puts("PASS: one-file SGBPACK1 embedded GB loader; layout/CRC guardrails and corrupt rejection");
    return 0;
}
