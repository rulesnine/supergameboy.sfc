/* Ik Core Phase5: real original GB-side SGB boot is executed by mGBA SM83
 * from PC=0000, before any Game Boy cartridge CPU instruction.
 * The boot fixture is extracted locally from pinned Expat-licensed SameBoy
 * source on GitHub CI and is NOT bundled in any artifact.
 */
#include "../native_mgba/ikcore_mgba_gb_host.h"
#include "../native_mgba/ikcore_sgb_packet_bus.h"
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>

static unsigned char *load(const char *name,size_t *size) {
    FILE *f=fopen(name,"rb");
    if(!f)return NULL;
    if(fseek(f,0,SEEK_END)){fclose(f);return NULL;}
    long n=ftell(f);
    if(n<0||n>8*1024*1024){fclose(f);return NULL;}
    rewind(f);
    unsigned char *data=malloc((size_t)n);
    if(!data){fclose(f);return NULL;}
    if(fread(data,1,(size_t)n,f)!=(size_t)n){fclose(f);free(data);return NULL;}
    fclose(f);*size=(size_t)n;return data;
}
int main(int argc,char **argv) {
    if(argc!=3)return 1;
    size_t size=0,boot_size=0;
    unsigned char *rom=load(argv[1],&size);
    unsigned char *boot=load(argv[2],&boot_size);
    if(!rom||!boot||boot_size!=256)return 2;
    if(ikcore_mgba_open_sgb_boot(rom,size,boot,255)) {
        fputs("Invalid SGB boot length incorrectly accepted\n",stderr);
        return 3;
    }
    ikcore_sgb_bus_reset();
    ikcore_mgba_host *h=ikcore_mgba_open_sgb_boot(rom,size,boot,boot_size);
    free(rom);free(boot);
    if(!h){fputs("mGBA refused licensed SGB boot\n",stderr);return 4;}
    if(!ikcore_mgba_boot_mapped(h)||ikcore_mgba_program_counter(h)!=0) {
        fprintf(stderr,"BOOT INVALID mapped=%d PC=%04x\n",
            ikcore_mgba_boot_mapped(h),ikcore_mgba_program_counter(h));
        return 5;
    }
    unsigned start=ikcore_mgba_program_counter(h),ticks=0;
    for(unsigned i=0;i<30;i++) {
        ikcore_mgba_frame frame;
        if(!ikcore_mgba_run(h,0,&frame))return 6;
        if(frame.frame_number!=i+1 || frame.width<160 ||
           frame.height<144||!frame.video||!frame.audio_rate)return 7;
        ++ticks;
    }
    unsigned pc=ikcore_mgba_program_counter(h);
    unsigned commands=ikcore_sgb_bus_count();
    ikcore_mgba_close(h);
    printf("IKCORE_MGBA_SGB_BOOT_OK frames=%u startPC=%04x currentPC=%04x sgbPacketEvents=%u\n",
        ticks,start,pc,commands);
    if(start!=0 || ticks!=30 || pc==0)return 8;
    return 0;
}
