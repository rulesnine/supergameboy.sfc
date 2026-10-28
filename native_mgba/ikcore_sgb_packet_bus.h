/* Ik Core independent SGB packet staging bus — no emulation or audio shortcuts.
 * Only the GB run thread pushes; only the host render/audio thread pops after
 * completing a GB frame. Do not share across threads without a mutex.
 */
#ifndef IKCORE_SGB_PACKET_BUS_H
#define IKCORE_SGB_PACKET_BUS_H
#include <stdint.h>
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif
#define IKCORE_SGB_PACKET_BYTES 112
#define IKCORE_SGB_PACKET_DEPTH 128
#define IKCORE_SGB_SOUND_CMD 8
#define IKCORE_SGB_SOU_TRN_CMD 9
typedef struct {
    uint64_t serial;
    uint8_t command;
    uint8_t length;
    uint8_t data[IKCORE_SGB_PACKET_BYTES];
} ikcore_sgb_packet;
void ikcore_sgb_bus_reset(void);
unsigned ikcore_sgb_bus_count(void);
unsigned ikcore_sgb_bus_dropped(void);
bool ikcore_sgb_bus_pop(ikcore_sgb_packet *out);
void ikcore_sgb_packet_hook(unsigned command,const unsigned char *data,unsigned bytes);
#ifdef __cplusplus
}
#endif
#endif
