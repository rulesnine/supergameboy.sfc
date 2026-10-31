/* SGB production visual telemetry regression test, no commercial ROM needed. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
extern void ikcore_fase5_sgb_reset_packets(void);
extern void ikcore_mgba_sgb_packet(const uint8_t*, uint64_t,uint64_t);
extern void ikcore_sgb_prod_visual_stats(uint64_t*,uint64_t*,uint64_t*,uint64_t*,uint64_t*);
static void emit(unsigned cmd) {uint8_t p[16]={0};p[0]=(uint8_t)((cmd<<3)|1);ikcore_mgba_sgb_packet(p,0,0);}
static int check(uint64_t ep,uint64_t ea,uint64_t ec,uint64_t eb,uint64_t em) {
    uint64_t p=0,a=0,c=0,b=0,m=0;
    ikcore_sgb_prod_visual_stats(&p,&a,&c,&b,&m);
    if(p!=ep||a!=ea||c!=ec||b!=eb||m!=em) {
        fprintf(stderr,"SGB stats wrong: pal=%llu attr=%llu chr=%llu pct=%llu mask=%llu\n",(unsigned long long)p,(unsigned long long)a,(unsigned long long)c,(unsigned long long)b,(unsigned long long)m);
        return 1;
    } return 0;
}
int main(void) {
    ikcore_fase5_sgb_reset_packets();
    if(check(0,0,0,0,0))return 1; /* Plain GB: generic border retained */
    emit(0x08);emit(0x13);emit(0x00);emit(0x01);emit(0x0A);
    if(check(3,0,1,0,0))return 2; /* CHR and PAL alone cannot replace border */
    emit(0x14);emit(0x04);emit(0x17);
    if(check(3,1,1,1,1))return 3; /* Authored PCT selects game's own art */
    ikcore_fase5_sgb_reset_packets();
    if(check(0,0,0,0,0))return 4;
    puts("PASS: untouched palette packets, original SGB border detection and generic fallback bookkeeping");
    return 0;
}
