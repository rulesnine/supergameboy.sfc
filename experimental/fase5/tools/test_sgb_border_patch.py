from patch_mgba_sgb_default_border import patch
body = '''#include <stdio.h>
''' + '''\tvideo->renderer->writePalette(video->renderer, 9 * 4 + 3, video->palette[9 * 4 + 3]);
}

void GBVideoDeinit(struct GBVideo* video) {'''
x=patch(body)
assert x.count('enableSGBBorder(video->renderer, false)')==1
assert x.count('enableSGBBorder(video->renderer, true)')==1
assert 'video->p->model & GB_MODEL_SGB' in x
assert 'video->sgbBorders' in x
assert 'IKF5 SGB fallback' in x
try: patch('no valid anchor')
except ValueError: pass
else: raise AssertionError('fail closed')
print('PASS: SGB border reset patch preserves conditional guard')
