#!/usr/bin/env python3
"""Passive packet observer for verified mGBA 0.10.5 src/gb/io.c; no runtime link."""
import argparse
from pathlib import Path
DECL = '''/* Ik Core experimental SGB packet observer. Optional weak symbol. */
#if defined(__GNUC__)
extern void ikcore_mgba_sgb_packet(const uint8_t *data, uint64_t gb_cycles,
                                   uint64_t gb_frame) __attribute__((weak));
#endif
'''
TARGET = '\tif (gb->sgbBit == 128 && bits == 2) {\n\t\tGBVideoWriteSGBPacket(&gb->video, gb->sgbPacket);'
PATCH = '''\tif (gb->sgbBit == 128 && bits == 2) {
#if defined(__GNUC__)
        if (ikcore_mgba_sgb_packet) {
            ikcore_mgba_sgb_packet(gb->sgbPacket, (uint64_t)mTimingCurrentTime(&gb->timing),
                                   gb->video.frameCounter);
        }
#endif
\t\tGBVideoWriteSGBPacket(&gb->video, gb->sgbPacket);'''
HEADER_ANCHOR = '#include <mgba/internal/gb/serialize.h>\n'
def patch(code):
    if '/* Ik Core experimental SGB packet observer.' in code:
        if code.count('ikcore_mgba_sgb_packet(gb->sgbPacket') != 1:
            raise ValueError('partially or multiply patched mGBA source')
        return code
    if code.count(TARGET) != 1 or code.count(HEADER_ANCHOR) != 1:
        raise ValueError('Unexpected mGBA io.c; do not patch this version')
    code = code.replace(HEADER_ANCHOR, HEADER_ANCHOR + '\n' + DECL, 1)
    return code.replace(TARGET, PATCH, 1)
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source', type=Path)
    args = ap.parse_args()
    before = args.source.read_text()
    after = patch(before)
    if before != after:
        args.source.write_text(after)
    print('OK: passive SGB observer present; existing mGBA parser preserved')
if __name__ == '__main__':
    main()
