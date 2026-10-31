#include "ik_sgb_spc_route.h"
#include <string.h>
void ik_sgb_spc_route_init(IkSgbSpcRoute *r, IkSgbSpcSoundSink sound,
                            IkSgbSpcTransferSink transfer, void *ctx) {
    if (!r) return;
    memset(r, 0, sizeof(*r));
    r->on_sound = sound;
    r->on_transfer = transfer;
    r->ctx = ctx;
}
void ik_sgb_spc_route_packet(IkSgbSpcRoute *r, const IkSgbPacket *pkt) {
    unsigned cmd;
    if (!r || !pkt) return;
    if ((pkt->bytes[0] & 7u) == 0) { ++r->invalid_packets; return; }
    cmd = pkt->bytes[0] >> 3;
    if (cmd == 0x08) {
        ++r->sound_packets;
        /* Preserve bytes 0..15 exactly: #117's N-SPC function expects
           data[1], [2], [3], [4], including the music/score code. */
        if (r->on_sound && r->on_sound(pkt->bytes, pkt->gb_cycles, r->ctx))
            ++r->sound_delivered;
        else
            ++r->sound_no_backend;
    } else if (cmd == 0x09) {
        /* SOU_TRN does NOT contain the actual 4096-byte LCD transfer. */
        ++r->transfer_requested;
        r->transfer_pending = 1;
    } else {
        ++r->other_packets;
    }
}
int ik_sgb_spc_route_transfer(IkSgbSpcRoute *r, const IkSgbTransfer *data) {
    if (!r || !r->transfer_pending || !data ||
        !data->valid || data->size != IK_SGB_TRANSFER_SIZE ||
        data->command != 0x09) return 0;
    r->transfer_pending = 0;
    if (r->on_transfer && r->on_transfer(data->data, data->gb_cycles, r->ctx)) {
        ++r->transfer_delivered;
        return 1;
    }
    ++r->transfer_no_backend;
    return 0;
}
