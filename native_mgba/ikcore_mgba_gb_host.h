/* Ik Core Fase 3: single GB CPU host using mGBA mCore GB-only engine.
 * This ABI contains NO SNES CPU or second emulated Game Boy CPU. Frames,
 * controls, SRAM, and samples originate exclusively from mGBA.
 *
 * Source is original project code. mGBA's own sources retain MPL-2.0.
 */
#ifndef IKCORE_MGBA_GB_HOST_H
#define IKCORE_MGBA_GB_HOST_H
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
enum { IKCORE_GB_SCREEN_W=160, IKCORE_GB_SCREEN_H=144,
       IKCORE_SGB_SCREEN_W=256, IKCORE_SGB_SCREEN_H=224,
       IKCORE_GB_AUDIO_BUFFER_FRAMES=4096 };
enum {
  IKCORE_GB_A=1u<<0,IKCORE_GB_B=1u<<1,
  IKCORE_GB_SELECT=1u<<2,IKCORE_GB_START=1u<<3,
  IKCORE_GB_RIGHT=1u<<4,IKCORE_GB_LEFT=1u<<5,
  IKCORE_GB_UP=1u<<6,IKCORE_GB_DOWN=1u<<7
};
typedef struct ikcore_mgba_host ikcore_mgba_host;
typedef struct {
  const void *video;
  unsigned width;
  unsigned height;
  unsigned pitch_pixels;
  unsigned pixel_bytes;
  int16_t audio_stereo[IKCORE_GB_AUDIO_BUFFER_FRAMES*2];
  unsigned audio_frames;
  unsigned audio_rate;
  unsigned frame_number;
  unsigned total_gb_cpu_frames;
  double gb_frame_ms;
} ikcore_mgba_frame;
ikcore_mgba_host *ikcore_mgba_open(const void *gb_rom,size_t rom_bytes,int sgb_mode);
/* SGB1 boot code must run BEFORE the cartridge, never be injected after
 * CPU state advanced. Supplied boot code is owned by caller; copied here.
 * Only supported as 256-byte GB-side SGB boot ROM (not the SNES .sfc). */
ikcore_mgba_host *ikcore_mgba_open_sgb_boot(const void *gb_rom,size_t rom_bytes,
                                             const void *boot_256,size_t boot_bytes);
unsigned ikcore_mgba_program_counter(const ikcore_mgba_host *host);
int ikcore_mgba_boot_mapped(const ikcore_mgba_host *host);
int ikcore_mgba_run(ikcore_mgba_host *host,uint8_t gb_keys,ikcore_mgba_frame *out);
size_t ikcore_mgba_clone_sram(ikcore_mgba_host *host,void **out_allocated);
int ikcore_mgba_restore_sram(ikcore_mgba_host *host,const void *data,size_t bytes);
unsigned ikcore_mgba_model(const ikcore_mgba_host *host);
void ikcore_mgba_close(ikcore_mgba_host *host);
#ifdef __cplusplus
}
#endif
#endif
