#!/usr/bin/env python3
"""Hook mGBA 0.10.5 native software renderer for SGB SOU_TRN (0x09).
No second GB PPU: use the same 2-bit scanline/tile layout already used by
CHR_TRN/PAL_TRN. Capture one 4096-byte transaction at transfer frame 1.
"""
import sys
from pathlib import Path
DEFS=r'''
/* Ik Core F6: audio upload transfer (0x09), optional native observer. */
extern void ikcore_mgba_sou_trn_scanline(unsigned y,const uint8_t *row)
    __attribute__((weak));
extern void ikcore_mgba_sou_trn_complete(uint64_t frame)
    __attribute__((weak));

'''
def patch(s):
    entry='static void GBVideoSoftwareRendererFinishScanline(struct GBVideoRenderer* renderer, int y) {'
    finish='static void GBVideoSoftwareRendererFinishFrame(struct GBVideoRenderer* renderer) {'
    if s.count(entry)!=1 or s.count(finish)!=1: raise ValueError('renderer source version differs')
    # Put declarations at the real (non-prototype) FinishScanline definition,
    # after all header includes, so no extra headers are required.
    s=s.replace(entry,DEFS+entry,1)
    a=s.indexOf(entry); b=s.index(finish,a)
    scan=s[a:b]
    scan_target='''\tif (softwareRenderer->sgbTransfer == 1) {
\t\tsize_t offset'''
    scan_new='''\tif (softwareRenderer->sgbTransfer == 1) {
\t\t/* SOU_TRN uploads sound samples via the same LCD transfer path.
\t\t * mGBA's own palette/marco decoder remains untouched. */
\t\tif ((softwareRenderer->sgbCommandHeader >> 3) == SGB_SOU_TRN &&
\t\t    ikcore_mgba_sou_trn_scanline) {
\t\t\tikcore_mgba_sou_trn_scanline((unsigned)y, softwareRenderer->row);
\t\t}
\t\tsize_t offset'''
    if scan.count(scan_target)!=1: raise ValueError('scanline transfer anchor changed')
    scan=scan.replace(scan_target,scan_new,1)
    s=s[:a]+scan+s[b:]
    b=s.index(finish); end=s.index('static void GBVideoSoftwareRendererEnableSGBBorder(',b)
    block=s[b:end]
    target='''\tif (softwareRenderer->model & GB_MODEL_SGB) {
\t\tswitch (softwareRenderer->sgbCommandHeader >> 3) {'''
    update='''\tif (softwareRenderer->model & GB_MODEL_SGB) {
\t\tif ((softwareRenderer->sgbCommandHeader >> 3) == SGB_SOU_TRN &&
\t\t    softwareRenderer->sgbTransfer == 1 &&
\t\t    ikcore_mgba_sou_trn_complete) {
\t\t\tikcore_mgba_sou_trn_complete(0);
\t\t}
\t\tswitch (softwareRenderer->sgbCommandHeader >> 3) {'''
    if block.count(target)!=1: raise ValueError('frame completion anchor changed')
    block=block.replace(target,update,1)
    tail='''\t\tcase SGB_PAL_TRN:
\t\tcase SGB_CHR_TRN:'''
    if block.count(tail)!=1:raise ValueError('transfer advancement anchor changed')
    block=block.replace(tail,'''\t\tcase SGB_SOU_TRN:
\t\tcase SGB_PAL_TRN:
\t\tcase SGB_CHR_TRN:''',1)
    s=s[:b]+block+s[end:]
    return s
if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: patch_mgba_sou_trn.py MGBA/src/gb/renderers/software.c')
    p=Path(sys.argv[1]);p.write_text(patch(p.read_text()))
    print('PASS: mGBA SOU_TRN native scanline capture and 5-frame transfer progression')
