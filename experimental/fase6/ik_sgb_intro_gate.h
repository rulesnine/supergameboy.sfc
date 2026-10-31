#ifndef IK_SGB_INTRO_GATE_H
#define IK_SGB_INTRO_GATE_H
/* The SGB firmware and cart live inside the SAME Snes9x core during cold
 * bootstrap. A second, independent mGBA cart begins at power-on, so NEVER
 * replay Snes9x cart-owned video/audio after the GB boot-ROM handoff.
 * The boundary is a core event, not a guessed time or logo pixel pattern. */
typedef struct {
    unsigned cart_started;
    unsigned intro_video_frames;
    unsigned intro_audio_callbacks;
    unsigned cut_boot_frame;
} IkSgbIntroGate;
static inline int ik_sgb_intro_allow(IkSgbIntroGate *g,int gb_boot_handoff,
                                      unsigned firmware_frame) {
    if(gb_boot_handoff && !g->cart_started) {
        g->cart_started=1u;
        g->cut_boot_frame=firmware_frame;
    }
    return !g->cart_started;
}
static inline void ik_sgb_intro_note_video(IkSgbIntroGate *g) {
    ++g->intro_video_frames;
}
static inline void ik_sgb_intro_note_audio(IkSgbIntroGate *g) {
    ++g->intro_audio_callbacks;
}
#endif
