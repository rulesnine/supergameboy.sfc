/* Original Ik Core SGB audio bridge.
 * Single-thread producer (mGBA video/packet callbacks), single-thread consumer
 * AFTER GB frame; do not concurrently call without explicit external mutex.
 * A stalled SOU_TRN blocks subsequent SOUND and never uploads partial data.
 * Only one 16-event fixed queue; no allocation in scanline hot path.
 */
#include "ikcore_sgb_audio_bridge.h"
#include <string.h>

typedef struct {
    unsigned command;
    unsigned length;
    uint8_t packet[112];
    uint8_t sou[IKCORE_SGB_SOU_BYTES];
    uint8_t covered[IKCORE_SGB_SOU_BYTES/16]; /* one bit per 2-byte pair */
    unsigned pairs;
    bool started;
    bool ready;
} Event;
static Event events[IKCORE_SGB_AUDIO_EVENTS];
static unsigned read_index, write_index, queued, dropped, completed;

void ikcore_sgb_audio_reset(void) {
    read_index=write_index=queued=dropped=completed=0;
    memset(events,0,sizeof(events));
}
unsigned ikcore_sgb_audio_queued(void) {return queued;}
unsigned ikcore_sgb_audio_dropped(void) {return dropped;}
unsigned ikcore_sgb_audio_completed_transfers(void) {return completed;}

void ikcore_sgb_sound_packet_hook(unsigned cmd,const unsigned char *data,
                                 unsigned length) {
    if (cmd!=IKCORE_SGB_COMMAND_SOUND && cmd!=IKCORE_SGB_COMMAND_SOU_TRN)
        return;
    if (!data || length<16 || length>112 || (length & 15u) ||
        (unsigned)(data[0]>>3)!=cmd || (unsigned)(data[0]&7u)!=length/16u) {
        ++dropped;
        return;
    }
    if (queued==IKCORE_SGB_AUDIO_EVENTS) {
        ++dropped; return;
    }
    Event *e=&events[write_index];
    memset(e,0,sizeof(*e));
    e->command=cmd;
    e->length=length;
    memcpy(e->packet,data,length);
    e->ready=(cmd==IKCORE_SGB_COMMAND_SOUND);
    write_index=(write_index+1u)%IKCORE_SGB_AUDIO_EVENTS;
    ++queued;
}

/* The SGB LCD transfer uses 20 GB tiles (160 pixels), 2BPP planar.
 * Same offset as mGBA software.c FinishScanline: 2*((y&7)+(y>>3)*160)
 * and 2 bytes for each 8-pixel group at offset + (x<<1).
 * Collect 2048 pairs across lines 0..103 to form exactly 4096 bytes.
 */
void ikcore_sgb_lcd_row_hook(unsigned y,const uint16_t *row,unsigned width) {
    if (!row || width != IKCORE_SGB_LCD_WIDTH || y>=144 || !queued)
        return;
    Event *e=NULL;
    for (unsigned i=0;i<queued;++i) {
        Event *candidate=&events[(read_index+i)%IKCORE_SGB_AUDIO_EVENTS];
        if (candidate->command==IKCORE_SGB_COMMAND_SOU_TRN &&
            !candidate->ready) {e=candidate;break;}
    }
    if (!e) return;
    if (!e->started) {
        if (y!=0) return; /* never accept partial/late-start transfer */
        e->started=true;
    }
    const unsigned base=2u*((y&7u)+(y>>3u)*IKCORE_SGB_LCD_WIDTH);
    for (unsigned x=0;x<IKCORE_SGB_LCD_WIDTH;x+=8) {
        const unsigned offset=base+(x<<1u);
        if (offset+1>=IKCORE_SGB_SOU_BYTES) break;
        unsigned lo=0,hi=0;
        for (unsigned p=0;p<8;++p) {
            const unsigned value=row[x+p]&3u;
            lo|=(value&1u)<<(7u-p);
            hi|=((value>>1)&1u)<<(7u-p);
        }
        const unsigned pair=offset>>1u;
        const unsigned mask=1u<<(pair&7u);
        if (!(e->covered[pair>>3u]&mask)) {
            e->covered[pair>>3u]|=(uint8_t)mask;
            e->sou[offset]=(uint8_t)lo;
            e->sou[offset+1]=(uint8_t)hi;
            ++e->pairs;
            if (e->pairs==IKCORE_SGB_SOU_BYTES/2u) {
                e->ready=true;
                ++completed;
                return;
            }
        }
    }
}

bool ikcore_sgb_audio_dispatch_one(const ikcore_sgb_audio_sink *sink) {
    if (!sink || !queued) return false;
    Event *e=&events[read_index];
    if (!e->ready) return false;
    if (e->command==IKCORE_SGB_COMMAND_SOUND) {
        if (!sink->sound) return false;
        sink->sound(e->packet,e->length,sink->opaque);
    } else if (e->command==IKCORE_SGB_COMMAND_SOU_TRN) {
        if (!sink->sou_transfer) return false;
        sink->sou_transfer(e->sou,sink->opaque);
    } else return false;
    /* Only release data AFTER callback finishes (APU event must copy). */
    memset(e,0,sizeof(*e));
    read_index=(read_index+1u)%IKCORE_SGB_AUDIO_EVENTS;
    --queued;
    return true;
}
