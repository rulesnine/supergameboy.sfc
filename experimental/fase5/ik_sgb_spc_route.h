#ifndef IK_SGB_SPC_ROUTE_H
#define IK_SGB_SPC_ROUTE_H
#include "ik_sgb_bridge.h"
#include <stdint.h>
/* Callbacks run on the GB emulation thread; the SPC backend must copy data
 * into its OWN synchronous or bounded audio-thread queue. */
typedef int (*IkSgbSpcSoundSink)(const uint8_t packet[16], uint64_t cycle, void *ctx);
typedef int (*IkSgbSpcTransferSink)(const uint8_t bytes[4096], uint64_t cycle, void *ctx);
typedef struct {
    IkSgbSpcSoundSink on_sound;
    IkSgbSpcTransferSink on_transfer;
    void *ctx;
    uint64_t sound_packets, sound_delivered, sound_no_backend;
    uint64_t transfer_requested, transfer_delivered, transfer_no_backend;
    uint64_t other_packets, invalid_packets;
    int transfer_pending;
} IkSgbSpcRoute;
void ik_sgb_spc_route_init(IkSgbSpcRoute *r,
                            IkSgbSpcSoundSink sound,
                            IkSgbSpcTransferSink transfer, void *ctx);
void ik_sgb_spc_route_packet(IkSgbSpcRoute *r, const IkSgbPacket *pkt);
int ik_sgb_spc_route_transfer(IkSgbSpcRoute *r, const IkSgbTransfer *snapshot);
#endif
