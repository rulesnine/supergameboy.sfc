/* Ik Core: exact 4 KiB SGB SOU_TRN transfer from Game Boy LCD tile stream.
 * Original interface; uses no proprietary firmware or sound samples.
 * Single GB emulation thread: command -> frame -> rendered line callbacks.
 */
#ifndef IKCORE_SOU_TRN_CAPTURE_H
#define IKCORE_SOU_TRN_CAPTURE_H
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif
#include <stdint.h>
enum { IKCORE_SOU_BYTES=4096, IKCORE_SOU_PIXELS=160, IKCORE_SOU_SKIP_FRAMES=6 };
typedef struct {
    uint8_t payload[IKCORE_SOU_BYTES];
    uint8_t seen[IKCORE_SOU_BYTES];
    unsigned complete_bytes;
    unsigned frames_to_skip;
    unsigned completed;
    unsigned incomplete;
    unsigned interrupted;
    bool pending;
    bool recording;
} ikcore_sou_capture;
typedef void (*ikcore_sou_complete_cb)(const uint8_t *payload, unsigned size, void *ctx);
void ikcore_sou_capture_reset(ikcore_sou_capture *c);
unsigned ikcore_sgb_transfer_capture_active(void);
void ikcore_sou_capture_arm(ikcore_sou_capture *c);
void ikcore_sou_capture_scanline(ikcore_sou_capture *c,int y,const uint16_t *pixels,unsigned width);
bool ikcore_sou_capture_end_frame(ikcore_sou_capture *c,ikcore_sou_complete_cb cb,void *ctx);
/* Hooks called by our optional patches into pinned mGBA. */
void ikcore_sgb_transfer_command_hook(unsigned cmd);
void ikcore_sgb_transfer_scanline_hook(int y,const uint16_t *pixels,unsigned width);
void ikcore_sgb_transfer_frame_hook(void);
void ikcore_sgb_transfer_reset_hook(void);
/* Strong host implementation (in Ik Core) can use this weak callback. */
void ikcore_sgb_transfer_completed_hook(const uint8_t *payload,unsigned size);
#ifdef __cplusplus
}
#endif
#endif
