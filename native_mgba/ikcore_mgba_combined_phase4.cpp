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
#include "ikcore_sgb_packet_bus.h"
#include "ikcore_sou_trn_capture.h"
#include "../apu/apu.h"
#include "../snes9x.h"
#include "../sgb/sgb.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>
extern "C" unsigned ikcore_sgb_spc_dispatch_frame(void);

/* The combined library owns the mGBA session. This is deliberately separate
 * from the existing Snes9x SGB singleton to avoid corrupting #43 state. */
static ikcore_mgba_host *ikcore_combined_gb = nullptr;
static ikcore_mgba_frame ikcore_combined_frame = {};
static bool ikcore_phase6_icd2_enabled=false;

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
    // These STRONG calls are mandatory. mGBA and Ik Core were previously
    // linked from static archives where only weak references to the packet
    // and LCD hooks existed, allowing the linker to omit the actual bridge.
    // Pull both objects into the same ELF before any Game Boy CPU starts.
    const unsigned packets=ikcore_sgb_bus_count();
    const unsigned capturing=ikcore_sgb_transfer_capture_active();
    return model==255 && count<=IKCORE_SGB_AUDIO_CAPACITY &&
           packets<=IKCORE_SGB_PACKET_DEPTH && capturing<=1u ? 0:-1;
}

extern "C" __attribute__((used, externally_visible, noinline)) void ikcore_mgba_phase4_stop(void)
{
    if(ikcore_combined_gb) {
        ikcore_mgba_close(ikcore_combined_gb);
        ikcore_combined_gb=nullptr;
    }
    ikcore_phase6_icd2_enabled=false;
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

/* Fase5: initial GB-side boot is owned by mGBA from PC=0000, not
 * transplanted from an already-running Game Boy CPU. Unlike the phase4
 * fast entry, this keeps the boot handshake program instead of skipping it.
 * This API does not *yet* connect SNES BIOS ICD2 reads/writes; no automatic
 * enabling in regular Clover/Hakchi runtime until synchronization exists.
 */
extern "C" __attribute__((used, externally_visible, noinline))
int ikcore_mgba_phase5_prepare_boot(const uint8_t *rom,size_t rom_bytes,
                                   const uint8_t *sgb_gb_boot,size_t boot_bytes)
{
    if(ikcore_combined_gb || !rom || !sgb_gb_boot || boot_bytes!=256)return 0;
    ikcore_sgb_audio_reset();
    ikcore_combined_gb=ikcore_mgba_open_sgb_boot(
        rom,rom_bytes,sgb_gb_boot,boot_bytes);
    if(!ikcore_combined_gb)return 0;
    return ikcore_mgba_boot_mapped(ikcore_combined_gb) ? 1:0;
}
extern "C" __attribute__((used, externally_visible, noinline))
unsigned ikcore_mgba_phase5_boot_pc(void)
{
    return ikcore_mgba_program_counter(ikcore_combined_gb);
}
/* Phase6: packet bridge with exact original Snes9x ICD2 BIOS register
 * ownership, NEVER a second copy of ICD2 in mGBA. 0=normal legacy path,
 * >0=packet accepted by real ICD2, <0=refused: no direct audio fallback.
 * This function is called only after a complete mGBA SGB command.
 */
extern "C" int ikcore_mgba_phase6_route_icd2_packet(const uint8_t *p,unsigned n)
{
    if(!ikcore_phase6_icd2_enabled) return 0;
    if(!Settings.SGB_BIOSModeActive || !ikcore_combined_gb || !p ||
       !S9xSGBBIOSGBIsReleased())return -1;
    return S9xSGBReceiveMGBAPackets(p,n);
}
extern "C" int ikcore_mgba_phase6_icd2_active(void)
{
    return ikcore_phase6_icd2_enabled?1:0;
}
/* Opt-in ONLY: caller must have loaded the actual SNES SGB BIOS and
 * the GB-side boot in mGBA BEFORE running either CPU. Regular #43 and
 * all Hakchi startup paths do not call this yet. */
extern "C" __attribute__((used, externally_visible, noinline))
int ikcore_mgba_phase6_enable_icd2(void)
{
    if(!ikcore_combined_gb || !Settings.SGB_BIOSModeActive)return 0;
    ikcore_phase6_icd2_enabled=true;
    return 1;
}
extern "C" __attribute__((used, externally_visible, noinline))
void ikcore_mgba_phase6_disable_icd2(void)
{
    ikcore_phase6_icd2_enabled=false;
}

extern "C" __attribute__((used, externally_visible, noinline)) const ikcore_mgba_frame *ikcore_mgba_phase4_latest_frame(void)
{
    return ikcore_combined_gb ? &ikcore_combined_frame : nullptr;
}

extern "C" __attribute__((used, externally_visible, noinline)) int ikcore_mgba_phase4_is_prepared(void)
{
    return ikcore_combined_gb ? 1 : 0;
}
