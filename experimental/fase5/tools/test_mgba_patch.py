#!/usr/bin/env python3
from patch_mgba_sgb_packet_tap import patch
sample = '''#include <mgba/internal/gb/serialize.h>
static void _writeSGBBits(struct GB* gb, int bits) {
\tif (gb->sgbBit == 128 && bits == 2) {
\t\tGBVideoWriteSGBPacket(&gb->video, gb->sgbPacket);
\t\t++gb->sgbBit;
\t}
}'''
out = patch(sample)
assert out.count('ikcore_mgba_sgb_packet(gb->sgbPacket') == 1
assert 'mTimingCurrentTime(&gb->timing)' in out
assert 'gb->timing.globalCycles' not in out
assert out.count('GBVideoWriteSGBPacket(&gb->video, gb->sgbPacket);') == 1
assert patch(out)==out
try:
    patch('bad source')
except ValueError:
    pass
else:
    raise AssertionError('must reject changed source')
print('PASS: mGBA packet observer patch is idempotent and fail-closed')
