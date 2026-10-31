/* SPDX-License-Identifier: MIT
 * Real SGB packet relay from mGBA's verified JOYP parser. This queues the
 * original 16-byte packets; no second GB CPU and no fake SNES sound playback.
 * All APIs are emulation-thread-only. No background thread or allocation.
 */
#include "ik_sgb_mgba_relay.h"
#include <stdint.h>
#include <string.h>

static IkSgbQueue queue;
static int initialized;
static uint64_t received, sound, transfers, last_cycles, dropped;
static uint64_t sound_triggers, sound_transfers;
/* Passive only: count the exact ROM-origin SGB color and border commands.
 * Never alter their bytes, renderer data, palettes or palette timing. */
static uint64_t prod_pal, prod_attrs, prod_chr, prod_pct, prod_mask;
/* mGBA software renderer's SGB LCD transfer: 20 GB tiles per row,
 * 2bpp packed into the same 4096-byte layout expected by #117 SOU_TRN.
 * One emulation thread; no heap and no alternative GB renderer. */
static uint8_t sou_work[IK_SGB_TRANSFER_SIZE], sou_snapshot[IK_SGB_TRANSFER_SIZE];
static unsigned sou_scanlines, sou_ready, sou_dropped;
static uint64_t sou_frame;
void ikcore_mgba_sou_trn_scanline(unsigned y,const uint8_t *row) {
    size_t offset;
    unsigned x,j;
    if (!row || y>=144) return;
    if (y==0) { memset(sou_work,0,sizeof sou_work); sou_scanlines=0; }
    offset=2u*((y & 7u)+(y >> 3u)*160u);
    for(x=0;x<160;x+=8) {
        uint8_t lo=0,hi=0;
        if(offset+(x<<1)+1u>=IK_SGB_TRANSFER_SIZE) break;
        for(j=0;j<8;j++) {
            lo |= (uint8_t)((row[x+j]&1u) << (7u-j));
            hi |= (uint8_t)(((row[x+j]>>1)&1u) << (7u-j));
        }
        sou_work[offset+(x<<1)]=lo;
        sou_work[offset+(x<<1)+1]=hi;
    }
    ++sou_scanlines;
}
void ikcore_mgba_sou_trn_complete(uint64_t frame) {
    if(sou_scanlines < 100u) return;
    if(sou_ready) { ++sou_dropped; return; }
    memcpy(sou_snapshot,sou_work,sizeof sou_snapshot);
    sou_frame=frame;
    sou_ready=1u;
    sou_scanlines=0u;
}
int ikcore_fase6_sou_trn_pop(uint8_t *out,size_t max_size,uint64_t *frame) {
    if (!sou_ready || !out || max_size<IK_SGB_TRANSFER_SIZE) return 0;
    memcpy(out,sou_snapshot,IK_SGB_TRANSFER_SIZE);
    if(frame) *frame=sou_frame;
    sou_ready=0;
    return 1;
}
unsigned ikcore_fase6_sou_trn_dropped(void) { return sou_dropped; }



void ikcore_fase5_sgb_reset_packets(void) {
    ik_sgb_queue_init(&queue);
    initialized = 1;
    received = sound = transfers = last_cycles = dropped = 0;
    sound_triggers = sound_transfers = 0;
    prod_pal=prod_attrs=prod_chr=prod_pct=prod_mask=0;
    sou_scanlines=sou_ready=sou_dropped=0; sou_frame=0;
}

void ikcore_mgba_sgb_packet(const uint8_t *data, uint64_t cycles,
                            uint64_t frame) {
    IkSgbPacket pkt;
    uint8_t cmd;
    if (!data) return;
    if (!initialized) ikcore_fase5_sgb_reset_packets();
    cmd = data[0] >> 3;
    ++received;
    switch (cmd) {
    case 0x00: case 0x01: case 0x02: case 0x03:
    case 0x0A: case 0x0B: ++prod_pal; break;
    case 0x04: case 0x05: case 0x06: case 0x07:
    case 0x0C: case 0x15: case 0x16: ++prod_attrs; break;
    case 0x13: ++prod_chr; break;
    case 0x14: ++prod_pct; break;
    case 0x17: ++prod_mask; break;
    default: break;
    }
    /* Preserve original counters displayed in prior NES Mini baselines. */
    if (cmd == 0x08 || cmd == 0x09) ++sound;
    if (cmd == 0x09 || cmd == 0x0B || cmd == 0x13 ||
        cmd == 0x14 || cmd == 0x15 || cmd == 0x18) ++transfers;
    if (cmd == 0x08) ++sound_triggers;
    if (cmd == 0x09) ++sound_transfers;
    last_cycles = cycles;

    pkt.gb_cycles = cycles;
    pkt.gb_frame = frame;
    memcpy(pkt.bytes, data, IK_SGB_PACKET_SIZE);
    if (!ik_sgb_queue_push(&queue, &pkt)) ++dropped;
}

int ikcore_fase5_sgb_pop_packet(IkSgbPacket *out) {
    if (!initialized || !out || queue.count == 0) return 0;
    *out = queue.entries[queue.head];
    queue.head = (queue.head + 1u) % IK_SGB_QUEUE_CAPACITY;
    --queue.count;
    ++queue.consumed;
    return 1;
}

void ikcore_fase5_sgb_relay_stats(uint64_t *queued, uint64_t *lost,
                                  uint64_t *sfx, uint64_t *sample_transfers) {
    if (queued) *queued = queue.count;
    if (lost) *lost = dropped;
    if (sfx) *sfx = sound_triggers;
    if (sample_transfers) *sample_transfers = sound_transfers;
}

void ikcore_fase5_stats(uint64_t *packets, uint64_t *sounds,
                        uint64_t *trns, uint64_t *cycles) {
    if (packets) *packets = received;
    if (sounds) *sounds = sound;
    if (trns) *trns = transfers;
    if (cycles) *cycles = last_cycles;
}

/* This is telemetry, not a palette replacement. A game-authored border
 * becomes authoritative upon PCT_TRN; absence of PCT retains the default
 * SGB frame that mGBA initialized in GBVideoReset. */
void ikcore_sgb_prod_visual_stats(uint64_t *pal, uint64_t *attrs,
                                  uint64_t *chr, uint64_t *pct,
                                  uint64_t *mask) {
    if (pal) *pal=prod_pal;
    if (attrs) *attrs=prod_attrs;
    if (chr) *chr=prod_chr;
    if (pct) *pct=prod_pct;
    if (mask) *mask=prod_mask;
}
