/* Ik Core native SGB Hybrid — Phase 4 combined-library bridge.
 *
 * Compiled INSIDE the original Snes9x libretro object set, linking against
 * the pinned mGBA Game Boy-only ARMv7 static library and the existing
 * Snes9x SPC700/DSP audio worker. No second Game Boy CPU is started here.
 *
 * The ABI intentionally does NOT redirect Snes9x's currently validated
 * SGB frame loop. The CPU replacement requires state-correct bootstrap,
 * graphics, SRAM and rate-matched PCM; opt-in runtime entry points below
 * are for the next step and remain unused by the normal core.
 */
#include "ikcore_mgba_gb_host.h"
#include "ikcore_sgb_audio_fifo.h"
#include "../apu/apu.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>
extern "C" unsigned ikcore_sgb_spc_dispatch_frame(void);

/* The combined library owns the mGBA session. This is deliberately separate
 * from the existing Snes9x SGB singleton to avoid corrupting #43 state. */
static ikcore_mgba_host *ikcore_combined_gb = nullptr;
static ikcore_mgba_frame ikcore_combined_frame = {};

/* Historical bit mapping from the validated SuperSnes9x SetJoypad() path.
 * Bit masks match the NES Mini's existing Clovercon->SNES pad mapping. */
static uint8_t ikcore_map_snes_pad(uint16_t mask)
{
    uint8_t buttons=0;
    if (mask & (1u<<7))  buttons |= IKCORE_GB_A;
    if (mask & ((1u<<15)|(1u<<14))) buttons |= IKCORE_GB_B;
    if (mask & (1u<<12)) buttons |= IKCORE_GB_START;
    if (mask & (1u<<13)) buttons |= IKCORE_GB_SELECT;
    if (mask & (1u<<11)) buttons |= IKCORE_GB_UP;
    if (mask & (1u<<10)) buttons |= IKCORE_GB_DOWN;
    if (mask & (1u<<9))  buttons |= IKCORE_GB_LEFT;
    if (mask & (1u<<8))  buttons |= IKCORE_GB_RIGHT;
    return buttons;
}

extern "C" __attribute__((used, externally_visible, noinline)) int ikcore_mgba_phase4_link_probe(void)
{
    /* Deliberate unresolved-in-absence-of-mGBA calls; compilation/linking
     * demonstrates real co-residence of the GB engine and Snes9x APU. */
    const int model=(int)ikcore_mgba_model(nullptr);
    const unsigned count=ikcore_sgb_audio_count();
    return model == 255 && count <= IKCORE_SGB_AUDIO_CAPACITY ? 0 : -1;
}

extern "C" __attribute__((used, externally_visible, noinline)) void ikcore_mgba_phase4_stop(void)
{
    if(ikcore_combined_gb) {
        ikcore_mgba_close(ikcore_combined_gb);
        ikcore_combined_gb=nullptr;
    }
    ikcore_sgb_audio_reset();
    memset(&ikcore_combined_frame,0,sizeof(ikcore_combined_frame));
}

/* Only the caller owns the loaded Game Boy bytes. mGBA clones the ROM.
 * Intended to be called once at startup, NOT after #43 has run the cart to
 * an arbitrary point: starting the same GB ROM later loses all its state. */
extern "C" __attribute__((used, externally_visible, noinline)) int ikcore_mgba_phase4_prepare(const uint8_t *rom,size_t bytes)
{
    if(ikcore_combined_gb || !rom || !bytes) return 0;
    ikcore_sgb_audio_reset();
    ikcore_combined_gb=ikcore_mgba_open(rom,bytes,1);
    return ikcore_combined_gb ? 1 : 0;
}

/* Audio must remain on the verified Snes9x worker, not a new implementation.
 * This is called on the GB producer thread, while the existing parallel SPC
 * worker owns the SNES APU. The worker's Begin/End frame calls still belong
 * to the Snes9x host and MUST bracket this function when it is enabled. */
extern "C" __attribute__((used, externally_visible, noinline)) int ikcore_mgba_phase4_run_one_frame(uint16_t snes_pad)
{
    if(!ikcore_combined_gb) return 0;
    if(!ikcore_mgba_run(ikcore_combined_gb,
                       ikcore_map_snes_pad(snes_pad),&ikcore_combined_frame))
        return 0;
    /* Do NOT silently consume SOUND and SOU_TRN before the real Snes9x APU
     * is active; otherwise the SPC program and effects would be lost. */
    if(S9xSGBPerfAudioActive())
        (void)ikcore_sgb_spc_dispatch_frame();
    return 1;
}

extern "C" __attribute__((used, externally_visible, noinline)) const ikcore_mgba_frame *ikcore_mgba_phase4_latest_frame(void)
{
    return ikcore_combined_gb ? &ikcore_combined_frame : nullptr;
}

extern "C" __attribute__((used, externally_visible, noinline)) int ikcore_mgba_phase4_is_prepared(void)
{
    return ikcore_combined_gb ? 1 : 0;
}
