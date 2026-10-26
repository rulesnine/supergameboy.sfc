#!/usr/bin/env python3
"""Ik Core native direct-SGB center-border overlay compatible with mGBA.

Ports the missing presentation *behavior*, not the mGBA engine:
SGB border tiles inside the 160x144 GB window contribute their nonzero
(opaque) 4bpp pixels. A zero-index pixel is transparent and retains the
original Game Boy/SGB display.

Reference: mGBA src/gb/renderers/software.c, _regenerateSGBBorder() +
GBVideoSoftwareRendererDrawRange(). Jeffrey Pfau, MPL-2.0.
https://github.com/mgba-emu/mgba/blob/master/src/gb/renderers/software.c
Adaptation is independent source in the existing Snes9x-based Ik Core
module, with no mGBA binary, firmware, original art or game data.

Runs after #43 optimize_sgb_compositor.py. Overlay is computed only on
atomic committed PCT_TRN border updates. The #43 original RGB565 border
cache and original fast per-pixel compositor remain exactly unchanged
if no central opaque overlay exists. No PPU, SPC/DSP, ALSA, timing, ROM,
saved games or palette-setting behavior is modified.
"""
from pathlib import Path

p = Path("supersnes9x/sgb/sgb.cpp")
s = p.read_text(encoding="utf-8")

def once(old,new,label):
    global s
    n=s.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected 1 match, found {n}")
    s=s.replace(old,new,1)

field = """\tuint16_t    perf_host_border[SGB_BORDER_W * SGB_BORDER_H] = {};
\tuint32_t    perf_host_border_version = ~0u;"""
once(field, field + """
#ifdef IKCORE_SGB_MGBA_BORDER_OVERLAY
\t// Only regenerated on a complete PCT_TRN commit (not partial CHR_TRN).
\t// mGBA-compatible nonzero BG overlay pixels within the GB viewport.
\tuint8_t     perf_overlay_mask[GB_SCREEN_WIDTH * GB_SCREEN_HEIGHT] = {};
\tuint16_t    perf_overlay_colors[GB_SCREEN_WIDTH * GB_SCREEN_HEIGHT] = {};
\tuint32_t    perf_overlay_serial = 1;
\tuint32_t    perf_overlay_cached = ~0u;
\tuint32_t    perf_overlay_pixels = 0;
#endif""", "overlay buffer")

reset = """\timpl_->perf_host_border_version = ~0u;
#endif
#endif
\timpl_->sgbc_trn.Reset();"""
once(reset, """\timpl_->perf_host_border_version = ~0u;
#ifdef IKCORE_SGB_MGBA_BORDER_OVERLAY
\timpl_->perf_overlay_cached = ~0u;
\timpl_->perf_overlay_serial = 1;
\timpl_->perf_overlay_pixels = 0;
#endif
#endif
#endif
\timpl_->sgbc_trn.Reset();""", "reset overlay metadata")

# Snapshot changes at CHR completion are ignored to prevent half-updated border.
anchor = "\t\timpl_->perf_stable_border_valid = true;"
# Other places use tabs at different nesting levels. Only the valid=true line
# is inspected, and the increment is inserted after every stable commit.
import re
pattern = re.compile(r'(?m)^(\s*)impl_->perf_stable_border_valid = true;$')
matches = list(pattern.finditer(s))
if not (2 <= len(matches) <= 6):
    raise SystemExit(f"stable border commits: unexpected {len(matches)}")
s = pattern.sub(lambda m: m.group(0) + "\n#ifdef IKCORE_SGB_MGBA_BORDER_OVERLAY\n" +
    m.group(1) + "++impl_->perf_overlay_serial;\n#endif", s)

