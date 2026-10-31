#ifndef IK_SGB_BOOT_PANE_H
#define IK_SGB_BOOT_PANE_H
#include <stdint.h>
#include <string.h>
/*
 * RC10: a genuine SGB console boots its GB CPU while the SNES presentation
 * continues. Our mGBA GB CPU then starts independently. To avoid displaying
 * the *first* GB boot sequence inside the Snes9x SGB intro (and again in
 * mGBA), preserve the last pre-release 160x144 GB pane while letting the
 * SNES firmware's outer 48/40-pixel border continue its ORIGINAL animation.
 *
 * This is presentation-only: don't block SNES CPU/APU, SPC boot, user cache,
 * GB gameplay, original CHR/PCT packets, or mGBA's own image. We deliberately
 * key off the real ICD2 $6003 GB-release bit, not a guessed frame count or
 * a recognizer for Nintendo artwork.
 */
#define IK_SGB_PANE_WIDTH 160u
#define IK_SGB_PANE_HEIGHT 144u
#define IK_SGB_FRAME_WIDTH 256u
#define IK_SGB_PANE_X 48u
#define IK_SGB_PANE_Y 39u /* Snes9x SGB ICD2 compositing uses Y=39 */
typedef struct {
    uint16_t saved[IK_SGB_PANE_WIDTH*IK_SGB_PANE_HEIGHT];
    unsigned pre_release_frames,held_frames,release_frame;
    unsigned has_saved,gb_released;
} IkSgbBootPane;
static inline void ik_sgb_pane_filter(IkSgbBootPane *s,uint16_t *pixels,
                                     int gb_released,unsigned snes_frame) {
    unsigned y;
    if(!s||!pixels)return;
    if(gb_released && !s->gb_released) {
        s->gb_released=1u;
        s->release_frame=snes_frame;
    }
    if(!s->gb_released) {
        for(y=0;y<IK_SGB_PANE_HEIGHT;++y)
            memcpy(s->saved+y*IK_SGB_PANE_WIDTH,
                   pixels+(y+IK_SGB_PANE_Y)*IK_SGB_FRAME_WIDTH+IK_SGB_PANE_X,
                   IK_SGB_PANE_WIDTH*sizeof(uint16_t));
        s->has_saved=1u;
        ++s->pre_release_frames;
    } else {
        for(y=0;y<IK_SGB_PANE_HEIGHT;++y) {
            uint16_t *dst=pixels+(y+IK_SGB_PANE_Y)*IK_SGB_FRAME_WIDTH+IK_SGB_PANE_X;
            if(s->has_saved)
                memcpy(dst,s->saved+y*IK_SGB_PANE_WIDTH,
                       IK_SGB_PANE_WIDTH*sizeof(uint16_t));
            else
                memset(dst,0,IK_SGB_PANE_WIDTH*sizeof(uint16_t));
        }
        ++s->held_frames;
    }
}
#endif
