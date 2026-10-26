/* Ik Core 2-stage SNES-audio bridge: mGBA GB command/capture producer ->
 * bounded FIFO -> Ik Core's verified N-SPC SOUND/SOU_TRN worker.
 * No SPC RAM writes here. Only callbacks on host playback thread may touch it.
 */
#include "ikcore_sgb_audio_fifo.h"
#include <string.h>
typedef struct {
    ikcore_sgb_audio_kind kind;
    unsigned length;
    uint8_t bytes[IKCORE_SGB_AUDIO_TRANSFER_BYTES];
} ikcore_sgb_audio_event;
static ikcore_sgb_audio_event events[IKCORE_SGB_AUDIO_CAPACITY];
static unsigned rd,wr,n,dropped;
void ikcore_sgb_audio_reset(void) {
    rd=0;wr=0;n=0;dropped=0;
}
unsigned ikcore_sgb_audio_count(void) {return n;}
unsigned ikcore_sgb_audio_dropped(void) {return dropped;}
static bool submit(ikcore_sgb_audio_kind kind,const uint8_t *data,unsigned len) {
    if(!data || (kind==IKCORE_SGB_AUDIO_SOUND && (len<5 || len>IKCORE_SGB_AUDIO_SOUND_BYTES
        || (data[0]>>3)!=8u)) ||
       (kind==IKCORE_SGB_AUDIO_TRANSFER && len!=IKCORE_SGB_AUDIO_TRANSFER_BYTES)) {
        ++dropped;return false;
    }
    if(n==IKCORE_SGB_AUDIO_CAPACITY) {++dropped;return false;}
    ikcore_sgb_audio_event *e=&events[wr];
    e->kind=kind;
    e->length=len;
    memcpy(e->bytes,data,len);
    ++n;wr=(wr+1u)%IKCORE_SGB_AUDIO_CAPACITY;
    return true;
}
bool ikcore_sgb_audio_queue_sound(const uint8_t* data,unsigned len) {
    return submit(IKCORE_SGB_AUDIO_SOUND,data,len);
}
bool ikcore_sgb_audio_queue_transfer(const uint8_t* data,unsigned len) {
    return submit(IKCORE_SGB_AUDIO_TRANSFER,data,len);
}
unsigned ikcore_sgb_audio_drain(ikcore_spc_packet_callback sound,
                               ikcore_spc_packet_callback transfer,void* user) {
    /* Never silently drop events merely because SPC isn't initialized. */
    if(!sound || !transfer)return 0;
    unsigned processed=0;
    while(n) {
        ikcore_sgb_audio_event *e=&events[rd];
        if(e->kind==IKCORE_SGB_AUDIO_SOUND) sound(e->bytes,e->length,user);
        else transfer(e->bytes,e->length,user);
        rd=(rd+1u)%IKCORE_SGB_AUDIO_CAPACITY;
        --n;++processed;
    }
    return processed;
}
void ikcore_sgb_audio_sound_packet_hook(const uint8_t* data,unsigned len) {
    (void)ikcore_sgb_audio_queue_sound(data,len);
}
void ikcore_sgb_transfer_completed_hook(const uint8_t* payload,unsigned size) {
    (void)ikcore_sgb_audio_queue_transfer(payload,size);
}