# The cache generator uses the existing stable, transaction-committed
# SgbState border. Emulated GB pixels are never altered.
old = """\t\tconst uint8_t mask = impl_->sgb_state.mask_mode;
\t\tconst uint8_t *src_fb = impl_->ppu.framebuffer;"""
new = r'''#ifdef IKCORE_SGB_MGBA_BORDER_OVERLAY
		if (impl_->perf_overlay_cached != impl_->perf_overlay_serial)
		{
			const auto &border = impl_->sgb_state.border;
			std::memset(impl_->perf_overlay_mask, 0,
			            sizeof impl_->perf_overlay_mask);
			unsigned opaque = 0;
			if (border.tiles_loaded && border.map_loaded)
			{
				for (uint32_t ty = 0; ty < SGB_TILE_ROWS; ++ty)
				{
					for (uint32_t tx = 0; tx < SGB_TILE_COLS; ++tx)
					{
						const uint16_t entry =
							border.tile_map[(ty + SGB_GB_TILE_Y) * 32u
							                + tx + SGB_GB_TILE_X];
						const uint32_t tile = entry & 0x03FFu;
						// Exactly mGBA's 256-tile loaded CHR_TRN range.
						if (tile >= 256u) continue;
						const uint32_t pal = (entry >> 10) & 3u;
						const bool flip_x = (entry & 0x4000u) != 0;
						const bool flip_y = (entry & 0x8000u) != 0;
						const uint8_t *tile_bytes =
							border.tiles + tile * 32u;
						for (uint32_t py = 0; py < 8; ++py)
						{
							const uint32_t src_y = flip_y ? 7u - py : py;
							const uint8_t p0 = tile_bytes[src_y * 2u + 0u];
							const uint8_t p1 = tile_bytes[src_y * 2u + 1u];
							const uint8_t p2 = tile_bytes[16u + src_y * 2u + 0u];
							const uint8_t p3 = tile_bytes[16u + src_y * 2u + 1u];
							for (uint32_t px = 0; px < 8; ++px)
							{
								const uint32_t bit = flip_x ? px : 7u - px;
								const uint32_t ci = ((p0 >> bit) & 1u)
									| (((p1 >> bit) & 1u) << 1)
									| (((p2 >> bit) & 1u) << 2)
									| (((p3 >> bit) & 1u) << 3);
								if (!ci) continue; // index zero = transparent
								const uint32_t pos =
									(ty * 8u + py) * GB_SCREEN_WIDTH
									+ tx * 8u + px;
								impl_->perf_overlay_mask[pos] = 1;
								impl_->perf_overlay_colors[pos] =
									BgrToHost(border.palettes[pal][ci]);
								++opaque;
							}
						}
					}
				}
			}
			impl_->perf_overlay_pixels = opaque;
			impl_->perf_overlay_cached = impl_->perf_overlay_serial;
			char msg[128];
			std::snprintf(msg, sizeof msg,
				"IKOVERLAY commit opaque=%u pix borderPct=%u",
				opaque, (unsigned)impl_->border_pct);
			S9xMessage(S9X_INFO, S9X_ROM_INFO, msg);
		}
#endif
		const uint8_t mask = impl_->sgb_state.mask_mode;
		const uint8_t *src_fb = impl_->ppu.framebuffer;'''
once(old,new,"cache rebuild after atomic PCT commit")

old_loop = """\t\tfor (uint32_t y = 0; y < GB_SCREEN_HEIGHT; ++y)
\t\t{
\t\t\tuint16_t *row = dest + (y + SGB_GB_TILE_Y * 8u) *
\t\t\t\tpitch_pixels + SGB_GB_TILE_X * 8u;
\t\t\tconst uint8_t *src = src_fb + y * GB_SCREEN_WIDTH;
\t\t\tconst uint32_t tile_row = (y >> 3) * SGB_TILE_COLS;
\t\t\tfor (uint32_t x = 0; x < GB_SCREEN_WIDTH; ++x)
\t\t\t\trow[x] = pal_host[tile_row + (x >> 3)][src[x] & 3u];
\t\t}
\t\treturn;"""
new_loop = r'''		for (uint32_t y = 0; y < GB_SCREEN_HEIGHT; ++y)
		{
			uint16_t *row = dest + (y + SGB_GB_TILE_Y * 8u) *
				pitch_pixels + SGB_GB_TILE_X * 8u;
			const uint8_t *src = src_fb + y * GB_SCREEN_WIDTH;
			const uint32_t tile_row = (y >> 3) * SGB_TILE_COLS;
#ifdef IKCORE_SGB_MGBA_BORDER_OVERLAY
			if (impl_->perf_overlay_pixels)
			{
				const uint32_t line = y * GB_SCREEN_WIDTH;
				for (uint32_t x = 0; x < GB_SCREEN_WIDTH; ++x)
				{
					const uint32_t pixel = line + x;
					row[x] = impl_->perf_overlay_mask[pixel]
						? impl_->perf_overlay_colors[pixel]
						: pal_host[tile_row + (x >> 3)][src[x] & 3u];
				}
			}
			else
#endif
			{
				// Original #43 optimized compositor remains bit-identical.
				for (uint32_t x = 0; x < GB_SCREEN_WIDTH; ++x)
					row[x] = pal_host[tile_row + (x >> 3)][src[x] & 3u];
			}
		}
		return;'''
once(old_loop,new_loop,"mGBA overlay per-pixel drawing")

p.write_text(s,encoding="utf-8")
print(f"IKCORE #48 mGBA-compatible transparent overlay installed; atomic border commits={len(matches)}")
