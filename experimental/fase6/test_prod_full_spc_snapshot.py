#!/usr/bin/env python3
"""Unit test the exact C++ snapshot bridge injected into pinned Snes9x.
No commercial firmware, physical console or external SNES files required.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess

script = Path(__file__).with_name("patch_snes9x_spc_exports.py").read_text()
start = script.index("/* QuickStart isolated SNES-only snapshot bridge.")
end = script.index('__attribute__((visibility("default")))\nint ikcore_spc_boot_ready(void)', start)
bridge = script[start:end]

cpp = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <cstddef>
using uint8 = uint8_t;
using uint32 = uint32_t;
using bool8 = int;
constexpr bool8 TRUE=1, FALSE=0;
constexpr int SUCCESS=1;
struct { bool8 SuperGameBoy, SGB_BIOSModeActive; } Settings={TRUE,TRUE};
static int active=1;
bool8 S9xSGBPerfAudioActive(void) {return active;}
uint32 S9xFreezeSize(void) {
    return Settings.SuperGameBoy ? 215083u
           : Settings.SGB_BIOSModeActive ? 215099u : 400u;
}
bool8 S9xFreezeGameMem(uint8 *out,uint32 n) {
    if(Settings.SuperGameBoy || Settings.SGB_BIOSModeActive || n!=400u)return FALSE;
    std::memset(out,0,n);
    std::memcpy(out,"#!s9xsnp:0012\n",14u);
    return TRUE;
}
int S9xUnfreezeGameMem(const uint8 *in,uint32 n) {
    return (!Settings.SuperGameBoy && !Settings.SGB_BIOSModeActive &&
            n==400u && std::memcmp(in,"#!s9xsnp:",10u)==0) ? SUCCESS : -1;
}
extern "C" {
''' + bridge + r'''
}
int main() {
    assert(ikcore_spc_full_snapshot_size()==400u);
    assert(Settings.SuperGameBoy && Settings.SGB_BIOSModeActive);
    uint8 buf[400];
    assert(ikcore_spc_full_snapshot_save(buf,sizeof(buf)));
    assert(Settings.SuperGameBoy && Settings.SGB_BIOSModeActive);
    assert(ikcore_spc_full_snapshot_restore(buf,sizeof(buf)));
    assert(Settings.SuperGameBoy && Settings.SGB_BIOSModeActive);
    active=0;
    assert(!ikcore_spc_full_snapshot_save(buf,sizeof(buf)));
    assert(Settings.SuperGameBoy && Settings.SGB_BIOSModeActive);
    std::puts("PASS: full SNES snapshot avoids GB-only SGB! branch, stable size across BIOS handoff");
}
'''
with TemporaryDirectory() as d:
    inp=Path(d)/"full_spc_snapshot.cpp"
    out=Path(d)/"full_spc_snapshot"
    inp.write_text(cpp)
    subprocess.run(["g++","-std=c++17","-Wall","-Wextra","-Werror",str(inp),"-o",str(out)],check=True)
    subprocess.run([str(out)],check=True)
