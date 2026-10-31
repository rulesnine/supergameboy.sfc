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

void ikcore_fase5_sgb_reset_packets(void) {
    ik_sgb_queue_init(&queue);
    initialized = 1;
    received = sound = transfers = last_cycles = dropped = 0;
    sound_triggers = sound_transfers = 0;
}

void ikcore_mgba_sgb_packet(const uint8_t *data, uint64_t cycles,
                            uint64_t frame) {
    IkSgbPacket pkt;
    uint8_t cmd;
    if (!data) return;
    if (!initialized) ikcore_fase5_sgb_reset_packets();
    cmd = data[0] >> 3;
    ++received;
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
