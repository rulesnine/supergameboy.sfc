/* Ik Core SGB command bus. Original code, not a reimplementation of SGB DSP.
 *
 * Single producer GB runtime and single consumer after each completed GB frame.
 * SGB packets always remain in original byte order; SOUND/SOU_TRN events must
 * later be translated to the existing Ik Core SPC700/DSP thread by the host.
 * SOU_TRN's 4096-byte LCD transfer has NOT yet been captured by this file.
 */
#include "ikcore_sgb_packet_bus.h"
#include <string.h>
#if defined(__GNUC__)
/* Optional SOUND observer: sends to SPC FIFO as soon as mGBA assembles
 * a complete packet. The full packet bus remains for graphical commands. */
extern void ikcore_sgb_audio_sound_packet_hook(const uint8_t *,unsigned)
    __attribute__((weak));
/* Return: 0 = no active authentic SNES BIOS route,
 * 1 = accepted into real ICD2, -1 = rejected (do NOT synthesize sound). */
extern int ikcore_mgba_phase6_route_icd2_packet(const uint8_t *,unsigned)
    __attribute__((weak));
#endif
static ikcore_sgb_packet queue[IKCORE_SGB_PACKET_DEPTH];
static unsigned read_pos, write_pos, queued, dropped;
static uint64_t serial;

void ikcore_sgb_bus_reset(void) {
    read_pos=0;write_pos=0;queued=0;dropped=0;serial=0;
}
unsigned ikcore_sgb_bus_count(void) {return queued;}
unsigned ikcore_sgb_bus_dropped(void) {return dropped;}

void ikcore_sgb_packet_hook(unsigned command,
                            const unsigned char *data,unsigned bytes) {
    if(!data||command>31||bytes<16||bytes>IKCORE_SGB_PACKET_BYTES||
       (bytes%16)!=0 || ((data[0]>>3)&31u)!=(command&31u) ||
       (data[0]&7u)!=(bytes/16u)) {
        ++dropped;
        return;
    }
    int icd2_routed=0;
#if defined(__GNUC__)
    if(ikcore_mgba_phase6_route_icd2_packet)
        icd2_routed=ikcore_mgba_phase6_route_icd2_packet(data,bytes);
    if(icd2_routed<0) ++dropped;
#endif
#if defined(__GNUC__)
    // BIOS-owned command traffic must NEVER also be played directly by
    // the SPC FIFO: the SNES firmware is already processing the packet.
    if(!icd2_routed &&
       command==IKCORE_SGB_SOUND_CMD && ikcore_sgb_audio_sound_packet_hook)
        ikcore_sgb_audio_sound_packet_hook(data,bytes);
#endif
    if(queued>=IKCORE_SGB_PACKET_DEPTH) {++dropped;return;}
    ikcore_sgb_packet *pkt=&queue[write_pos];
    pkt->serial=++serial;
    pkt->command=(uint8_t)command;
    pkt->length=(uint8_t)bytes;
    memcpy(pkt->data,data,bytes);
    write_pos=(write_pos+1)%IKCORE_SGB_PACKET_DEPTH;
    ++queued;
}
bool ikcore_sgb_bus_pop(ikcore_sgb_packet *out) {
    if(!out||!queued)return false;
    *out=queue[read_pos];
    read_pos=(read_pos+1)%IKCORE_SGB_PACKET_DEPTH;
    --queued;
    return true;
}
