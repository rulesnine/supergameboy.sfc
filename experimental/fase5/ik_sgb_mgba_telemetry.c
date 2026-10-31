/* SPDX-License-Identifier: MIT
 * Real packet counts from mGBA 0.10.5's JOYP parser; no firmware or ROM data.
 * This is telemetry only, NOT an ICD2 or SPC700 bridge.
 */
#include <stdint.h>
static uint64_t received, sound, transfers, last_cycles;
void ikcore_mgba_sgb_packet(const uint8_t *data, uint64_t cycles, uint64_t frame) {
    uint8_t cmd;
    (void)frame;
    if (!data) return;
    ++received;
    cmd = data[0] >> 3;
    if (cmd == 0x08 || cmd == 0x09) ++sound;
    if (cmd == 0x09 || cmd == 0x0B || cmd == 0x13 || cmd == 0x14 || cmd == 0x15 || cmd == 0x18) ++transfers;
    last_cycles = cycles;
}
void ikcore_fase5_stats(uint64_t *packets, uint64_t *sounds,
                        uint64_t *trns, uint64_t *cycles) {
    if (packets) *packets = received;
    if (sounds) *sounds = sound;
    if (trns) *trns = transfers;
    if (cycles) *cycles = last_cycles;
}
