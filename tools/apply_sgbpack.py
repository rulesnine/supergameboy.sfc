from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MMH = ROOT / "supersnes9x" / "memmap.h"
MMC = ROOT / "supersnes9x" / "memmap.cpp"

def replace_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {n}")
    return text.replace(old, new, 1)

# ---- memmap.h
h = MMH.read_text(encoding="utf-8-sig")
h_anchor = """\tbool8\tLoadROMWithSGBBIOSBytes (const uint8 *gb_bytes, uint32 gb_size,
\t                                  const char *gb_path, const char *bios_path);
\t// Detect+load a Game Boy ROM from a memory buffer, routing it into the
"""
h_new = """\tbool8\tLoadROMWithSGBBIOSBytes (const uint8 *gb_bytes, uint32 gb_size,
\t                                  const char *gb_path, const char *bios_path);
\t// SGBPACK1: one-file Super Game Boy container.
\t// Returns 1 = recognized and loaded, 0 = not SGBPACK, -1 = malformed/load error.
\tint\t\tLoadSGBPackFromBytes (const uint8 *data, uint32 size, const char *pack_path);
\t// Detect+load a Game Boy ROM from a memory buffer, routing it into the
"""
h = replace_once(h, h_anchor, h_new, "memmap.h declaration")
MMH.write_text(h, encoding="utf-8")

# ---- memmap.cpp
c = MMC.read_text(encoding="utf-8-sig")

# Standalone loading needs one extra hook before FileLoader/HeaderRemove.
# Snes9x treats any file whose size is +512 bytes past an 8 KiB boundary as
# copier-headered and removes those 512 bytes. SGBPACK v1 happens to be
# 0x140200 bytes, so we must sniff the raw file before HeaderRemove can alter it.
raw_anchor = """    S9xSetBiosNotice(NULL);   // a fresh load owns the missing-BIOS state
    s_bios_paths_at_load = S9xBiosPathsFingerprint();

    // .gb / .gbc — hand off to the SGB subsystem. The 65816 path below
"""
raw_new = """    S9xSetBiosNotice(NULL);   // a fresh load owns the missing-BIOS state
    s_bios_paths_at_load = S9xBiosPathsFingerprint();

    // SGBPACK1 raw-file sniff. This must run before FileLoader/HeaderRemove:
    // a v1 pack is 512 bytes past an 8 KiB boundary and otherwise looks like
    // a copier-headered SNES ROM, causing Snes9x to remove the first 512 bytes
    // and hide the footer from the SGBPACK parser.
    if (!S9xFilenameHasExt(filename, ".zip") &&
        !S9xFilenameHasExt(filename, ".jma"))
    {
        STREAM fp = OPEN_STREAM(filename, "rb");
        if (fp)
        {
            std::vector<uint8> raw(MAX_ROM_SIZE + 0x200);
            const uint32 raw_size = READ_STREAM(raw.data(), (uint32) raw.size(), fp);
            CLOSE_STREAM(fp);

            if (raw_size >= 0x100 &&
                memcmp(raw.data() + raw_size - 0x100, "SGBPACK1", 8) == 0)
            {
                const int pack = LoadSGBPackFromBytes(raw.data(), raw_size, filename);
                if (pack > 0) return TRUE;
                if (pack < 0)
                {
                    S9xMessage(S9X_ERROR, S9X_ROM_INFO,
                               "Invalid or corrupted SGBPACK1 image.");
                    return FALSE;
                }
            }
        }
    }

    // .gb / .gbc — hand off to the SGB subsystem. The 65816 path below
"""
c = replace_once(c, raw_anchor, raw_new, "LoadROM raw SGBPACK hook")

mem_anchor = """    if (optional_rom_filename)
        ROMFilename = optional_rom_filename;
    else
        ROMFilename = "MemoryROM";

    // In-memory GB/SGB detection — mirror LoadROM so libretro and other
"""
mem_new = """    if (optional_rom_filename)
        ROMFilename = optional_rom_filename;
    else
        ROMFilename = "MemoryROM";

    // SGBPACK1 takes priority over ordinary SNES/GB sniffing. The file starts
    // with a valid SGB program ROM, so it must be recognized before SNES scoring.
    {
        int pack = LoadSGBPackFromBytes(source, sourceSize, optional_rom_filename);
        if (pack > 0) return TRUE;
        if (pack < 0) return FALSE;
    }

    // In-memory GB/SGB detection — mirror LoadROM so libretro and other
"""
c = replace_once(c, mem_anchor, mem_new, "LoadROMMem hook")

file_anchor = """        totalFileSize = FileLoader(ROM, filename, MAX_ROM_SIZE);

        if (!totalFileSize)
            return (FALSE);

        // Super Famicom Box carts, merged or as a MAME set, are assembled
"""
file_new = """        totalFileSize = FileLoader(ROM, filename, MAX_ROM_SIZE);

        if (!totalFileSize)
            return (FALSE);

        // Detect a one-file SGBPACK after FileLoader but before any SNES
        // scoring. This also works when the SGBPACK is inside a supported archive.
        {
            int pack = LoadSGBPackFromBytes(ROM, (uint32) totalFileSize, filename);
            if (pack > 0) return TRUE;
            if (pack < 0) return FALSE;
        }

        // Super Famicom Box carts, merged or as a MAME set, are assembled
"""
c = replace_once(c, file_anchor, file_new, "LoadROM hook")

function_block = r'''
// ---------------------------------------------------------------------------
// SGBPACK1
//
// v1 layout:
//   [SGB program ROM][GB cart ROM][256-byte SGB boot ROM][256-byte footer]
//
// Footer (little endian):
//   00  char[8] "SGBPACK1"
//   08  u32 version (=1)
//   0C  u32 flags
//   10  u32 SGB offset
//   14  u32 SGB size
//   18  u32 GB offset
//   1C  u32 GB size
//   20  u32 boot offset
//   24  u32 boot size
//   28  u32 CRC32 SGB
//   2C  u32 CRC32 GB
//   30  u32 CRC32 boot
//   A8  u32 CRC32 of everything before footer
//
// This is a container, not a new SNES mapper. The embedded parts are handed
// to SuperSnes9x's existing SGB BIOS-mode bridge.
// ---------------------------------------------------------------------------

namespace {

struct SGBPackView
{
    const uint8 *sgb;
    uint32 sgb_size;
    const uint8 *gb;
    uint32 gb_size;
    const uint8 *boot;
    uint32 boot_size;
};

static uint32 SGBPackLE32(const uint8 *p)
{
    return (uint32) p[0]
         | ((uint32) p[1] << 8)
         | ((uint32) p[2] << 16)
         | ((uint32) p[3] << 24);
}

static uint32 SGBPackCRC32(const uint8 *data, uint32 size)
{
    uint32 crc = 0xffffffffU;
    for (uint32 i = 0; i < size; ++i)
    {
        crc ^= data[i];
        for (int b = 0; b < 8; ++b)
            crc = (crc >> 1) ^ (0xedb88320U & (0U - (crc & 1U)));
    }
    return crc ^ 0xffffffffU;
}

// 0 = not SGBPACK, 1 = valid, -1 = signature exists but pack is invalid.
static int ParseSGBPack1(const uint8 *data, uint32 size, SGBPackView &v)
{
    static const uint32 footer_size = 0x100;
    if (!data || size < footer_size)
        return 0;

    const uint8 *f = data + size - footer_size;
    if (memcmp(f, "SGBPACK1", 8) != 0)
        return 0;

    if (SGBPackLE32(f + 0x08) != 1)
        return -1;

    const uint32 sgb_off   = SGBPackLE32(f + 0x10);
    const uint32 sgb_size  = SGBPackLE32(f + 0x14);
    const uint32 gb_off    = SGBPackLE32(f + 0x18);
    const uint32 gb_size   = SGBPackLE32(f + 0x1c);
    const uint32 boot_off  = SGBPackLE32(f + 0x20);
    const uint32 boot_size = SGBPackLE32(f + 0x24);
    const uint32 data_end  = size - footer_size;

    if (sgb_off != 0 ||
        (uint64) sgb_off + sgb_size != gb_off ||
        (uint64) gb_off + gb_size != boot_off ||
        (uint64) boot_off + boot_size != data_end ||
        boot_size != 256)
        return -1;

    if ((uint64) sgb_off + sgb_size > data_end ||
        (uint64) gb_off + gb_size > data_end ||
        (uint64) boot_off + boot_size > data_end)
        return -1;

    if (SGBPackCRC32(data + sgb_off, sgb_size) != SGBPackLE32(f + 0x28) ||
        SGBPackCRC32(data + gb_off, gb_size) != SGBPackLE32(f + 0x2c) ||
        SGBPackCRC32(data + boot_off, boot_size) != SGBPackLE32(f + 0x30) ||
        SGBPackCRC32(data, data_end) != SGBPackLE32(f + 0xa8))
        return -1;

    uint8 mode = 0;
    if (!S9xIsSGBBIOSImage(data + sgb_off, sgb_size, &mode) ||
        (mode != 1 && mode != 2))
        return -1;

    std::vector<uint8> boot(data + boot_off, data + boot_off + boot_size);
    if (!IsSGBBootROM(boot))
        return -1;

    if (gb_size < 0x150 || !S9xRomBytesAreGb(data + gb_off, (int32) gb_size))
        return -1;

    v.sgb       = data + sgb_off;
    v.sgb_size  = sgb_size;
    v.gb        = data + gb_off;
    v.gb_size   = gb_size;
    v.boot      = data + boot_off;
    v.boot_size = boot_size;
    return 1;
}

} // anonymous namespace

int CMemory::LoadSGBPackFromBytes(const uint8 *data, uint32 size, const char *pack_path)
{
    SGBPackView p = {};
    const int parsed = ParseSGBPack1(data, size, p);
    if (parsed <= 0)
        return parsed;

    // Copy first: LoadROMMem replaces the global SNES ROM buffer.
    std::vector<uint8> sgb (p.sgb,  p.sgb  + p.sgb_size);
    std::vector<uint8> gb  (p.gb,   p.gb   + p.gb_size);
    std::vector<uint8> boot(p.boot, p.boot + p.boot_size);

    uint8 mode = 1;
    if (!S9xIsSGBBIOSImage(sgb.data(), (uint32) sgb.size(), &mode))
        return -1;

    S9xDeleteCheats();
    if (Settings.SuperGameBoy || Settings.SGB_BIOSModeActive)
    {
        S9xSGBDeinit();
        Settings.SuperGameBoy       = FALSE;
        Settings.SGB_BIOSModeActive = FALSE;
    }

    if (!S9xSGBInit())
        return -1;

#ifdef SGBPACK_LITE
    // NES/SNES Classic fast path: use the dedicated GB/SGB engine directly
    // instead of running the complete SNES-side SGB BIOS every frame.
    // force_model=3 enables authentic SGB command processing (palettes,
    // ATTR, MASK, CHR_TRN/PCT_TRN border uploads) without the 65816/SPC/PPU.
    S9xSGBSetForceModel(3);
    S9xSGBSetRunMode(mode);
    if (!S9xSGBLoadBootROMBytes(boot.data(), boot.size()))
    {
        S9xSGBDeinit();
        return -1;
    }
    if (!S9xSGBLoadROMBytes(gb.data(), gb.size(), pack_path))
    {
        S9xSGBDeinit();
        return -1;
    }

    S9xSGBPrepareBiosCart();
    S9xSGBSetAudioRate(Settings.SoundPlaybackRate);

    Settings.SuperGameBoy       = TRUE;
    Settings.SGB_BIOSModeActive = FALSE;
    Settings.GameBoyRunMode     = mode;
    Settings.GBClockMultiplier  = 1.0f;
    Settings.PAL                = FALSE;
    Settings.FrameTime          = Settings.FrameTimeNTSC;
    ROMFramesPerSecond          = 60;
#else
    if (!S9xSGBLoadBootROMBytes(boot.data(), boot.size()))
    {
        S9xSGBDeinit();
        return -1;
    }

    if (!S9xSGBLoadROMBytes(gb.data(), gb.size(), pack_path))
    {
        S9xSGBDeinit();
        return -1;
    }

    S9xSGBPrepareBiosCart();
    S9xSGBSetAudioRate(Settings.SoundPlaybackRate);

    // Recursive call is intentional and safe: the extracted SGB region has no
    // SGBPACK footer, so it follows the ordinary SNES BIOS-cart load path.
    if (!LoadROMMem(sgb.data(), (uint32) sgb.size(), pack_path))
    {
        S9xSGBDeinit();
        return -1;
    }

    S9xDeleteCheats();

    Settings.SGB_BIOSModeActive = TRUE;
    Settings.GameBoyRunMode     = mode;
    Settings.GBClockMultiplier  = 1.0f;
    S9xSGBSetRunMode(mode);
    S9xMessage(S9X_INFO, S9X_ROM_INFO,
               "IKCORE FULL SGB BIOS path enabled.");
#endif

    if (pack_path && *pack_path)
    {
        strncpy(Settings.GBRomPath, pack_path, sizeof Settings.GBRomPath - 1);
        Settings.GBRomPath[sizeof Settings.GBRomPath - 1] = '\0';
        strncpy(Settings.SGB_BIOSPath, pack_path, sizeof Settings.SGB_BIOSPath - 1);
        Settings.SGB_BIOSPath[sizeof Settings.SGB_BIOSPath - 1] = '\0';
        ROMFilename = pack_path;
    }
    else
    {
        Settings.GBRomPath[0] = '\0';
        Settings.SGB_BIOSPath[0] = '\0';
        ROMFilename = "SGBPACK";
    }

    S9xInitCheatData();
    if (Settings.ApplyCheats)
        S9xCheatsEnable();
    if (pack_path && *pack_path)
        S9xLoadCheatFile(S9xGetFilename(".cht", CHEAT_DIR).c_str());

    S9xMessage(S9X_INFO, S9X_ROM_INFO,
               "Loaded SGBPACK1 single-file Super Game Boy image.");
    return 1;
}

'''

insert_anchor = """bool8 CMemory::LoadROMInt (int32 ROMfillSize)
{
"""
c = replace_once(c, insert_anchor, function_block + insert_anchor, "SGBPACK function insertion")
MMC.write_text(c, encoding="utf-8")

# SGBPACK_LITE keeps the direct GB/SGB engine but renders the full 256x224
# SGB composite (border + 160x144 game pane), not the plain GB-only surface.
CPU = ROOT / "supersnes9x" / "cpuexec.cpp"
cpu = CPU.read_text(encoding="utf-8-sig")
cpu_anchor = """		PPU.ScreenHeight          = SGB_GB_SCREEN_H;
		IPPU.RenderedScreenWidth  = SGB_GB_SCREEN_W;
		IPPU.RenderedScreenHeight = SGB_GB_SCREEN_H;
"""
cpu_new = """#ifdef SGBPACK_LITE
		PPU.ScreenHeight          = 224;
		IPPU.RenderedScreenWidth  = 256;
		IPPU.RenderedScreenHeight = 224;
#else
		PPU.ScreenHeight          = SGB_GB_SCREEN_H;
		IPPU.RenderedScreenWidth  = SGB_GB_SCREEN_W;
		IPPU.RenderedScreenHeight = SGB_GB_SCREEN_H;
#endif
"""
cpu = replace_once(cpu, cpu_anchor, cpu_new, "cpuexec lite geometry")

cpu_anchor2 = """			IPPU.RenderedScreenWidth  = SGB_GB_SCREEN_W;
			IPPU.RenderedScreenHeight = SGB_GB_SCREEN_H;
			S9xSGBBlitScreenGB(GFX.Screen, GFX.RealPPL);
"""
cpu_new2 = """#ifdef SGBPACK_LITE
			IPPU.RenderedScreenWidth  = 256;
			IPPU.RenderedScreenHeight = 224;
			S9xSGBBlitScreen(GFX.Screen, GFX.RealPPL);
#else
			IPPU.RenderedScreenWidth  = SGB_GB_SCREEN_W;
			IPPU.RenderedScreenHeight = SGB_GB_SCREEN_H;
			S9xSGBBlitScreenGB(GFX.Screen, GFX.RealPPL);
#endif
"""
cpu = replace_once(cpu, cpu_anchor2, cpu_new2, "cpuexec lite blit")
CPU.write_text(cpu, encoding="utf-8")


# ---- Ik Core Windows identity
WLANG = ROOT / "supersnes9x" / "win32" / "wlanguage.h"
w = WLANG.read_text(encoding="utf-8-sig")
if "SuperSnes9x" not in w:
    raise SystemExit("wlanguage.h: expected SuperSnes9x branding anchor")
w = w.replace("SuperSnes9x", "Ik Core")

disc_start = w.find("#define DISCLAIMER_TEXT")
disc_end = w.find("\n\n#define APP_NAME", disc_start)
if disc_start < 0 or disc_end < 0:
    raise SystemExit("wlanguage.h: disclaimer anchors not found")
disclaimer = r'''#define DISCLAIMER_TEXT        TEXT("Ik Core v%s for Windows.\r\n\
Unofficial SGBPACK Runtime.\r\n\r\n\
Derived from SuperSnes9x / Snes9x.\r\n\
Based on Snes9x by Gary Henderson and Jerremy Koot, with contributions\r\n\
from the Snes9x and SuperSnes9x development communities.\r\n\r\n\
Ik Core adds SGBPACK1 single-file loading and its own Windows identity.\r\n\
Full copyright notices and license terms are distributed with this build.\r\n\r\n\
Ik Core is independent and is not affiliated with, authorized, sponsored\r\n\
or endorsed by Nintendo Co., Ltd. Nintendo and related product names are\r\n\
trademarks of their respective owners.")'''
w = w[:disc_start] + disclaimer + w[disc_end:]
WLANG.write_text(w, encoding="utf-8")

RC = ROOT / "supersnes9x" / "win32" / "rsrc" / "snes9x.rc"
rc = RC.read_text(encoding="utf-8-sig")
if "SuperSnes9x" not in rc:
    raise SystemExit("snes9x.rc: expected SuperSnes9x branding anchor")
rc = rc.replace("SuperSnes9x", "Ik Core")
rc = rc.replace(" FILEVERSION 1,5,5,0", " FILEVERSION 1,0,0,0", 1)
rc = rc.replace(" PRODUCTVERSION 1,5,5,0", " PRODUCTVERSION 1,0,0,0", 1)
rc = rc.replace('VALUE "CompanyName", "http://www.snes9x.com"', 'VALUE "CompanyName", "Ik Core Project"', 1)
rc = rc.replace('VALUE "FileDescription", "Ik Core"', 'VALUE "FileDescription", "Ik Core - SGBPACK Runtime"', 1)
rc = rc.replace('VALUE "FileVersion", "1.63"', 'VALUE "FileVersion", "1.0.0"', 1)
rc = rc.replace('VALUE "InternalName", "Ik Core"', 'VALUE "InternalName", "IkCore"', 1)
rc = rc.replace('VALUE "LegalCopyright", "Copyright  1996-2024"', 'VALUE "LegalCopyright", "Snes9x contributors; Ik Core modifications 2026"', 1)
rc = rc.replace('VALUE "OriginalFilename", "Ik Core.exe"', 'VALUE "OriginalFilename", "IkCore.exe"', 1)
rc = rc.replace('VALUE "ProductName", "Ik Core SNES Emulator"', 'VALUE "ProductName", "Ik Core - SGBPACK Runtime"', 1)
rc = rc.replace('VALUE "ProductVersion", "1.63"', 'VALUE "ProductVersion", "1.0.0"', 1)
RC.write_text(rc, encoding="utf-8")

WS = ROOT / "supersnes9x" / "win32" / "wsnes9x.cpp"
ws = WS.read_text(encoding="utf-8-sig")
ws = ws.replace("SuperSnes9x", "Ik Core")
ws = ws.replace('TEXT("Snes9x - Menu Initialization Failure")',
                'TEXT("Ik Core - Menu Initialization Failure")')
ws = ws.replace("before opening Snes9x again.", "before opening Ik Core again.")
ws = ws.replace("Snes9x command line options have been written to stdout.txt in the same folder as snes9x.exe",
                "Ik Core command line options have been written to stdout.txt in the same folder as IkCore.exe")
WS.write_text(ws, encoding="utf-8")

# Brand the SGBPACK loader message itself so CI can prove this integration ran.
c = MMC.read_text(encoding="utf-8")
c = c.replace("Loaded SGBPACK1 single-file Super Game Boy image.",
              "Ik Core loaded SGBPACK1 single-file Super Game Boy image.")
MMC.write_text(c, encoding="utf-8")


print("SGBPACK and Ik Core source integration applied successfully.")


# ---- N2.4 sampled GB/SGB profiler (compiled only with IKCORE_SGB_PROFILE)
# The profiler is intentionally sampled: clock_gettime around every memory
# machine-cycle would distort this Cortex-A7 workload. We sample 1/256 calls
# and scale the totals, while frame/compositor/command timings are exact.

GBMH = ROOT / "supersnes9x" / "sgb" / "gb_memory.h"
gmh = GBMH.read_text(encoding="utf-8-sig")
gmh_anchor = """void MemTick(Memory &m, int32_t tcycles, bool tick_dma = true);
void MemOamBugIncDec(Memory &m, uint16_t value);
"""
gmh_new = """void MemTick(Memory &m, int32_t tcycles, bool tick_dma = true);
void MemOamBugIncDec(Memory &m, uint16_t value);

#ifdef IKCORE_SGB_PROFILE
struct SgbMemProfile
{
	uint64_t calls;
	uint64_t samples;
	uint64_t timer_ns;
	uint64_t dma_ns;
	uint64_t ppu_ns;
	uint64_t apu_ns;
	uint64_t rtc_ns;
};
void SgbMemProfileReset(void);
void SgbMemProfileGet(SgbMemProfile *out);
#endif
"""
gmh = replace_once(gmh, gmh_anchor, gmh_new, "gb_memory.h profiler declarations")
GBMH.write_text(gmh, encoding="utf-8")

GBMC = ROOT / "supersnes9x" / "sgb" / "gb_memory.cpp"
gmc = GBMC.read_text(encoding="utf-8-sig")
gmc = replace_once(gmc, "#include <cstring>\n", "#include <cstring>\n#ifdef IKCORE_SGB_PROFILE\n#include <ctime>\n#endif\n", "gb_memory.cpp profiler include")

gmc_anchor = """namespace SGB {

namespace {
}
"""
gmc_new = """namespace SGB {

#ifdef IKCORE_SGB_PROFILE
static SgbMemProfile g_ik_mem_prof = {};

static inline uint64_t IkProfNowNs(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return static_cast<uint64_t>(ts.tv_sec) * 1000000000ULL +
	       static_cast<uint64_t>(ts.tv_nsec);
}

void SgbMemProfileReset(void)
{
	std::memset(&g_ik_mem_prof, 0, sizeof g_ik_mem_prof);
}

void SgbMemProfileGet(SgbMemProfile *out)
{
	if (out) *out = g_ik_mem_prof;
}
#endif

namespace {
}
"""
gmc = replace_once(gmc, gmc_anchor, gmc_new, "gb_memory.cpp profiler globals")

old_tick = """\tif (!stopped && m.timer) TimerStep(*m.timer, m, tcycles);

\t// One DMA byte per 4 CPU T-cycles (a split write cycle ticks DMA only
\t// in its first half so the engine still sees whole M-cycles).
\tif (!stopped && tick_dma)
\t\tfor (int32_t t = 0; t < tcycles; t += 4)
\t\t\tDmaTickM(m);

\tint32_t rt = tcycles;
\tif (m.double_speed)
\t{
\t\tconst int32_t acc = m.ds_tick_rem + tcycles;
\t\trt            = acc >> 1;
\t\tm.ds_tick_rem = static_cast<uint8_t>(acc & 1);
\t}
\tif (rt > 0)
\t{
\t\tif (m.ppu) PpuStep(*m.ppu, m, rt);
\t\tif (m.apu && !(stopped && !m.cgb_hw)) ApuStep(*m.apu, rt);
\t\tif (m.cart) MbcTickRtc(m.cart->mbc, rt);
\t}
"""
new_tick = """#ifdef IKCORE_SGB_PROFILE
\t++g_ik_mem_prof.calls;
\tconst bool ik_sample = (g_ik_mem_prof.calls & 0xFFu) == 0;
\tif (ik_sample) ++g_ik_mem_prof.samples;
\tuint64_t ik_t0 = 0;

\tif (!stopped && m.timer)
\t{
\t\tif (ik_sample) ik_t0 = IkProfNowNs();
\t\tTimerStep(*m.timer, m, tcycles);
\t\tif (ik_sample) g_ik_mem_prof.timer_ns += IkProfNowNs() - ik_t0;
\t}

\tif (!stopped && tick_dma)
\t{
\t\tif (ik_sample) ik_t0 = IkProfNowNs();
\t\tfor (int32_t t = 0; t < tcycles; t += 4)
\t\t\tDmaTickM(m);
\t\tif (ik_sample) g_ik_mem_prof.dma_ns += IkProfNowNs() - ik_t0;
\t}

\tint32_t rt = tcycles;
\tif (m.double_speed)
\t{
\t\tconst int32_t acc = m.ds_tick_rem + tcycles;
\t\trt            = acc >> 1;
\t\tm.ds_tick_rem = static_cast<uint8_t>(acc & 1);
\t}
\tif (rt > 0)
\t{
\t\tif (m.ppu)
\t\t{
\t\t\tif (ik_sample) ik_t0 = IkProfNowNs();
\t\t\tPpuStep(*m.ppu, m, rt);
\t\t\tif (ik_sample) g_ik_mem_prof.ppu_ns += IkProfNowNs() - ik_t0;
\t\t}
\t\tif (m.apu && !(stopped && !m.cgb_hw))
\t\t{
\t\t\tif (ik_sample) ik_t0 = IkProfNowNs();
\t\t\tApuStep(*m.apu, rt);
\t\t\tif (ik_sample) g_ik_mem_prof.apu_ns += IkProfNowNs() - ik_t0;
\t\t}
\t\tif (m.cart)
\t\t{
\t\t\tif (ik_sample) ik_t0 = IkProfNowNs();
\t\t\tMbcTickRtc(m.cart->mbc, rt);
\t\t\tif (ik_sample) g_ik_mem_prof.rtc_ns += IkProfNowNs() - ik_t0;
\t\t}
\t}
#else
\tif (!stopped && m.timer) TimerStep(*m.timer, m, tcycles);

\t// One DMA byte per 4 CPU T-cycles (a split write cycle ticks DMA only
\t// in its first half so the engine still sees whole M-cycles).
\tif (!stopped && tick_dma)
\t\tfor (int32_t t = 0; t < tcycles; t += 4)
\t\t\tDmaTickM(m);

\tint32_t rt = tcycles;
\tif (m.double_speed)
\t{
\t\tconst int32_t acc = m.ds_tick_rem + tcycles;
\t\trt            = acc >> 1;
\t\tm.ds_tick_rem = static_cast<uint8_t>(acc & 1);
\t}
\tif (rt > 0)
\t{
\t\tif (m.ppu) PpuStep(*m.ppu, m, rt);
\t\tif (m.apu && !(stopped && !m.cgb_hw)) ApuStep(*m.apu, rt);
\t\tif (m.cart) MbcTickRtc(m.cart->mbc, rt);
\t}
#endif
"""
gmc = replace_once(gmc, old_tick, new_tick, "gb_memory.cpp sampled component profiler")
GBMC.write_text(gmc, encoding="utf-8")

SGB = ROOT / "supersnes9x" / "sgb" / "sgb.cpp"
sg = SGB.read_text(encoding="utf-8-sig")
sg = replace_once(sg, "#include <vector>\n", "#include <vector>\n#ifdef IKCORE_SGB_PROFILE\n#include <ctime>\n#endif\n", "sgb.cpp profiler include")

sg_anchor = """namespace SGB {

// Embedded SGB1 / SGB2 GB-side boot ROMs."""
sg_new = """namespace SGB {

#ifdef IKCORE_SGB_PROFILE
struct IkCoreSgbProfile
{
	uint64_t frames = 0;
	uint64_t frame_ns = 0;
	uint64_t cpu_steps = 0;
	uint64_t cpu_samples = 0;
	uint64_t cpu_step_sample_ns = 0;
	uint64_t command_calls = 0;
	uint64_t command_ns = 0;
	uint64_t blit_calls = 0;
	uint64_t blit_ns = 0;
};

static IkCoreSgbProfile g_ik_prof;

static inline uint64_t IkSgbProfNowNs(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return static_cast<uint64_t>(ts.tv_sec) * 1000000000ULL +
	       static_cast<uint64_t>(ts.tv_nsec);
}

struct IkSgbProfScope
{
	uint64_t *dst;
	uint64_t t0;
	explicit IkSgbProfScope(uint64_t *p) : dst(p), t0(IkSgbProfNowNs()) {}
	~IkSgbProfScope() { *dst += IkSgbProfNowNs() - t0; }
};

static void IkSgbProfReset(void)
{
	g_ik_prof = IkCoreSgbProfile();
	SgbMemProfileReset();
}

static void IkSgbProfReport(void)
{
	if (!g_ik_prof.frames) return;

	SgbMemProfile mp = {};
	SgbMemProfileGet(&mp);

	const double frames = static_cast<double>(g_ik_prof.frames);
	const double mem_scale = mp.samples ?
		static_cast<double>(mp.calls) / static_cast<double>(mp.samples) : 0.0;
	const double cpu_scale = g_ik_prof.cpu_samples ?
		static_cast<double>(g_ik_prof.cpu_steps) /
		static_cast<double>(g_ik_prof.cpu_samples) : 0.0;

	const double frame_ms = static_cast<double>(g_ik_prof.frame_ns) / frames / 1.0e6;
	const double cpu_incl_ms =
		static_cast<double>(g_ik_prof.cpu_step_sample_ns) * cpu_scale / frames / 1.0e6;
	const double timer_ms = static_cast<double>(mp.timer_ns) * mem_scale / frames / 1.0e6;
	const double dma_ms   = static_cast<double>(mp.dma_ns)   * mem_scale / frames / 1.0e6;
	const double ppu_ms   = static_cast<double>(mp.ppu_ns)   * mem_scale / frames / 1.0e6;
	const double apu_ms   = static_cast<double>(mp.apu_ns)   * mem_scale / frames / 1.0e6;
	const double rtc_ms   = static_cast<double>(mp.rtc_ns)   * mem_scale / frames / 1.0e6;
	double cpu_bus_ms = cpu_incl_ms - timer_ms - dma_ms - ppu_ms - apu_ms - rtc_ms;
	if (cpu_bus_ms < 0.0) cpu_bus_ms = 0.0;
	const double cmd_ms = static_cast<double>(g_ik_prof.command_ns) / frames / 1.0e6;
	const double blit_ms = g_ik_prof.blit_calls ?
		static_cast<double>(g_ik_prof.blit_ns) /
		static_cast<double>(g_ik_prof.blit_calls) / 1.0e6 : 0.0;

	char msg[512];
	std::snprintf(msg, sizeof msg,
		"IKPROF frames=%llu frame=%.3fms SM83+bus~=%.3fms PPU~=%.3fms "
		"APU~=%.3fms timer~=%.3fms DMA~=%.3fms RTC~=%.3fms "
		"SGBcmd=%.3fms compose=%.3fms memSamples=%llu cpuSamples=%llu",
		static_cast<unsigned long long>(g_ik_prof.frames),
		frame_ms, cpu_bus_ms, ppu_ms, apu_ms, timer_ms, dma_ms, rtc_ms,
		cmd_ms, blit_ms,
		static_cast<unsigned long long>(mp.samples),
		static_cast<unsigned long long>(g_ik_prof.cpu_samples));
	S9xMessage(S9X_INFO, S9X_ROM_INFO, msg);
}
#endif

// Embedded SGB1 / SGB2 GB-side boot ROMs."""
sg = replace_once(sg, sg_anchor, sg_new, "sgb.cpp profiler globals")

old_step = """\twhile (impl_->ppu.t_cycles < target_t)
\t{
\t\tconst bool was_boot = impl_->mem.boot_rom_enabled;
\t\timpl_->cpu.Step(impl_->mem);

\t\tif (was_boot && !impl_->mem.boot_rom_enabled &&
"""
new_step = """\twhile (impl_->ppu.t_cycles < target_t)
\t{
\t\tconst bool was_boot = impl_->mem.boot_rom_enabled;
#ifdef IKCORE_SGB_PROFILE
\t\t++g_ik_prof.cpu_steps;
\t\tif ((g_ik_prof.cpu_steps & 0xFFu) == 0)
\t\t{
\t\t\tconst uint64_t ik_t0 = IkSgbProfNowNs();
\t\t\timpl_->cpu.Step(impl_->mem);
\t\t\tg_ik_prof.cpu_step_sample_ns += IkSgbProfNowNs() - ik_t0;
\t\t\t++g_ik_prof.cpu_samples;
\t\t}
\t\telse
\t\t{
\t\t\timpl_->cpu.Step(impl_->mem);
\t\t}
#else
\t\timpl_->cpu.Step(impl_->mem);
#endif

\t\tif (was_boot && !impl_->mem.boot_rom_enabled &&
"""
sg = replace_once(sg, old_step, new_step, "sgb.cpp sampled CPU profiler")

old_cmd = """void Emulator::OnSgbCommandInternal(uint8_t cmd, const uint8_t *data, uint32_t len)
{
\tDbgPushCmd(cmd);
"""
new_cmd = """void Emulator::OnSgbCommandInternal(uint8_t cmd, const uint8_t *data, uint32_t len)
{
#ifdef IKCORE_SGB_PROFILE
\tIkSgbProfScope ik_scope(&g_ik_prof.command_ns);
\t++g_ik_prof.command_calls;
#endif
\tDbgPushCmd(cmd);
"""
sg = replace_once(sg, old_cmd, new_cmd, "sgb.cpp command profiler")

old_facade = """bool S9xSGBInit(void)               { return SGB::Instance().Init(); }
void S9xSGBDeinit(void)             { SGB::Instance().Deinit(); }
"""
new_facade = """bool S9xSGBInit(void)
{
#ifdef IKCORE_SGB_PROFILE
\tSGB::IkSgbProfReset();
#endif
\treturn SGB::Instance().Init();
}
void S9xSGBDeinit(void)             { SGB::Instance().Deinit(); }
"""
sg = replace_once(sg, old_facade, new_facade, "sgb.cpp profiler reset")

old_run_facade = """void S9xSGBRunFrame(void)           { SGB::Instance().RunFrame(); }
void S9xSGBRunCycles(int tcycles)   { SGB::Instance().RunCycles(static_cast<int32_t>(tcycles)); }
"""
new_run_facade = """void S9xSGBRunFrame(void)
{
#ifdef IKCORE_SGB_PROFILE
\tconst uint64_t ik_t0 = SGB::IkSgbProfNowNs();
\tSGB::Instance().RunFrame();
\tSGB::g_ik_prof.frame_ns += SGB::IkSgbProfNowNs() - ik_t0;
\t++SGB::g_ik_prof.frames;
\tif ((SGB::g_ik_prof.frames % 120u) == 0)
\t\tSGB::IkSgbProfReport();
#else
\tSGB::Instance().RunFrame();
#endif
}
void S9xSGBRunCycles(int tcycles)   { SGB::Instance().RunCycles(static_cast<int32_t>(tcycles)); }
"""
sg = replace_once(sg, old_run_facade, new_run_facade, "sgb.cpp frame profiler")

old_blit_facade = """void S9xSGBBlitScreen(uint16_t *dest, uint32_t pitch_pixels)
{
\tSGB::Instance().BlitScreen(dest, pitch_pixels);
}
"""
new_blit_facade = """void S9xSGBBlitScreen(uint16_t *dest, uint32_t pitch_pixels)
{
#ifdef IKCORE_SGB_PROFILE
\tconst uint64_t ik_t0 = SGB::IkSgbProfNowNs();
\tSGB::Instance().BlitScreen(dest, pitch_pixels);
\tSGB::g_ik_prof.blit_ns += SGB::IkSgbProfNowNs() - ik_t0;
\t++SGB::g_ik_prof.blit_calls;
#else
\tSGB::Instance().BlitScreen(dest, pitch_pixels);
#endif
}
"""
sg = replace_once(sg, old_blit_facade, new_blit_facade, "sgb.cpp compositor profiler")
SGB.write_text(sg, encoding="utf-8")

print("IK Core N2.4 sampled GB/SGB profiler integration applied.")


# ---- N2.5 lazy-APU structural optimization diagnostic
# Keep GB/SGB behavior, but do not call ApuStep once per machine cycle.
# Accumulate real-time APU cycles and flush at every APU-visible I/O access
# plus once at the end of each direct GB frame. This preserves register/write
# ordering while removing thousands of tiny ApuStep calls per frame.

GBMH = ROOT / "supersnes9x" / "sgb" / "gb_memory.h"
gmh = GBMH.read_text(encoding="utf-8-sig")

lazy_field_anchor = """\t// Double-speed odd-cycle carry for MemTick's CPU→PPU/APU clock halving.
\t// Transient (never serialized).
\tuint8_t  ds_tick_rem = 0;
"""
lazy_field_new = """\t// Double-speed odd-cycle carry for MemTick's CPU→PPU/APU clock halving.
\t// Transient (never serialized).
\tuint8_t  ds_tick_rem = 0;

#ifdef IKCORE_SGB_LAZY_APU
\t// Deferred real-time APU cycles. Flushed before every APU-visible register
\t// access and at the end of each direct GB frame.
\tint32_t  apu_pending_cycles = 0;
#endif
"""
gmh = replace_once(gmh, lazy_field_anchor, lazy_field_new, "gb_memory.h lazy APU field")

lazy_decl_anchor = """void MemTick(Memory &m, int32_t tcycles, bool tick_dma = true);
void MemOamBugIncDec(Memory &m, uint16_t value);
"""
lazy_decl_new = """void MemTick(Memory &m, int32_t tcycles, bool tick_dma = true);
void MemOamBugIncDec(Memory &m, uint16_t value);
#ifdef IKCORE_SGB_LAZY_APU
void MemFlushApu(Memory &m);
#endif
"""
gmh = replace_once(gmh, lazy_decl_anchor, lazy_decl_new, "gb_memory.h lazy APU declaration")
GBMH.write_text(gmh, encoding="utf-8")

GBMC = ROOT / "supersnes9x" / "sgb" / "gb_memory.cpp"
gmc = GBMC.read_text(encoding="utf-8-sig")

reset_anchor = """\tm.late_dots    = -1;
\tm.ds_tick_rem  = 0;
\tm.cgb_hw       = cgb;
"""
reset_new = """\tm.late_dots    = -1;
\tm.ds_tick_rem  = 0;
#ifdef IKCORE_SGB_LAZY_APU
\tm.apu_pending_cycles = 0;
#endif
\tm.cgb_hw       = cgb;
"""
gmc = replace_once(gmc, reset_anchor, reset_new, "gb_memory.cpp lazy APU reset")

tick_normal = """\tif (rt > 0)
\t{
\t\tif (m.ppu) PpuStep(*m.ppu, m, rt);
\t\tif (m.apu && !(stopped && !m.cgb_hw)) ApuStep(*m.apu, rt);
\t\tif (m.cart) MbcTickRtc(m.cart->mbc, rt);
\t}
#endif
}
"""
tick_lazy = """\tif (rt > 0)
\t{
\t\tif (m.ppu) PpuStep(*m.ppu, m, rt);
#ifdef IKCORE_SGB_LAZY_APU
\t\tif (m.apu && !(stopped && !m.cgb_hw))
\t\t\tm.apu_pending_cycles += rt;
#else
\t\tif (m.apu && !(stopped && !m.cgb_hw)) ApuStep(*m.apu, rt);
#endif
\t\t// RTC exists only on MBC3. Avoid a function call on every GB machine
\t\t// cycle for all other mapper types (KOF96 uses MBC5).
\t\tif (m.cart && m.cart->mbc.type == MbcType::MBC3)
\t\t\tMbcTickRtc(m.cart->mbc, rt);
\t}
#endif
}
"""
if tick_normal not in gmc:
    raise RuntimeError("normal MemTick tail anchor missing")
gmc = gmc.replace(tick_normal, tick_lazy, 1)

flush_insert_anchor = """


uint8_t MemRead(Memory &m, uint16_t addr)
"""
flush_insert = """

#ifdef IKCORE_SGB_LAZY_APU
void MemFlushApu(Memory &m)
{
\tif (!m.apu || m.apu_pending_cycles <= 0) return;
\tconst int32_t cycles = m.apu_pending_cycles;
\tm.apu_pending_cycles = 0;
\tApuStep(*m.apu, cycles);
}
#endif

uint8_t MemRead(Memory &m, uint16_t addr)
"""
gmc = replace_once(gmc, flush_insert_anchor, flush_insert, "gb_memory.cpp lazy APU flush insertion");

# Sync PCM reads.
gmc = replace_once(gmc,
"""\t\tcase 0xFF76:
\t\t\treturn (m.ppu && m.ppu->cgb && m.apu) ? ApuReadPcm12(*m.apu) : 0xFF;
\t\tcase 0xFF77:
\t\t\treturn (m.ppu && m.ppu->cgb && m.apu) ? ApuReadPcm34(*m.apu) : 0xFF;
""",
"""\t\tcase 0xFF76:
#ifdef IKCORE_SGB_LAZY_APU
\t\t\tMemFlushApu(m);
#endif
\t\t\treturn (m.ppu && m.ppu->cgb && m.apu) ? ApuReadPcm12(*m.apu) : 0xFF;
\t\tcase 0xFF77:
#ifdef IKCORE_SGB_LAZY_APU
\t\t\tMemFlushApu(m);
#endif
\t\t\treturn (m.ppu && m.ppu->cgb && m.apu) ? ApuReadPcm34(*m.apu) : 0xFF;
""", "gb_memory.cpp PCM lazy sync");

# Sync normal APU reads.
gmc = replace_once(gmc,
"""\tif (addr >= 0xFF10 && addr <= 0xFF3F)
\t{
\t\treturn m.apu ? ApuRead(*m.apu, addr, m.ppu && m.ppu->cgb) : 0xFF;
\t}
""",
"""\tif (addr >= 0xFF10 && addr <= 0xFF3F)
\t{
#ifdef IKCORE_SGB_LAZY_APU
\t\tMemFlushApu(m);
#endif
\t\treturn m.apu ? ApuRead(*m.apu, addr, m.ppu && m.ppu->cgb) : 0xFF;
\t}
""", "gb_memory.cpp APU read lazy sync");

# Sync normal APU writes.
gmc = replace_once(gmc,
"""\tif (addr >= 0xFF10 && addr <= 0xFF3F)
\t{
\t\tif (m.apu) ApuWrite(*m.apu, addr, value, m.ppu && m.ppu->cgb,
\t\t                    m.timer ? m.timer->div_counter : 0, m.double_speed);
\t\treturn;
\t}
""",
"""\tif (addr >= 0xFF10 && addr <= 0xFF3F)
\t{
#ifdef IKCORE_SGB_LAZY_APU
\t\tMemFlushApu(m);
#endif
\t\tif (m.apu) ApuWrite(*m.apu, addr, value, m.ppu && m.ppu->cgb,
\t\t                    m.timer ? m.timer->div_counter : 0, m.double_speed);
\t\treturn;
\t}
""", "gb_memory.cpp APU write lazy sync");

GBMC.write_text(gmc, encoding="utf-8")

SGB = ROOT / "supersnes9x" / "sgb" / "sgb.cpp"
sg = SGB.read_text(encoding="utf-8-sig")

frame_flush_anchor = """\twhile (!impl_->ppu.frame_ready && safety > 0 && (impl_->ppu.lcdc & 0x80))
\t{
\t\tRunCycles(456);
\t\tsafety -= 456;
\t}

\t// Frame-locking pins GB time to the host's frame cadence, not the GB's
"""
frame_flush_new = """\twhile (!impl_->ppu.frame_ready && safety > 0 && (impl_->ppu.lcdc & 0x80))
\t{
\t\tRunCycles(456);
\t\tsafety -= 456;
\t}

#ifdef IKCORE_SGB_LAZY_APU
\t// Flush deferred audio to this exact frame boundary. Register accesses
\t// already force earlier synchronization when the game touches the APU.
\tMemFlushApu(impl_->mem);
#endif

\t// Frame-locking pins GB time to the host's frame cadence, not the GB's
"""
sg = replace_once(sg, frame_flush_anchor, frame_flush_new, "sgb.cpp frame-end lazy APU flush");

# Emit one diagnostic marker on init; no per-cycle timers.
init_anchor = """bool S9xSGBInit(void)
{
#ifdef IKCORE_SGB_PROFILE
\tSGB::IkSgbProfReset();
#endif
\treturn SGB::Instance().Init();
}
"""
init_new = """bool S9xSGBInit(void)
{
#ifdef IKCORE_SGB_PROFILE
\tSGB::IkSgbProfReset();
#endif
#ifdef IKCORE_SGB_LAZY_APU
\tS9xMessage(S9X_INFO, S9X_ROM_INFO,
\t           "IKOPT N2.5 lazy APU synchronization enabled.");
#endif
\treturn SGB::Instance().Init();
}
"""
sg = replace_once(sg, init_anchor, init_new, "sgb.cpp lazy APU marker");

SGB.write_text(sg, encoding="utf-8")

print("IK Core N2.5 lazy-APU optimization integration applied.")


# ---- N2.6 exact event-free fast paths
# These are not hardware cuts. They skip work only when the skipped path has
# no state transition to perform during this machine cycle.

GBMC = ROOT / "supersnes9x" / "sgb" / "gb_memory.cpp"
gmc = GBMC.read_text(encoding="utf-8-sig")

dma_old = """\tif (!stopped && tick_dma)
\t\tfor (int32_t t = 0; t < tcycles; t += 4)
\t\t\tDmaTickM(m);
"""
dma_new = """\t// OAM DMA is idle for almost the entire game. Calling DmaTickM once per
\t// machine cycle while neither setup nor transfer is active is a pure no-op.
\tif (!stopped && tick_dma && (m.dma_active || m.dma_setup > 0))
\t\tfor (int32_t t = 0; t < tcycles; t += 4)
\t\t\tDmaTickM(m);
"""
dma_count = gmc.count(dma_old)
if dma_count < 1:
    raise RuntimeError("gb_memory.cpp DMA idle anchor missing")
gmc = gmc.replace(dma_old, dma_new)
GBMC.write_text(gmc, encoding="utf-8")

GBT = ROOT / "supersnes9x" / "sgb" / "gb_timer.cpp"
gt = GBT.read_text(encoding="utf-8-sig")

timer_anchor = """void TimerStep(Timer &t, Memory &mem, int32_t tcycles)
{
\tfor (int32_t i = 0; i < tcycles; ++i)
"""
timer_new = """void TimerStep(Timer &t, Memory &mem, int32_t tcycles)
{
#ifdef IKCORE_GB_FAST_IDLE
\t// Cpu::Step normally advances one 4-T-cycle machine cycle at a time.
\t// If this interval contains no TIMA falling edge, serial activity,
\t// delayed reload, or DIV-APU edge, TimerStep has exactly one observable
\t// effect: advancing DIV. Do that in O(1) instead of four per-dot loops.
\tif (tcycles > 0 && tcycles <= 4 &&
\t    !t.tima_overflow_pending && t.reload_delay == 0 &&
\t    t.reload_just == 0 && mem.serial_guard == 0 && mem.serial_bits == 0)
\t{
\t\tconst uint16_t old_div = t.div_counter;
\t\tconst uint16_t new_div =
\t\t\tstatic_cast<uint16_t>(old_div + static_cast<uint16_t>(tcycles));

\t\tbool timer_fall = false;
\t\tif (t.tac & 0x04)
\t\t{
\t\t\tconst uint8_t bit = TIMA_BIT[t.tac & 0x03];
\t\t\ttimer_fall = DivBit(old_div, bit) && !DivBit(new_div, bit);
\t\t}

\t\tbool apu_edge = false;
\t\tif (mem.apu)
\t\t{
\t\t\tconst uint8_t abit = mem.double_speed ? 13 : 12;
\t\t\tapu_edge = DivBit(old_div, abit) != DivBit(new_div, abit);
\t\t}

\t\tif (!timer_fall && !apu_edge)
\t\t{
\t\t\tt.div_counter = new_div;
\t\t\treturn;
\t\t}
\t}
#endif

\tfor (int32_t i = 0; i < tcycles; ++i)
"""
gt = replace_once(gt, timer_anchor, timer_new, "gb_timer.cpp event-free fast path")
GBT.write_text(gt, encoding="utf-8")

print("IK Core N2.6 exact idle fast paths applied.")


# ---- N2.7 exact PPU idle-mode batching
# HBlank/VBlank spend many dots doing only bookkeeping. Batch up to the
# current MemTick slice when no dot-visible edge, delayed IRQ, palette/WX
# pulse, output tail, line boundary, or LY=153 quirk can occur.

GBPPU = ROOT / "supersnes9x" / "sgb" / "gb_ppu.cpp"
gp = GBPPU.read_text(encoding="utf-8-sig")

ppu_anchor = """\t// Swallow the dots a CPU-driven LCD enable would have consumed before
\t// its first one (Emulator::Reset decides how many).
\twhile (p.boot_skew > 0 && tcycles > 0) { --p.boot_skew; --tcycles; }
\twhile (tcycles-- > 0)
\t\tExecPpuDot(p, mem);
}
"""

ppu_new = """\t// Swallow the dots a CPU-driven LCD enable would have consumed before
\t// its first one (Emulator::Reset decides how many).
\twhile (p.boot_skew > 0 && tcycles > 0) { --p.boot_skew; --tcycles; }

#ifdef IKCORE_PPU_IDLE_FAST
\t// The CPU advances the PPU in tiny machine-cycle slices. In settled
\t// HBlank/VBlank most dots have no work other than mode_clock++. Skip the
\t// per-dot switch only when every delayed/pipelined state is already quiet
\t// and this slice cannot reach an internal mode/line/LY153 event.
\tif (tcycles > 0 && tcycles <= 4 &&
\t    p.pal_glitch == 0 && p.stat_irq_delay == 0 &&
\t    p.vblank_irq_at == 0 && p.wx_write_cooldown == 0 &&
\t    p.lcdc_d4 == p.lcdc && p.lcdc_d3 == p.lcdc &&
\t    p.lcdc_d2 == p.lcdc && p.lcdc_shadow == p.lcdc &&
\t    p.wx_d4 == p.wx && p.wx_d3 == p.wx &&
\t    p.wx_d2 == p.wx && p.wx_d1 == p.wx)
\t{
\t\tif (p.mode == PpuMode::HBlank && p.om.done)
\t\t{
\t\t\tconst int32_t mode0_length =
\t\t\t\tMODE0_DOTS - 4 - p.mode3_sprite_stall + p.lcdon_pad;
\t\t\tif (p.mode_clock + tcycles < mode0_length)
\t\t\t{
\t\t\t\tp.mode_clock += tcycles;
\t\t\t\treturn;
\t\t\t}
\t\t}
\t\telse if (p.mode == PpuMode::VBlank)
\t\t{
\t\t\tconst bool ly153_edge =
\t\t\t\tp.ly == 153 && p.mode_clock < 4 &&
\t\t\t\tp.mode_clock + tcycles >= 4;
\t\t\tif (!ly153_edge && p.mode_clock + tcycles < LINE_DOTS)
\t\t\t{
\t\t\t\tp.mode_clock += tcycles;
\t\t\t\treturn;
\t\t\t}
\t\t}
\t}
#endif

\twhile (tcycles-- > 0)
\t\tExecPpuDot(p, mem);
}
"""

gp = replace_once(gp, ppu_anchor, ppu_new, "gb_ppu.cpp idle-mode batching")
GBPPU.write_text(gp, encoding="utf-8")

print("IK Core N2.7 exact PPU idle batching applied.")


# ---- N2.8 exact MBC5 / power-of-two ROM hot path
# KOF96 is a 1 MiB MBC5 cart. Preserve mapper behavior exactly while avoiding
# the generic multi-mapper decision tree and integer modulo on every ROM fetch.

GBMBC = ROOT / "supersnes9x" / "sgb" / "gb_mbc.cpp"
gm = GBMBC.read_text(encoding="utf-8-sig")

readrom_anchor = """inline uint32_t ReadRom(const std::vector<uint8_t> &rom, uint32_t offset)
{
\tif (rom.empty()) return 0xFF;
\treturn rom[offset % rom.size()];
}
"""
readrom_new = """inline uint32_t ReadRom(const std::vector<uint8_t> &rom, uint32_t offset)
{
\tif (rom.empty()) return 0xFF;
#ifdef IKCORE_MBC5_FAST
\t// Most licensed GB ROMs, including this 1 MiB KOF96 image, are a
\t// power-of-two size. For those carts x % size is exactly x & (size-1),
\t// avoiding ARM's integer-divide helper in the instruction-fetch path.
\tconst size_t n = rom.size();
\tif ((n & (n - 1)) == 0)
\t\treturn rom[static_cast<size_t>(offset) & (n - 1)];
#endif
\treturn rom[offset % rom.size()];
}
"""
gm = replace_once(gm, readrom_anchor, readrom_new, "gb_mbc.cpp power-of-two ROM fast path")

mbcread_anchor = """uint8_t MbcRead(MbcState &s, const std::vector<uint8_t> &rom, const std::vector<uint8_t> &sram, uint16_t addr, bool mbc1_multicart, MbcUnl *unl)
{
\tif (s.type == MbcType::MBC6)
\t\treturn Mbc6Read(s, rom, sram, addr);
"""
mbcread_new = """uint8_t MbcRead(MbcState &s, const std::vector<uint8_t> &rom, const std::vector<uint8_t> &sram, uint16_t addr, bool mbc1_multicart, MbcUnl *unl)
{
\tif (s.type == MbcType::MBC6)
\t\treturn Mbc6Read(s, rom, sram, addr);

#ifdef IKCORE_MBC5_FAST
\t// Exact fast path for ordinary MBC5. BBD/Hitek/Sintax/etc. use distinct
\t// MbcType values and therefore stay on the full generic path below.
\t// Mbc5MultiBank preserves the 23-in-1 outer mask/base behavior.
\tif (s.type == MbcType::MBC5)
\t{
\t\tif (addr < 0x4000)
\t\t{
\t\t\tconst uint32_t bank = Mbc5MultiBank(s, 0);
\t\t\treturn ReadRom(rom, bank * 0x4000u + addr);
\t\t}
\t\tif (addr < 0x8000)
\t\t{
\t\t\tconst uint32_t bank = Mbc5MultiBank(s, s.rom_bank);
\t\t\treturn ReadRom(rom, bank * 0x4000u + (addr - 0x4000u));
\t\t}
\t\tif (addr >= 0xA000 && addr < 0xC000)
\t\t{
\t\t\tconst uint32_t bank = s.ram_bank & 0x0F;
\t\t\treturn ReadSram(sram, bank * 0x2000u + (addr - 0xA000u));
\t\t}
\t\treturn 0xFF;
\t}
#endif
"""
gm = replace_once(gm, mbcread_anchor, mbcread_new, "gb_mbc.cpp MBC5 exact hot path")
GBMBC.write_text(gm, encoding="utf-8")

print("IK Core N2.8 exact MBC5/ROM hot path applied.")


# ---- N2.9 exact Mode-3 sprite lookup masks
# The original dot pipeline linearly scans up to 10 (or 40 with the host
# override) sprite hits several times per Mode-3 dot. The scanline hit list
# is already immutable after mode 2, so precompute exact raw-X masks once per
# line and replace the repeated linear searches with bit operations.

GBPH = ROOT / "supersnes9x" / "sgb" / "gb_ppu.h"
gh = GBPH.read_text(encoding="utf-8-sig")

sprite_field_anchor = """\tSpriteHit sprites[40];
\tuint8_t   sprite_count    = 0;
\tbool      window_active   = false;   // window engaged on this LY
"""
sprite_field_new = """\tSpriteHit sprites[40];
\tuint8_t   sprite_count    = 0;
#ifdef IKCORE_PPU_SPRITE_MASKS
\t// Transient per-scanline lookup tables. Bit N corresponds exactly to
\t// sprites[N] in OAM-scan order. Rebuilt at every mode 2 -> 3 boundary.
\tuint64_t  sprite_x_mask[256] = {0};
\tuint64_t  sprite_before_mask[256] = {0};
#endif
\tbool      window_active   = false;   // window engaged on this LY
"""
gh = replace_once(gh, sprite_field_anchor, sprite_field_new,
                  "gb_ppu.h sprite lookup masks")
GBPH.write_text(gh, encoding="utf-8")

GBPPU = ROOT / "supersnes9x" / "sgb" / "gb_ppu.cpp"
gp = GBPPU.read_text(encoding="utf-8-sig")

eval_anchor = """\tp.sprite_count = 0;
\tfor (int i = 0; i < 40 && p.sprite_count < limit; ++i)
"""
eval_new = """\tp.sprite_count = 0;
#ifdef IKCORE_PPU_SPRITE_MASKS
\tstd::memset(p.sprite_x_mask, 0, sizeof p.sprite_x_mask);
\tstd::memset(p.sprite_before_mask, 0, sizeof p.sprite_before_mask);
#endif
\tfor (int i = 0; i < 40 && p.sprite_count < limit; ++i)
"""
gp = replace_once(gp, eval_anchor, eval_new, "gb_ppu.cpp sprite-mask reset")

eval_tail_anchor = """\t// The list stays in OAM-scan order: the FIFO's fetch order gives DMG
\t// X-priority and OAM-index priority naturally (first fetch wins the
\t// opaque FIFO slots).
}
"""
eval_tail_new = """#ifdef IKCORE_PPU_SPRITE_MASKS
\tfor (uint8_t i = 0; i < p.sprite_count; ++i)
\t{
\t\tconst uint8_t raw = static_cast<uint8_t>(p.sprites[i].x + 8);
\t\tp.sprite_x_mask[raw] |= (1ull << i);
\t}
\tuint64_t before = 0;
\tfor (int x = 0; x < 256; ++x)
\t{
\t\tp.sprite_before_mask[x] = before;
\t\tbefore |= p.sprite_x_mask[x];
\t}
#endif

\t// The list stays in OAM-scan order: the FIFO's fetch order gives DMG
\t// X-priority and OAM-index priority naturally (first fetch wins the
\t// opaque FIFO slots).
}
"""
gp = replace_once(gp, eval_tail_anchor, eval_tail_new,
                  "gb_ppu.cpp sprite-mask build")

discard_anchor = """void SpriteDiscardPassed(const Ppu &p, PixelMachine &m, uint8_t x_match)
{
\tfor (uint8_t i = 0; i < p.sprite_count; ++i)
\t{
\t\tif (m.sprite_used_mask & (1ull << i)) continue;
\t\tconst uint8_t raw = static_cast<uint8_t>(p.sprites[i].x + 8);
\t\tif (raw < x_match) m.sprite_used_mask |= 1ull << i;
\t}
}
"""
discard_new = """void SpriteDiscardPassed(const Ppu &p, PixelMachine &m, uint8_t x_match)
{
#ifdef IKCORE_PPU_SPRITE_MASKS
\tm.sprite_used_mask |= p.sprite_before_mask[x_match];
#else
\tfor (uint8_t i = 0; i < p.sprite_count; ++i)
\t{
\t\tif (m.sprite_used_mask & (1ull << i)) continue;
\t\tconst uint8_t raw = static_cast<uint8_t>(p.sprites[i].x + 8);
\t\tif (raw < x_match) m.sprite_used_mask |= 1ull << i;
\t}
#endif
}
"""
gp = replace_once(gp, discard_anchor, discard_new,
                  "gb_ppu.cpp discard sprite mask")

match_anchor = """int SpriteMatchAt(const Ppu &p, const PixelMachine &m, uint8_t x_match)
{
\tfor (uint8_t i = 0; i < p.sprite_count; ++i)
\t{
\t\tif (m.sprite_used_mask & (1ull << i)) continue;
\t\tif (static_cast<uint8_t>(p.sprites[i].x + 8) == x_match) return i;
\t}
\treturn -1;
}
"""
match_new = """int SpriteMatchAt(const Ppu &p, const PixelMachine &m, uint8_t x_match)
{
#ifdef IKCORE_PPU_SPRITE_MASKS
\tconst uint64_t avail = p.sprite_x_mask[x_match] & ~m.sprite_used_mask;
\tif (!avail) return -1;
\treturn static_cast<int>(__builtin_ctzll(avail));
#else
\tfor (uint8_t i = 0; i < p.sprite_count; ++i)
\t{
\t\tif (m.sprite_used_mask & (1ull << i)) continue;
\t\tif (static_cast<uint8_t>(p.sprites[i].x + 8) == x_match) return i;
\t}
\treturn -1;
#endif
}
"""
gp = replace_once(gp, match_anchor, match_new,
                  "gb_ppu.cpp exact sprite match mask")

raw0_anchor = """bool SpritePendingAtRaw0(const Ppu &p, const PixelMachine &m)
{
\tfor (uint8_t i = 0; i < p.sprite_count; ++i)
\t{
\t\tif (m.sprite_used_mask & (1ull << i)) continue;
\t\tif (static_cast<uint8_t>(p.sprites[i].x + 8) == 0) return true;
\t}
\treturn false;
}
"""
raw0_new = """bool SpritePendingAtRaw0(const Ppu &p, const PixelMachine &m)
{
#ifdef IKCORE_PPU_SPRITE_MASKS
\treturn (p.sprite_x_mask[0] & ~m.sprite_used_mask) != 0;
#else
\tfor (uint8_t i = 0; i < p.sprite_count; ++i)
\t{
\t\tif (m.sprite_used_mask & (1ull << i)) continue;
\t\tif (static_cast<uint8_t>(p.sprites[i].x + 8) == 0) return true;
\t}
\treturn false;
#endif
}
"""
gp = replace_once(gp, raw0_anchor, raw0_new,
                  "gb_ppu.cpp raw-X0 sprite mask")

GBPPU.write_text(gp, encoding="utf-8")
print("IK Core N2.9 exact Mode-3 sprite masks applied.")


# ---- N2.10 fixed default timing knobs for the single-core NES Mini runtime
# gb_knob.h intentionally uses function-local statics so generic multi-core
# test runners can set ACID_* environment overrides safely. The NES Mini
# runtime never sets those overrides and runs one core instance. Compile the
# exact tuned defaults as constants so hot PPU paths do not execute C++ local
# static guard checks on every dot. This changes configurability, not the
# default timing values used by the emulator.

GBKNOB = ROOT / "supersnes9x" / "sgb" / "gb_knob.h"
gk = GBKNOB.read_text(encoding="utf-8-sig")

knob_anchor = """inline int AcidKnob(const char *name, int def)
{
\tconst char *e = getenv(name);
\treturn e ? atoi(e) : def;
}
"""
knob_new = """#ifdef IKCORE_FIXED_ACID_KNOBS
// Dedicated single-core NES Mini build: no ACID_* environment overrides are
// used. Expanding to the exact default lets the compiler constant-fold the
// per-dot tuning checks while preserving the tuned default behavior.
#define AcidKnob(name, def) (def)
#else
inline int AcidKnob(const char *name, int def)
{
\tconst char *e = getenv(name);
\treturn e ? atoi(e) : def;
}
#endif
"""
gk = replace_once(gk, knob_anchor, knob_new, "gb_knob.h fixed-default fast path")
GBKNOB.write_text(gk, encoding="utf-8")

print("IK Core N2.10 fixed default timing knobs applied.")


# ---- N3.1 full-BIOS GB sync hot path
# Full SGB mode synchronizes GB time after every 65816 opcode and before ICD2
# accesses. Most of those tiny deltas are smaller than the SM83 instruction
# overshoot already carried in run_target. The generic RunCycles() still did
# all per-call setup and tail checks even when no GB instruction could run.
# Keep the identical persistent target and CPU-step ordering, but return early
# on those zero-work sync slices when no deferred side effect is pending.

SGBH = ROOT / "supersnes9x" / "sgb" / "sgb.h"
sh = SGBH.read_text(encoding="utf-8-sig")
decl_anchor = """\t// Advance by N T-cycles. Used when snes9x drives the master clock directly.
\tvoid RunCycles(int32_t tcycles);
"""
decl_new = """\t// Advance by N T-cycles. Used when snes9x drives the master clock directly.
\tvoid RunCycles(int32_t tcycles);
#ifdef IKCORE_SGB_FULL_FASTSYNC
\t// Full-SGB BIOS hot path. Semantics match RunCycles' persistent target,
\t// but zero-work opcode sync slices skip invariant setup/tail work.
\tvoid RunSyncCycles(int32_t tcycles);
#endif
"""
sh = replace_once(sh, decl_anchor, decl_new, "sgb.h N3.1 RunSyncCycles declaration")
SGBH.write_text(sh, encoding="utf-8")

SGBCPP = ROOT / "supersnes9x" / "sgb" / "sgb.cpp"
sc = SGBCPP.read_text(encoding="utf-8-sig")

insert_anchor = """const FrameBuffer &Emulator::GetFrameBuffer() const { return impl_->fb; }
"""
fast_body = r'''
#ifdef IKCORE_SGB_FULL_FASTSYNC
void Emulator::RunSyncCycles(int32_t tcycles)
{
	if (!impl_->has_rom || tcycles <= 0) return;

	// Preserve RunCycles' absolute-credit semantics exactly. A prior SM83
	// instruction may already have overshot this target by several T-cycles.
	const int64_t target_t = impl_->run_target + tcycles;
	impl_->run_target = target_t;

	// This is the common full-BIOS case: SNES advanced a tiny slice but GB is
	// already caught up because of instruction overshoot. The old path still
	// recomputed mode/APU state and tested all tails for every such call.
	const bool no_gb_step = impl_->ppu.t_cycles >= target_t;
	const bool pending_mmm01 = impl_->cart.mbc.mmm01_just_locked;
	const bool pending_border =
		impl_->border_capture.stage != Impl::BorderCapture::Idle &&
		impl_->ppu.frame_ready;
	const bool needs_sgbc_tail = impl_->sgbc && impl_->ppu.cgb;
	if (no_gb_step && !pending_mmm01 && !pending_border && !needs_sgbc_tail)
		return;

	// Same setup as RunCycles, executed only when GB work (or a deferred tail)
	// actually exists.
	impl_->apu.suppress_nrx2_glitch = impl_->SuppressNrxGlitches();
	impl_->ppu.cgb = impl_->CgbActive();
	impl_->ppu.dmg_compat = impl_->ppu.cgb && impl_->dmg_compat_cgb &&
		(!impl_->mem.boot_rom_enabled || (impl_->mem.key0 & 0x04));
	impl_->ppu.hold_present_on_enable = !impl_->BiosMode() &&
		(impl_->cgb_mode || impl_->run_mode == RunMode::DMG);

	if (impl_->cart.mbc.mmm01_just_locked)
	{
		impl_->cart.mbc.mmm01_just_locked = false;
		uint8_t pal01[16], pal23[16], attr_blk[16];
		BuildSgbDefaultPalettePackets(pal01, pal23);
		BuildResetAttrBlkPacket(attr_blk);
		if (impl_->boot_rom_loaded)
		{
			IcdPushQueue(impl_->icd2, pal01);
			IcdPushQueue(impl_->icd2, pal23);
			IcdPushQueue(impl_->icd2, attr_blk);
		}
		else
		{
			OnSgbCommandInternal(0x00, &pal01[1],    14);
			OnSgbCommandInternal(0x01, &pal23[1],    14);
			OnSgbCommandInternal(0x04, &attr_blk[1], 14);
		}
	}

	while (impl_->ppu.t_cycles < target_t)
	{
		const bool was_boot = impl_->mem.boot_rom_enabled;
		impl_->cpu.Step(impl_->mem);

		if (was_boot && !impl_->mem.boot_rom_enabled &&
		    !impl_->boot_handoff_captured)
		{
			if (impl_->sgbc && impl_->cgb_mode)
				impl_->SgbcHandoff();
			impl_->boot_handoff_captured = true;
			impl_->boot_handoff_regs     = impl_->cpu.State().r;
		}
	}

	// Preserve the same post-step tails as generic RunCycles. These are rare
	// in normal SGB1 gameplay but correctness matters for SGB borders/SGBC.
	if (impl_->sgbc && impl_->ppu.cgb)
	{
		const uint8_t ly = impl_->ppu.ly;
		if (ly < GB_SCREEN_HEIGHT && impl_->ppu.bgp == 0 &&
		    impl_->ppu.obp0 == 0 && impl_->ppu.obp1 == 0)
			impl_->cgb_blank_run = true;
		if (ly >= GB_SCREEN_HEIGHT && impl_->cgb_overlay_ly < GB_SCREEN_HEIGHT)
		{
			std::memcpy(impl_->cgb_overlay_fb, impl_->ppu.color_fb,
			            sizeof impl_->cgb_overlay_fb);
			impl_->cgb_overlay_valid = true;
			impl_->cgb_overlay_bgp   = impl_->ppu.bgp;
			impl_->cgb_overlay_lcdc  = impl_->ppu.lcdc;
			impl_->cgb_overlay_obp0  = impl_->ppu.obp0;
			impl_->cgb_overlay_obp1  = impl_->ppu.obp1;
			impl_->cgb_overlay_blank_any = impl_->cgb_blank_run;
			impl_->cgb_blank_run = false;
		}
		impl_->cgb_overlay_ly = ly;
	}

	if (impl_->border_capture.stage != Impl::BorderCapture::Idle &&
	    impl_->ppu.frame_ready)
	{
		if (impl_->border_capture.skip)
		{
			--impl_->border_capture.skip;
			impl_->ppu.frame_ready = false;
			return;
		}
		uint8_t decoded[4096];
		DecodeBorderCapture((impl_->sgbc && impl_->ppu.cgb) ? impl_->sgbc_trn.Frame()
		                                                    : impl_->ppu.raw_framebuffer, decoded);
		const uint8_t cmd =
			(impl_->border_capture.stage == Impl::BorderCapture::ChrTrn)
				? static_cast<uint8_t>(0x13)
				: static_cast<uint8_t>(0x14);
		++g_sgb_dbg.cap_fired;
		SgbHandleCommand(impl_->sgb_state, cmd,
		                 impl_->border_capture.pkt, 16,
		                 decoded, impl_->ppu.framebuffer);
		++impl_->border_plane;
		if (cmd == 0x14) ++impl_->border_pct;
		impl_->border_capture.stage = Impl::BorderCapture::Idle;
	}
}
#endif

'''
sc = replace_once(sc, insert_anchor, fast_body + insert_anchor,
                  "sgb.cpp N3.1 RunSyncCycles body")

old1 = """\t\t\tSGB::Instance().RunCycles(gb_cycles);
"""
new1 = """#ifdef IKCORE_SGB_FULL_FASTSYNC
\t\t\tSGB::Instance().RunSyncCycles(gb_cycles);
#else
\t\t\tSGB::Instance().RunCycles(gb_cycles);
#endif
"""
# There are two instances (SGB1 and SGB2/DMG); replace both deliberately.
count = sc.count(old1)
if count != 2:
    raise SystemExit(f"sgb.cpp N3.1 TickSnes callsites: expected 2, found {count}")
sc = sc.replace(old1, new1)

SGBCPP.write_text(sc, encoding="utf-8")
print("IK Core N3.1 full-BIOS fast sync path applied.")


# ---- N3.2 remove redundant per-opcode GB sync
# The pinned cpuexec.cpp currently contains BOTH:
#   (1) an end-of-every-65816-opcode GB sync, and
#   (2) a scanline-end GB sync explicitly documented as the replacement for
#       that old per-opcode hook, with exact ICD2-access syncs in getset.h.
# Running both defeats the intended batching and is extremely expensive on A7.
# N3.2 keeps exact catch-up before ICD2 reads/writes and at every scanline end,
# but suppresses only the redundant opcode-tail call.

CPUX = ROOT / "supersnes9x" / "cpuexec.cpp"
cx = CPUX.read_text(encoding="utf-8-sig")
op_sync = """\t\tif (Settings.SGB_BIOSModeActive && S9xSGBBIOSGBIsReleased())
\t\t\tS9xSGBSyncToSnesCycle(CPU.Cycles);
\t}

\t// P2 — in BIOS mode the GB core is held in reset until the BIOS
"""
op_sync_new = """#ifndef IKCORE_SGB_SCANLINE_SYNC
\t\tif (Settings.SGB_BIOSModeActive && S9xSGBBIOSGBIsReleased())
\t\t\tS9xSGBSyncToSnesCycle(CPU.Cycles);
#endif
\t}

\t// P2 — in BIOS mode the GB core is held in reset until the BIOS
"""
cx = replace_once(cx, op_sync, op_sync_new,
                  "cpuexec N3.2 suppress redundant per-opcode SGB sync")

# The scanline replacement must exist; fail CI rather than silently building
# a configuration without guaranteed forward progress.
scan_guard = """// Per-scanline GB sync in BIOS-released mode. Replaces the
"""
if scan_guard not in cx:
    raise SystemExit("cpuexec.cpp: N3.2 scanline-sync replacement marker missing")

CPUX.write_text(cx, encoding="utf-8")
print("IK Core N3.2 scanline/ICD2 SGB synchronization applied.")


# ---- A7 OPT 1/5: fixed-profile specialization (N2.10 philosophy)
# This build is exclusively the authentic SGB1 BIOS path used by SGBPACK:
# NTSC SGB1, DMG-side GB execution, no SA1/SuperFX/NSS/SFCBox/VoiceKun.
# We keep all SGB-visible timing/state, but turn invariants into compile-time
# facts so GCC/LTO can delete generic branches from the hottest loops.

CPUX = ROOT / "supersnes9x" / "cpuexec.cpp"
cx = CPUX.read_text(encoding="utf-8-sig")

# Full SGBPACK never uses the BIOS-less Settings.SuperGameBoy path.
direct_start = """\t// Super Game Boy mode — run the GB core for one frame and return.
\t// The 65816 loop below is bypassed entirely; snes9x's frontends
\t// call S9xMainLoop once per frame, so this satisfies the contract.
\tif (Settings.SuperGameBoy)
\t{
"""
direct_start_new = """\t// Super Game Boy mode — run the GB core for one frame and return.
\t// The 65816 loop below is bypassed entirely; snes9x's frontends
\t// call S9xMainLoop once per frame, so this satisfies the contract.
#ifndef IKCORE_SGB_FIXED_PROFILE
\tif (Settings.SuperGameBoy)
\t{
"""
cx = replace_once(cx, direct_start, direct_start_new,
                  "cpuexec fixed profile direct-path open")

direct_end = """\t\tCPU.Flags |= SCAN_KEYS_FLAG;
\t\treturn;
\t}

\t#define CHECK_FOR_IRQ_CHANGE() \\
"""
direct_end_new = """\t\tCPU.Flags |= SCAN_KEYS_FLAG;
\t\treturn;
\t}
#endif

\t#define CHECK_FOR_IRQ_CHANGE() \\
"""
cx = replace_once(cx, direct_end, direct_end_new,
                  "cpuexec fixed profile direct-path close")

# Compile out unrelated cartridge/supervisor hardware from the per-opcode loop.
cx = replace_once(cx,
"""\t\tif (Settings.SFCBox)
\t\t{
""",
"""#ifndef IKCORE_SGB_FIXED_PROFILE
\t\tif (Settings.SFCBox)
\t\t{
""",
"cpuexec fixed profile SFCBox open")
cx = replace_once(cx,
"""\t\t}

\t\tif (Settings.NSS)
\t\t{
""",
"""\t\t}
#endif

#ifndef IKCORE_SGB_FIXED_PROFILE
\t\tif (Settings.NSS)
\t\t{
""",
"cpuexec fixed profile SFCBox close/NSS open")
cx = replace_once(cx,
"""\t\t}

\t\tif (CPU.NMIPending)
""",
"""\t\t}
#endif

\t\tif (CPU.NMIPending)
""",
"cpuexec fixed profile NSS close")

cx = replace_once(cx,
"""\t\t\t// Voicer-kun: the game names a CD track, starts it, or ends the voice.
\t\t\tif (Settings.VoiceKun)
\t\t\t{
""",
"""\t\t\t// Voicer-kun: the game names a CD track, starts it, or ends the voice.
#ifndef IKCORE_SGB_FIXED_PROFILE
\t\t\tif (Settings.VoiceKun)
\t\t\t{
""",
"cpuexec fixed profile VoiceKun open")
cx = replace_once(cx,
"""\t\t\t}

\t\t\tuint8\t\t\t\tOp;
""",
"""\t\t\t}
#endif

\t\t\tuint8\t\t\t\tOp;
""",
"cpuexec fixed profile VoiceKun close")

cx = replace_once(cx,
"""\t\tif (Settings.SA1)
\t\t\tS9xSA1MainLoop();

\t\t// Per-SNES-opcode GB sync""",
"""#ifndef IKCORE_SGB_FIXED_PROFILE
\t\tif (Settings.SA1)
\t\t\tS9xSA1MainLoop();
#endif

\t\t// Per-SNES-opcode GB sync""",
"cpuexec fixed profile SA1 per opcode")

# The full SGBPACK build enters S9xMainLoop only with BIOS mode active.
# Replace read-only Settings checks with a compile-time true expression.
marker = '#include "voicekun.h"\n'
macro = '''#include "voicekun.h"

#ifdef IKCORE_SGB_FIXED_PROFILE
#define IKCORE_SGB_BIOS_ACTIVE true
#else
#define IKCORE_SGB_BIOS_ACTIVE Settings.SGB_BIOSModeActive
#endif
'''
cx = replace_once(cx, marker, macro, "cpuexec fixed profile BIOS macro")
cx = cx.replace("Settings.SGB_BIOSModeActive", "IKCORE_SGB_BIOS_ACTIVE")
# Restore the macro's fallback after the global replacement.
cx = cx.replace("#define IKCORE_SGB_BIOS_ACTIVE IKCORE_SGB_BIOS_ACTIVE",
                "#define IKCORE_SGB_BIOS_ACTIVE Settings.SGB_BIOSModeActive")

# Scanline-only generic coprocessor/device hooks are impossible for the SGB ROM.
cx = replace_once(cx,
"""\t\t\tif (Settings.SuperFX)
\t\t\t{
\t\t\t\tif (!SuperFX.oneLineDone)
\t\t\t\t\tS9xSuperFXExec();
\t\t\t\tSuperFX.oneLineDone = FALSE;
\t\t\t}
""",
"""#ifndef IKCORE_SGB_FIXED_PROFILE
\t\t\tif (Settings.SuperFX)
\t\t\t{
\t\t\t\tif (!SuperFX.oneLineDone)
\t\t\t\t\tS9xSuperFXExec();
\t\t\t\tSuperFX.oneLineDone = FALSE;
\t\t\t}
#endif
""",
"cpuexec fixed profile SuperFX")

for label, block in [
("SFCBox scanline", """\t\t\tif (Settings.SFCBox)
\t\t\t\tS9xSFCBoxEndScanline();
"""),
("NSS scanline", """\t\t\tif (Settings.NSS)
\t\t\t\tS9xNSSEndScanline();
"""),
("SuperDisc scanline", """\t\t\tif (Settings.SuperDisc)
\t\t\t\tS9xSuperDiscEndScanline();
"""),
("RP2040 scanline", """\t\t\tif (Settings.RP2040Cart)
\t\t\t\tS9xRP2040CartEndScanline();
"""),
("SA1 scanline", """\t\t\tif (Settings.SA1)
\t\t\t\tSA1.Cycles -= Timings.H_Max * 3;
""")
]:
    cx = replace_once(cx, block,
                      "#ifndef IKCORE_SGB_FIXED_PROFILE\n" + block + "#endif\n",
                      "cpuexec fixed profile " + label)

CPUX.write_text(cx, encoding="utf-8")

# GB PPU: in an authentic SGB1 BIOS session the GB side is DMG, never CGB.
# Replace the runtime p.cgb tests by a compile-time false predicate only for
# this specialized build. Generic builds retain the original behavior.
PPUCPP = ROOT / "supersnes9x" / "sgb" / "gb_ppu.cpp"
pc = PPUCPP.read_text(encoding="utf-8-sig")
ns = "namespace SGB {\n"
pred = """namespace SGB {

#ifdef IKCORE_SGB_FIXED_PROFILE
#define IKCORE_PPU_CGB(p) false
#else
#define IKCORE_PPU_CGB(p) ((p).cgb)
#endif
"""
pc = replace_once(pc, ns, pred, "gb_ppu fixed profile predicate")
cgb_reads = pc.count("p.cgb")
if cgb_reads < 30:
    raise SystemExit(f"gb_ppu.cpp: expected many p.cgb hot-path reads, found {cgb_reads}")
# Do not touch members whose names merely begin with cgb (e.g.
# p.cgb_pal_written). Protect that one state field before replacing the
# standalone mode predicate.
pc = pc.replace("p.cgb_pal_written", "__IKCORE_CGB_PAL_WRITTEN__")
pc = pc.replace("p.cgb", "IKCORE_PPU_CGB(p)")
pc = pc.replace("__IKCORE_CGB_PAL_WRITTEN__", "p.cgb_pal_written")
PPUCPP.write_text(pc, encoding="utf-8")

# SGB clock bridge: SGBPACK's authentic target is SGB1, whose hardware ratio
# is exactly SNES master / 5. Remove the per-sync run-mode dispatch and 64-bit
# division while keeping the same remainder accumulator and RunSyncCycles path.
SGBCPP = ROOT / "supersnes9x" / "sgb" / "sgb.cpp"
sc = SGBCPP.read_text(encoding="utf-8-sig")
tick_old = """\tint32_t gb_cycles;
\tconst SGB::RunMode mode = SGB::Instance().GetRunMode();
\tif (mode == SGB::RunMode::SGB)
\t{
\t\t// Exact: subtracting gb_cycles*5 reverses accum/5 with no remainder.
\t\tg_snes_cycle_accum += snes_master_cycles;
\t\tgb_cycles = g_snes_cycle_accum / 5;
\t\tif (gb_cycles > 0)
\t\t{
\t\t\tg_snes_cycle_accum -= gb_cycles * 5;
#ifdef IKCORE_SGB_FULL_FASTSYNC
\t\t\tSGB::Instance().RunSyncCycles(gb_cycles);
#else
\t\t\tSGB::Instance().RunCycles(gb_cycles);
#endif
\t\t}
\t}
\telse
\t{
"""
tick_new = """\tint32_t gb_cycles;
#ifdef IKCORE_SGB_FIXED_PROFILE
\t// Authentic SGB1: fixed ICD2 clock ratio, no runtime mode dispatch.
\tg_snes_cycle_accum += snes_master_cycles;
\tgb_cycles = g_snes_cycle_accum / 5;
\tif (gb_cycles > 0)
\t{
\t\tg_snes_cycle_accum -= gb_cycles * 5;
#ifdef IKCORE_SGB_FULL_FASTSYNC
\t\tSGB::Instance().RunSyncCycles(gb_cycles);
#else
\t\tSGB::Instance().RunCycles(gb_cycles);
#endif
\t}
#else
\tconst SGB::RunMode mode = SGB::Instance().GetRunMode();
\tif (mode == SGB::RunMode::SGB)
\t{
\t\t// Exact: subtracting gb_cycles*5 reverses accum/5 with no remainder.
\t\tg_snes_cycle_accum += snes_master_cycles;
\t\tgb_cycles = g_snes_cycle_accum / 5;
\t\tif (gb_cycles > 0)
\t\t{
\t\t\tg_snes_cycle_accum -= gb_cycles * 5;
#ifdef IKCORE_SGB_FULL_FASTSYNC
\t\t\tSGB::Instance().RunSyncCycles(gb_cycles);
#else
\t\t\tSGB::Instance().RunCycles(gb_cycles);
#endif
\t\t}
\t}
\telse
\t{
"""
sc = replace_once(sc, tick_old, tick_new, "sgb fixed profile SGB1 clock path")

tick_close = """\t\t}
\t}
}

void S9xSGBResetSyncAnchor"""
tick_close_new = """\t\t}
\t}
#endif
}

void S9xSGBResetSyncAnchor"""
sc = replace_once(sc, tick_close, tick_close_new, "sgb fixed profile SGB1 clock close")

# RunSyncCycles is called at every scanline/ICD2 catch-up. BIOS SGB1 implies
# DMG PPU and no SGBC overlay, so make those invariant setup values explicit.
sync_setup = """\timpl_->apu.suppress_nrx2_glitch = impl_->SuppressNrxGlitches();
\timpl_->ppu.cgb = impl_->CgbActive();
\timpl_->ppu.dmg_compat = impl_->ppu.cgb && impl_->dmg_compat_cgb &&
\t\t(!impl_->mem.boot_rom_enabled || (impl_->mem.key0 & 0x04));
\timpl_->ppu.hold_present_on_enable = !impl_->BiosMode() &&
\t\t(impl_->cgb_mode || impl_->run_mode == RunMode::DMG);
"""
sync_setup_new = """\timpl_->apu.suppress_nrx2_glitch = impl_->SuppressNrxGlitches();
#ifdef IKCORE_SGB_FIXED_PROFILE
\timpl_->ppu.cgb = false;
\timpl_->ppu.dmg_compat = false;
\timpl_->ppu.hold_present_on_enable = false;
#else
\timpl_->ppu.cgb = impl_->CgbActive();
\timpl_->ppu.dmg_compat = impl_->ppu.cgb && impl_->dmg_compat_cgb &&
\t\t(!impl_->mem.boot_rom_enabled || (impl_->mem.key0 & 0x04));
\timpl_->ppu.hold_present_on_enable = !impl_->BiosMode() &&
\t\t(impl_->cgb_mode || impl_->run_mode == RunMode::DMG);
#endif
"""
sc = replace_once(sc, sync_setup, sync_setup_new, "sgb fixed profile RunSync setup")

SGBCPP.write_text(sc, encoding="utf-8")
print("IK Core A7 OPT 1/5 fixed-profile specialization applied.")


# ---- A7 OPT 2/5: SM83 CPU + memory hot-path specialization
# Preserve every machine cycle and bus-visible access. This pass only removes
# runtime checks that are invariant in the dedicated SGB1/DMG/MBC5 build.

CPUCPP = ROOT / "supersnes9x" / "sgb" / "gb_cpu.cpp"
cc = CPUCPP.read_text(encoding="utf-8-sig")
trace_old = """\tif (g_trace_hook) g_trace_hook(pc_at_fetch, op, state_);

\tDispatch(state_, mem, op);
"""
trace_new = """#ifndef IKCORE_SGB_CPU_MEM_FAST
\tif (g_trace_hook) g_trace_hook(pc_at_fetch, op, state_);
#endif

\tDispatch(state_, mem, op);
"""
cc = replace_once(cc, trace_old, trace_new, "gb_cpu fixed runtime trace hook")
CPUCPP.write_text(cc, encoding="utf-8")

OPSH = ROOT / "supersnes9x" / "sgb" / "gb_ops.h"
oh = OPSH.read_text(encoding="utf-8-sig")
ops_ns = """namespace SGB {

// Dispatch a single non-CB opcode."""
ops_pred = """namespace SGB {

#ifdef IKCORE_SGB_CPU_MEM_FAST
// Authentic SGB1 uses DMG hardware: these CGB-only branches are impossible.
#define IKCORE_MEM_CGB_HW(mem) false
#else
#define IKCORE_MEM_CGB_HW(mem) ((mem).cgb_hw)
#endif

// Dispatch a single non-CB opcode."""
oh = replace_once(oh, ops_ns, ops_pred, "gb_ops fixed DMG predicate")
# Only the hot inline bus helpers use this member here. Protect no similarly
# named members exist in this header.
oh = oh.replace("mem.cgb_hw", "IKCORE_MEM_CGB_HW(mem)")
OPSH.write_text(oh, encoding="utf-8")

GBMC = ROOT / "supersnes9x" / "sgb" / "gb_memory.cpp"
mc = GBMC.read_text(encoding="utf-8-sig")

# Exact fixed-profile MemTick. Late-write reconstruction above this anchor is
# left untouched. SGB1 is single-speed DMG hardware; timer/PPU/APU/cart
# pointers are wired unconditionally by Emulator::Reset/StateLoad. MBC5 has
# no RTC, so the generic MbcTickRtc call has no state to advance.
stop_anchor = """\t// STOP halts the oscillator: DIV/TIMA and OAM DMA freeze; the APU
\t// freezes too on DMG (it keeps running on CGB hardware).
\tconst bool stopped = m.cpu && m.cpu->stopped;

"""
stop_new = """\t// STOP halts the oscillator: DIV/TIMA and OAM DMA freeze; the APU
\t// freezes too on DMG (it keeps running on CGB hardware).
\tconst bool stopped = m.cpu && m.cpu->stopped;

#ifdef IKCORE_SGB_CPU_MEM_FAST
\t// Dedicated SGB1/DMG path. Same machine-cycle ordering as the generic
\t// code below, without pointer/double-speed/RTC branches that cannot vary.
\tif (!stopped)
\t\tTimerStep(*m.timer, m, tcycles);

\tif (!stopped && tick_dma && (m.dma_active || m.dma_setup > 0))
\t\tfor (int32_t t = 0; t < tcycles; t += 4)
\t\t\tDmaTickM(m);

\tif (tcycles > 0)
\t{
\t\tPpuStep(*m.ppu, m, tcycles);
\t\tif (!stopped) ApuStep(*m.apu, tcycles);
\t}
\treturn;
#endif

"""
mc = replace_once(mc, stop_anchor, stop_new, "gb_memory fixed MemTick path")

# The overwhelmingly common instruction-fetch path after boot: ordinary MBC5
# ROM read, no OAM DMA bus conflict. Keep the generic path for boot and DMA,
# where the special bus/overlay semantics remain observable.
read_anchor = """uint8_t MemRead(Memory &m, uint16_t addr)
{
\t// OAM DMA bus conflict:"""
read_new = """uint8_t MemRead(Memory &m, uint16_t addr)
{
#ifdef IKCORE_SGB_CPU_MEM_FAST
\tif (addr < 0x8000 && !m.boot_rom_enabled && !m.dma_active)
\t\treturn MbcRead(m.cart->mbc, m.cart->rom, m.cart->sram, addr,
\t\t               m.cart->mbc1_multicart, &m.cart->unl);
#endif
\t// OAM DMA bus conflict:"""
mc = replace_once(mc, read_anchor, read_new, "gb_memory fixed ROM fetch path")

write_anchor = """void MemWrite(Memory &m, uint16_t addr, uint8_t value)
{
\t// OAM DMA bus conflict"""
write_new = """void MemWrite(Memory &m, uint16_t addr, uint8_t value)
{
#ifdef IKCORE_SGB_CPU_MEM_FAST
\t// Mapper-register writes are always accepted even during OAM DMA. The
\t// dedicated SGBPACK always has its MBC5 cart wired, so skip generic tests.
\tif (addr < 0x8000)
\t{
\t\tMbcWrite(*m.cart, addr, value);
\t\treturn;
\t}
#endif
\t// OAM DMA bus conflict"""
mc = replace_once(mc, write_anchor, write_new, "gb_memory fixed MBC write path")

GBMC.write_text(mc, encoding="utf-8")
print("IK Core A7 OPT 2/5 CPU/memory hot paths applied.")


# ---- A7 OPT 3/5: fast DMG timing skeleton
# Mode 3 intentionally runs two pixel machines: tm is a timing skeleton and
# om is the real pixel-output machine. On SGB1/DMG, tm does not need tile or
# sprite pixel *values* to determine timing; only FIFO occupancy, fetch phase,
# window/object state and bus-visible OAM latches affect its schedule.
# Keep om bit-for-bit on the original path. For tm, preserve every dot and
# state transition but skip pixel-value VRAM reads / FIFO array traffic.

GBPPU = ROOT / "supersnes9x" / "sgb" / "gb_ppu.cpp"
gp = GBPPU.read_text(encoding="utf-8-sig")

push_anchor = """\tconst bool flip = IKCORE_PPU_CGB(p) && (m.fetch_attr & 0x20);
\tfor (int i = 0; i < 8; ++i)
"""
push_new = """#ifdef IKCORE_SGB_TIMING_SKELETON_FAST
\tif (!m.emits)
\t{
\t\t// Timing skeleton: a successful BG push always contributes 8 FIFO
\t\t// slots. Pixel values/attributes are consumed only by the output
\t\t// machine and cannot affect DMG fetch timing.
\t\tm.bgf_count = 8;
\t\tm.fetch_stage = 0;
\t\tm.fetch_dot   = 0;
\t\treturn;
\t}
#endif
\tconst bool flip = IKCORE_PPU_CGB(p) && (m.fetch_attr & 0x20);
\tfor (int i = 0; i < 8; ++i)
"""
gp = replace_once(gp, push_anchor, push_new, "gb_ppu skeleton BG FIFO value bypass")

fetch_anchor = """void FetcherDot(Ppu &p, PixelMachine &m)
{
\tif (m.fetch_pause > 0)
\t{
\t\t--m.fetch_pause;
\t\treturn;
\t}
\tswitch (m.fetch_stage)
"""
fetch_new = """void FetcherDot(Ppu &p, PixelMachine &m)
{
\tif (m.fetch_pause > 0)
\t{
\t\t--m.fetch_pause;
\t\treturn;
\t}
#ifdef IKCORE_SGB_TIMING_SKELETON_FAST
\tif (!m.emits)
\t{
\t\t// DMG timing-only fetcher. The six T1/T2 dots and push retry are
\t\t// identical to the full fetcher, but tile/data bytes are irrelevant
\t\t// to tm: only phase, FIFO occupancy and window tile count drive time.
\t\tswitch (m.fetch_stage)
\t\t{
\t\tcase 0:
\t\t\tif (m.fetch_dot == 0) { m.fetch_dot = 1; return; }
\t\t\tm.fetch_dot = 0; m.fetch_stage = 1; return;
\t\tcase 1:
\t\t\tif (m.fetch_dot == 0) { m.fetch_dot = 1; return; }
\t\t\tm.fetch_dot = 0; m.fetch_stage = 2; return;
\t\tcase 2:
\t\t\tif (m.fetch_dot == 0) { m.fetch_dot = 1; return; }
\t\t\tm.fetch_dot = 0;
\t\t\tif (m.fetch_is_window)
\t\t\t\tm.fetch_tile_x = static_cast<uint8_t>((m.fetch_tile_x + 1) & 31);
\t\t\tm.fetch_stage = 3;
\t\t\tBgPushAttempt(p, m);
\t\t\treturn;
\t\tdefault:
\t\t\tBgPushAttempt(p, m);
\t\t\treturn;
\t\t}
\t}
#endif
\tswitch (m.fetch_stage)
"""
gp = replace_once(gp, fetch_anchor, fetch_new, "gb_ppu timing-only fetcher")

overlay_anchor = """void ObjOverlayRow(Ppu &p, PixelMachine &m, uint8_t lo, uint8_t hi, uint8_t flags, uint8_t oi)
{
\tm.objf_uflow = 0;
\twhile (m.objf_size < 8)
"""
overlay_new = """void ObjOverlayRow(Ppu &p, PixelMachine &m, uint8_t lo, uint8_t hi, uint8_t flags, uint8_t oi)
{
\tm.objf_uflow = 0;
#ifdef IKCORE_SGB_TIMING_SKELETON_FAST
\tif (!m.emits)
\t{
\t\t// tm only needs FIFO occupancy for pop/rewind bookkeeping. Sprite
\t\t// color, palette and owner data never feed the DMG timing machine.
\t\tm.objf_size = 8;
\t\treturn;
\t}
#endif
\twhile (m.objf_size < 8)
"""
gp = replace_once(gp, overlay_anchor, overlay_new, "gb_ppu skeleton OBJ FIFO value bypass")

obj3_anchor = """\tcase 3:
\t\tm.obj_lo = p.vram[ObjLineAddr(p, m, h.y)];
\t\tm.obj_fetch_state = 2;
\t\treturn;
\tcase 2: m.obj_fetch_state = 1; return;
\tdefault:
\t\tm.obj_hi = p.vram[static_cast<uint16_t>(ObjLineAddr(p, m, h.y) + 1)];
\t\tm.during_obj = false;
\t\tm.obj_fetch_state = 0;
\t\tm.obj_overlay = true;
\t\treturn;
"""
obj3_new = """\tcase 3:
#ifdef IKCORE_SGB_TIMING_SKELETON_FAST
\t\tif (m.emits)
#endif
\t\t\tm.obj_lo = p.vram[ObjLineAddr(p, m, h.y)];
\t\tm.obj_fetch_state = 2;
\t\treturn;
\tcase 2: m.obj_fetch_state = 1; return;
\tdefault:
#ifdef IKCORE_SGB_TIMING_SKELETON_FAST
\t\tif (m.emits)
#endif
\t\t\tm.obj_hi = p.vram[static_cast<uint16_t>(ObjLineAddr(p, m, h.y) + 1)];
\t\tm.during_obj = false;
\t\tm.obj_fetch_state = 0;
\t\tm.obj_overlay = true;
\t\treturn;
"""
gp = replace_once(gp, obj3_anchor, obj3_new, "gb_ppu skeleton OBJ VRAM bypass")

render_anchor = """\tuint8_t c, at;
\tbool win;
\tif (m.bgf_insert)
\t{
\t\tm.bgf_insert = false;
\t\tc = 0; at = 0; win = m.fetch_is_window;
\t}
\telse
\t{
\t\tc   = m.bgf_color[m.bgf_head];
\t\tat  = m.bgf_attr[m.bgf_head];
\t\twin = m.bgf_layer[m.bgf_head] != 0;
\t\tm.bgf_head = static_cast<uint8_t>((m.bgf_head + 1) & 7);
\t\t--m.bgf_count;
\t}
\t// The OBJ FIFO pops in step with every BG pop — dropped pixels consume
\t// sprite pixels too (left-edge clipping falls out of this).
\tuint8_t obj_c = 0, obj_fl = 0;
\tif (m.objf_size > 0)
\t{
\t\tobj_c  = m.objf_color[m.objf_head];
\t\tobj_fl = m.objf_flags[m.objf_head];
\t\tm.objf_head = static_cast<uint8_t>((m.objf_head + 1) & 7);
\t\t--m.objf_size;
\t}
\telse
\t{
\t\t++m.objf_uflow;
\t}
"""
render_new = """\tuint8_t c = 0, at = 0;
\tbool win = m.fetch_is_window;
\tif (m.bgf_insert)
\t{
\t\tm.bgf_insert = false;
\t}
\telse
\t{
#ifdef IKCORE_SGB_TIMING_SKELETON_FAST
\t\tif (m.emits)
\t\t{
#endif
\t\t\tc   = m.bgf_color[m.bgf_head];
\t\t\tat  = m.bgf_attr[m.bgf_head];
\t\t\twin = m.bgf_layer[m.bgf_head] != 0;
#ifdef IKCORE_SGB_TIMING_SKELETON_FAST
\t\t}
#endif
\t\tm.bgf_head = static_cast<uint8_t>((m.bgf_head + 1) & 7);
\t\t--m.bgf_count;
\t}
\t// The OBJ FIFO pops in step with every BG pop — dropped pixels consume
\t// sprite pixels too (left-edge clipping falls out of this).
\tuint8_t obj_c = 0, obj_fl = 0;
\tif (m.objf_size > 0)
\t{
#ifdef IKCORE_SGB_TIMING_SKELETON_FAST
\t\tif (m.emits)
\t\t{
#endif
\t\t\tobj_c  = m.objf_color[m.objf_head];
\t\t\tobj_fl = m.objf_flags[m.objf_head];
#ifdef IKCORE_SGB_TIMING_SKELETON_FAST
\t\t}
#endif
\t\tm.objf_head = static_cast<uint8_t>((m.objf_head + 1) & 7);
\t\t--m.objf_size;
\t}
\telse
\t{
\t\t++m.objf_uflow;
\t}
"""
gp = replace_once(gp, render_anchor, render_new, "gb_ppu skeleton RenderDot data bypass")

emit_anchor = """\tEmitPixel(p, m, c, at, win, obj_c, obj_fl);
\t++m.pos;
"""
emit_new = """#ifdef IKCORE_SGB_TIMING_SKELETON_FAST
\tif (m.emits)
#endif
\t\tEmitPixel(p, m, c, at, win, obj_c, obj_fl);
\t++m.pos;
"""
gp = replace_once(gp, emit_anchor, emit_new, "gb_ppu skeleton EmitPixel bypass")

# Dedicated SGBPACK never enables the host "no sprite limit" hack. Fixing the
# hardware limit removes one branch at every mode-2->3 transition and makes
# the s>=10 instant-fetch path unreachable in this build.
limit_anchor = """\tconst int limit = p.no_sprite_limit
\t\t? static_cast<int>(sizeof p.sprites / sizeof p.sprites[0])
\t\t: GB_OAM_SCAN_LIMIT;
"""
limit_new = """#ifdef IKCORE_SGB_TIMING_SKELETON_FAST
\tconst int limit = GB_OAM_SCAN_LIMIT;
#else
\tconst int limit = p.no_sprite_limit
\t\t? static_cast<int>(sizeof p.sprites / sizeof p.sprites[0])
\t\t: GB_OAM_SCAN_LIMIT;
#endif
"""
gp = replace_once(gp, limit_anchor, limit_new, "gb_ppu fixed hardware sprite limit")

GBPPU.write_text(gp, encoding="utf-8")
print("IK Core A7 OPT 3/5 fast DMG timing skeleton applied.")


# ---- PERF1: direct SGB performance PPU
# Dedicated NES Mini path. Keep our own SM83/SGB command engine and full
# 256x224 SGB compositor, but replace the expensive dual FIFO/dot Mode-3
# renderer with a single scanline renderer plus hardware-style timing events.
# This is intentionally a performance architecture (mGBA-like event granularity),
# not the full SameBoy-style per-dot validation path.

GBPPU = ROOT / "supersnes9x" / "sgb" / "gb_ppu.cpp"
gp = GBPPU.read_text(encoding="utf-8-sig")

# The legacy renderer already resolves DMG BG/window/sprites directly from
# VRAM/OAM and is otherwise unused by the current FIFO pipeline. Use it only
# for PERF1 and only on the DMG/SGB1 path.
win_activate = """\t\tif (!p.window_active && x == trigger_x &&
\t\t\t(p.lcdc & 0x20) != 0 &&
\t\t\tp.wy_triggered)
\t\t{
\t\t\tp.window_active  = true;
\t\t\tp.window_start_x = static_cast<int16_t>(x);
\t\t}
"""
win_activate_new = """\t\tif (!p.window_active && x == trigger_x &&
\t\t\t(p.lcdc & 0x20) != 0 &&
\t\t\tp.wy_triggered)
\t\t{
#ifdef IKCORE_SGB_PERF_PPU
\t\t\t// The full FIFO path increments the output machine's internal
\t\t\t// window line when activation commits. The scanline renderer
\t\t\t// performs the same state transition here.
\t\t\t++p.om.window_line;
#endif
\t\t\tp.window_active  = true;
\t\t\tp.window_start_x = static_cast<int16_t>(x);
\t\t}
"""
gp = replace_once(gp, win_activate, win_activate_new,
                  "gb_ppu PERF1 window-line activation")

transfer_old = """\tcase PpuMode::Transfer:
\t{
// Both machines advance on every mode-3 dot. The skeleton decides when
// mode 3 ends; the output machine trails it by entry_delay dots and keeps
// running into HBlank until it has produced all 160 pixels.
\t\tif (!p.tm.done && Mode3Dot(p, p.tm, mem))
\t\t{
\t\t\tp.tm.done = true;
\t\t\ttransitioned = Mode3Exit(p, p.tm, mem);
\t\t}
\t\tif (!p.om.done && Mode3Dot(p, p.om, mem))
\t\t{
\t\t\tp.om.done = true;
\t\t\tMode3WxCarry(p, p.om);
\t\t\tMode3OutputExit(p, p.om);
\t\t}
\t\tp.draw_x        = p.om.lcd_x;
\t\tp.window_active = p.om.fetch_is_window || p.om.win_carry;
\t\tbreak;
\t}
"""
transfer_new = """\tcase PpuMode::Transfer:
\t{
#ifdef IKCORE_SGB_PERF_PPU
\t\t// NES Mini performance path: preserve mode timing/STAT/OAM locks but
\t\t// do not execute two full FIFO machines for every dot.  DMG mode-3
\t\t// length is approximated from the documented base plus SCX fine
\t\t// alignment and the hardware 10-sprite fetch budget.
\t\tconst int32_t perf_sprites =
\t\t\tp.sprite_count < GB_OAM_SCAN_LIMIT ? p.sprite_count : GB_OAM_SCAN_LIMIT;
\t\tconst int32_t perf_stall = (p.scx & 7) + perf_sprites * SPRITE_STALL_DOTS;
\t\tconst int32_t perf_len = MODE3_DOTS + perf_stall;

\t\tif (p.mode_clock >= perf_len)
\t\t{
\t\t\t// Resolve the visible line once. The direct renderer samples the
\t\t\t// line's latched registers and current VRAM/OAM; this is the same
\t\t\t// high-level strategy used by fast handheld emulators and avoids
\t\t\t// tens of thousands of FIFO state-machine iterations per frame.
\t\t\tp.window_active = p.om.win_carry;
\t\t\tfor (int x = 0; x < GB_SCREEN_WIDTH; ++x)
\t\t\t{
\t\t\t\tp.draw_x = static_cast<int16_t>(x);
\t\t\t\tRenderPixel(p);
\t\t\t}
\t\t\tp.draw_x = GB_SCREEN_WIDTH;
\t\t\tp.om.lcd_x = GB_SCREEN_WIDTH;
\t\t\tp.tm.done = true;
\t\t\tp.om.done = true;
\t\t\tMode3WxCarry(p, p.om);
\t\t\tFinalizeScanline(p);
\t\t\ttransitioned = Mode3Exit(p, p.tm, mem);
\t\t}
#else
// Both machines advance on every mode-3 dot. The skeleton decides when
// mode 3 ends; the output machine trails it by entry_delay dots and keeps
// running into HBlank until it has produced all 160 pixels.
\t\tif (!p.tm.done && Mode3Dot(p, p.tm, mem))
\t\t{
\t\t\tp.tm.done = true;
\t\t\ttransitioned = Mode3Exit(p, p.tm, mem);
\t\t}
\t\tif (!p.om.done && Mode3Dot(p, p.om, mem))
\t\t{
\t\t\tp.om.done = true;
\t\t\tMode3WxCarry(p, p.om);
\t\t\tMode3OutputExit(p, p.om);
\t\t}
\t\tp.draw_x        = p.om.lcd_x;
\t\tp.window_active = p.om.fetch_is_window || p.om.win_carry;
#endif
\t\tbreak;
\t}
"""
gp = replace_once(gp, transfer_old, transfer_new,
                  "gb_ppu PERF1 event-driven Mode3")

GBPPU.write_text(gp, encoding="utf-8")
print("IK Core PERF1 direct/event-driven SGB PPU applied.")


# ---- FINAL PERF2: hybrid SGB audio + atomic border handoff
# Bootstrap the real SGB BIOS only long enough to initialize the SNES N-SPC
# engine, then switch the SAME GB/SGB instance to the fast direct path while
# keeping SPC700/DSP state alive. No mGBA is used.
#
# During direct play:
#   * GB APU runs exact (workflow intentionally drops IKCORE_SGB_LAZY_APU)
#   * SPC700/DSP is advanced audio-only once per host frame
#   * SGB SOUND writes map directly to the N-SPC CPU ports
#   * SOU_TRN captures the 4 KiB transfer and copies packets to APU RAM
#   * border visibility commits atomically on PCT_TRN (no visual fade)

# ---- APU public helpers -----------------------------------------------------
APUH = ROOT / "supersnes9x" / "apu" / "apu.h"
ah = APUH.read_text(encoding="utf-8-sig")
apu_decl_anchor = """void   S9xSpcSyncToConsumption(void);
void   S9xSpcSyncReset(void);
"""
apu_decl_new = """void   S9xSpcSyncToConsumption(void);
void   S9xSpcSyncReset(void);

#ifdef IKCORE_SGB_HYBRID_AUDIO
// Ik Core PERF2: preserve the SGB BIOS-initialized N-SPC engine after the
// SNES CPU/PPU are retired. These functions touch only SPC700/DSP state.
void  S9xSGBPerfAudioEnable(void);
bool8 S9xSGBPerfAudioActive(void);
void  S9xSGBPerfAudioFrame(void);
void  S9xSGBPerfSoundCommand(const uint8 *data, uint32 len);
void  S9xSGBPerfSouTrn(const uint8 *data_4k);
#endif
"""
ah = replace_once(ah, apu_decl_anchor, apu_decl_new,
                  "apu.h PERF2 helpers")
APUH.write_text(ah, encoding="utf-8")

APUCPP = ROOT / "supersnes9x" / "apu" / "apu.cpp"
ac = APUCPP.read_text(encoding="utf-8-sig")

# Hybrid state lives beside the SPC resampler internals so it can advance
# SMP/DSP without going through stale SNES CPU cycle counters.
apu_ns_anchor = """namespace spc {
static apu_callback callback = NULL;
"""
apu_ns_new = """namespace spc {
static apu_callback callback = NULL;
"""
ac = replace_once(ac, apu_ns_anchor, apu_ns_new, "apu PERF2 namespace anchor")

# Insert implementation immediately before S9xAPUTimingSetSpeedup.
apu_impl_anchor = """void S9xAPUTimingSetSpeedup(int ticks)
{
"""
apu_impl = r'''#ifdef IKCORE_SGB_HYBRID_AUDIO
namespace {
static bool   ik_perf_audio_active = false;
static double ik_perf_smp_frac = 0.0;
static uint32 ik_perf_sound_commands = 0;
static int ik_sfx_spc_cycles_advanced = 0;
static uint32 ik_perf_sou_trn_commands = 0;

// Native SPC700 clock / SGB NTSC frame cadence. Keep fractional cycles so the
// audio-only engine neither drifts nor needs the retired SNES CPU.Cycles.
constexpr double IK_PERF_SMP_PER_FRAME =
    1024000.0 / 60.09881389744051;
}

void S9xSGBPerfAudioEnable(void)
{
    ik_perf_audio_active = true;
    ik_perf_smp_frac = 0.0;
    // Throw away splash-era buffered PCM, NOT SPC RAM/DSP/SMP state.
    // The N-SPC program and its sample tables remain exactly as the BIOS
    // initialized them.
    S9xClearSamples();
    S9xSpcSyncReset();
}

bool8 S9xSGBPerfAudioActive(void)
{
    return ik_perf_audio_active ? TRUE : FALSE;
}

void S9xSGBPerfAudioFrame(void)
{
    if (!ik_perf_audio_active) return;

    ik_perf_smp_frac += IK_PERF_SMP_PER_FRAME;
    const int cycles = (int)ik_perf_smp_frac;
    ik_perf_smp_frac -= (double)cycles;
    if (cycles <= 0) return;

    // SFX port handshakes already consumed part of this exact SPC frame.
    // Do not change frame clocks or the #117 music resampler rate.
    const int remaining = cycles > ik_sfx_spc_cycles_advanced
                        ? cycles - ik_sfx_spc_cycles_advanced : 0;
    ik_sfx_spc_cycles_advanced = 0;
    if (remaining) {
        SNES::smp.clock -= remaining;
        SNES::smp.enter();
    }
    SNES::dsp.synchronize();
}

// SGB SOUND packet bytes are defined as:
//   [1] SFX A = SNES/APU port 1
//   [2] SFX B = SNES/APU port 2
//   [3] pitch/volume attributes = port 3
//   [4] music score code = port 0
// Port 0 is the command/score trigger, so publish parameters first and port 0
// last to make the four-byte update atomic from the N-SPC driver's view.
void S9xSGBPerfSoundCommand(const uint8 *data, uint32 len)
{
    if (!ik_perf_audio_active || !data || len < 5) return;
    SNES::cpu.port_write(1, data[1]);
    SNES::cpu.port_write(2, data[2]);
    SNES::cpu.port_write(3, data[3]);
    SNES::cpu.port_write(0, data[4]);
    ++ik_perf_sound_commands;
}

// SOU_TRN is a 4 KiB stream of little-endian transfer packets.
// N > 0: [size][dest][N bytes]
// N = 0: [0000][jump address].  The real BIOS uploads through the SPC IPL;
// here the already-running N-SPC engine receives the identical APU-RAM bytes
// directly. This avoids re-running the SNES CPU/PPU just to copy sound data.
void S9xSGBPerfSouTrn(const uint8 *src)
{
    if (!ik_perf_audio_active || !src) return;

    size_t off = 0;
    while (off + 4 <= 4096)
    {
        const uint16 n = (uint16)(src[off] | (src[off + 1] << 8));
        const uint16 dst = (uint16)(src[off + 2] | (src[off + 3] << 8));
        off += 4;

        if (n == 0)
        {
            // Jump packet: safely restart/enter the uploaded N-SPC program.
            SNES::smp.regs.pc = dst;
            SNES::smp.opcode_number = 0;
            SNES::smp.opcode_cycle = 0;
            break;
        }

        if (off + n > 4096) break;
        size_t copy_n = n;
        if ((size_t)dst + copy_n > 0x10000)
            copy_n = 0x10000 - (size_t)dst;
        if (copy_n)
            memcpy(SNES::smp.apuram + dst, src + off, copy_n);
        off += n;
    }
    ++ik_perf_sou_trn_commands;
}
#endif

void S9xAPUTimingSetSpeedup(int ticks)
{
'''
ac = replace_once(ac, apu_impl_anchor, apu_impl,
                  "apu.cpp PERF2 audio-only engine")

# Mix SPC underneath GB in direct PERF2 just like released BIOS mode.
mix_gate_old = """    const bool mix_spc_under_gb = Settings.SGB_BIOSModeActive &&
                                   S9xSGBBIOSGBIsReleased();
"""
mix_gate_new = """    const bool mix_spc_under_gb =
        (Settings.SGB_BIOSModeActive && S9xSGBBIOSGBIsReleased())
#ifdef IKCORE_SGB_HYBRID_AUDIO
        || S9xSGBPerfAudioActive()
#endif
        ;
"""
ac = replace_once(ac, mix_gate_old, mix_gate_new,
                  "apu.cpp PERF2 mix gate")

mix2_gate_old = """    const bool sgb_bios_mix = Settings.SGB_BIOSModeActive && S9xSGBBIOSGBIsReleased();
"""
mix2_gate_new = """    const bool sgb_bios_mix =
        (Settings.SGB_BIOSModeActive && S9xSGBBIOSGBIsReleased())
#ifdef IKCORE_SGB_HYBRID_AUDIO
        || S9xSGBPerfAudioActive()
#endif
        ;
"""
ac = replace_once(ac, mix2_gate_old, mix2_gate_new,
                  "apu.cpp PERF2 overlay gate")
APUCPP.write_text(ac, encoding="utf-8")

# ---- Libretro SPC rate controller follows hybrid audio too -----------------
LR = ROOT / "supersnes9x" / "libretro" / "libretro.cpp"
lc = LR.read_text(encoding="utf-8-sig")
sync_old = """    if (Settings.SGB_BIOSModeActive && S9xSGBBIOSGBIsReleased())
        S9xSpcSyncToConsumption();
    else
        S9xSpcSyncReset();
"""
sync_new = """    if ((Settings.SGB_BIOSModeActive && S9xSGBBIOSGBIsReleased())
#ifdef IKCORE_SGB_HYBRID_AUDIO
        || S9xSGBPerfAudioActive()
#endif
       )
        S9xSpcSyncToConsumption();
    else
        S9xSpcSyncReset();
"""
lc = replace_once(lc, sync_old, sync_new,
                  "libretro PERF2 SPC rate sync")
LR.write_text(lc, encoding="utf-8")

# ---- SGB state: SOU_TRN capture + atomic border ----------------------------
SGBH = ROOT / "supersnes9x" / "sgb" / "sgb.h"
sh = SGBH.read_text(encoding="utf-8-sig")
sgb_method_anchor = """\tbool    IsBootSetupComplete() const;
\tbool    IsScreenVisible() const;
\tuint32_t GetPacketCount() const;
"""
sgb_method_new = """\tbool    IsBootSetupComplete() const;
\tbool    IsScreenVisible() const;
\tuint32_t GetPacketCount() const;
#ifdef IKCORE_SGB_HYBRID_AUDIO
\tvoid    EnterPerfDirectMode();
#endif
"""
sh = replace_once(sh, sgb_method_anchor, sgb_method_new,
                  "sgb.h PERF2 enter-direct method")

sgb_c_anchor = """bool          S9xSGBScreenVisible (void);
"""
sgb_c_new = """bool          S9xSGBScreenVisible (void);
#ifdef IKCORE_SGB_HYBRID_AUDIO
void          S9xSGBEnterPerfDirectMode(void);
#endif
"""
sh = replace_once(sh, sgb_c_anchor, sgb_c_new,
                  "sgb.h PERF2 C facade")
SGBH.write_text(sh, encoding="utf-8")

SGBCPP = ROOT / "supersnes9x" / "sgb" / "sgb.cpp"
sc = SGBCPP.read_text(encoding="utf-8-sig")

# Need apu helper declarations in the SGB module.
sc = replace_once(sc, '#include "sgb.h"\n',
                  '#include "sgb.h"\n#ifdef IKCORE_SGB_HYBRID_AUDIO\n#include "../apu/apu.h"\n#endif\n',
                  "sgb.cpp PERF2 apu include")

# Extend Impl near the ordinary border-capture state.
impl_anchor = """\tSgbcTrnHold sgbc_trn;   // see sgbc.h; armed only under SGBC
"""
impl_new = """#ifdef IKCORE_SGB_HYBRID_AUDIO
\t// Direct-mode SOU_TRN uses the same 4 KiB LCD transfer mechanism as
\t// CHR_TRN/PCT_TRN. Capture one completed GB frame after the packet.
\tbool        perf_sou_capture = false;
\tuint8_t     perf_sou_skip = 0;

\t// Visible SGB border is committed only after PCT_TRN. CHR_TRN may update
\t// one tile plane at a time; exposing it immediately is what produced the
\t// half-drawn border seen in PERF1 transitions.
\tuint16_t    perf_stable_border[SGB_BORDER_W * SGB_BORDER_H] = {};
\tbool        perf_stable_border_valid = false;
#endif

\tSgbcTrnHold sgbc_trn;   // see sgbc.h; armed only under SGBC
"""
sc = replace_once(sc, impl_anchor, impl_new,
                  "sgb.cpp PERF2 Impl state")

# Reset hybrid capture/snapshot bookkeeping.
reset_anchor = """\timpl_->border_capture.stage = Impl::BorderCapture::Idle;
\timpl_->sgbc_trn.Reset();
"""
reset_new = """\timpl_->border_capture.stage = Impl::BorderCapture::Idle;
#ifdef IKCORE_SGB_HYBRID_AUDIO
\timpl_->perf_sou_capture = false;
\timpl_->perf_sou_skip = 0;
\timpl_->perf_stable_border_valid = false;
#endif
\timpl_->sgbc_trn.Reset();
"""
sc = replace_once(sc, reset_anchor, reset_new,
                  "sgb.cpp PERF2 reset state")

# SOUND + SOU_TRN command routing.
cmd_anchor = """\tif (cmd == 0x13 || cmd == 0x14)
\t{
"""
cmd_new = """#ifdef IKCORE_SGB_HYBRID_AUDIO
\tif (cmd == 0x08 && S9xSGBPerfAudioActive())
\t{
\t\t// Keep diagnostic/state bookkeeping and also drive the retained N-SPC
\t\t// engine directly.
\t\tSgbHandleCommand(impl_->sgb_state, cmd, data, len,
\t\t                 impl_->ppu.vram, impl_->ppu.framebuffer);
\t\tS9xSGBPerfSoundCommand(data, len);
\t\treturn;
\t}

\tif (cmd == 0x09 && S9xSGBPerfAudioActive())
\t{
\t\timpl_->perf_sou_capture = true;
\t\timpl_->perf_sou_skip = 1;
\t\timpl_->ppu.frame_ready = false;
\t\treturn;
\t}
#endif

\tif (cmd == 0x13 || cmd == 0x14)
\t{
"""
sc = replace_once(sc, cmd_anchor, cmd_new,
                  "sgb.cpp PERF2 SOUND/SOU_TRN routing")

# At frame completion, capture SOU_TRN and atomically commit PCT border.
tail_anchor = """\tif (impl_->border_capture.stage != Impl::BorderCapture::Idle &&
\t    impl_->ppu.frame_ready)
\t{
"""
tail_new = """#ifdef IKCORE_SGB_HYBRID_AUDIO
\tif (impl_->perf_sou_capture && impl_->ppu.frame_ready)
\t{
\t\tif (impl_->perf_sou_skip)
\t\t{
\t\t\t--impl_->perf_sou_skip;
\t\t}
\t\telse
\t\t{
\t\t\tuint8_t decoded_sou[4096];
\t\t\tDecodeBorderCapture(impl_->ppu.raw_framebuffer, decoded_sou);
\t\t\tS9xSGBPerfSouTrn(decoded_sou);
\t\t\timpl_->perf_sou_capture = false;
\t\t}
\t}
#endif

\tif (impl_->border_capture.stage != Impl::BorderCapture::Idle &&
\t    impl_->ppu.frame_ready)
\t{
"""
tail_scope = sc.find("void Emulator::RunCycles(int32_t tcycles)")
if tail_scope < 0:
    raise SystemExit("sgb.cpp PERF2: RunCycles scope not found")
tail_idx = sc.find(tail_anchor, tail_scope)
if tail_idx < 0:
    raise SystemExit("sgb.cpp PERF2: SOU capture tail not found in RunCycles")
sc = sc[:tail_idx] + tail_new + sc[tail_idx + len(tail_anchor):]

pct_commit_anchor = """\t\t++impl_->border_plane;
\t\tif (cmd == 0x14) ++impl_->border_pct;
\t\timpl_->border_capture.stage = Impl::BorderCapture::Idle;
"""
pct_commit_new = """\t\t++impl_->border_plane;
\t\tif (cmd == 0x14)
\t\t{
\t\t\t++impl_->border_pct;
#ifdef IKCORE_SGB_HYBRID_AUDIO
\t\t\t// PCT_TRN is the atomic presentation point: tile data and map/palette
\t\t\t// are now a coherent border.
\t\t\tSgbRenderBorder(impl_->sgb_state, impl_->perf_stable_border);
\t\t\timpl_->perf_stable_border_valid = true;
#endif
\t\t}
\t\timpl_->border_capture.stage = Impl::BorderCapture::Idle;
"""
pct_scope = sc.find("void Emulator::RunCycles(int32_t tcycles)")
pct_idx = sc.find(pct_commit_anchor, pct_scope)
if pct_idx < 0:
    raise SystemExit("sgb.cpp PERF2: atomic PCT commit not found in RunCycles")
sc = sc[:pct_idx] + pct_commit_new + sc[pct_idx + len(pct_commit_anchor):]

# Use stable border in direct compositor.
blit_anchor = """\tuint16_t *const staging = impl_->composite;
\tSgbRenderBorder(impl_->sgb_state, staging);
"""
blit_new = """\tuint16_t *const staging = impl_->composite;
#ifdef IKCORE_SGB_HYBRID_AUDIO
\tif (impl_->perf_stable_border_valid)
\t\tstd::memcpy(staging, impl_->perf_stable_border,
\t\t            sizeof impl_->perf_stable_border);
\telse
\t\tSgbRenderBorder(impl_->sgb_state, staging);
#else
\tSgbRenderBorder(impl_->sgb_state, staging);
#endif
"""
sc = replace_once(sc, blit_anchor, blit_new,
                  "sgb.cpp PERF2 stable border blit")

# Clean handoff helper. No reset: same GB CPU/PPU/APU/cart state continues.
handoff_anchor = """bool Emulator::IsScreenVisible() const
{
\treturn impl_->sgb_state.mask_mode == SGB_MASK_CANCEL;
}
"""
handoff_new = """bool Emulator::IsScreenVisible() const
{
\treturn impl_->sgb_state.mask_mode == SGB_MASK_CANCEL;
}

#ifdef IKCORE_SGB_HYBRID_AUDIO
void Emulator::EnterPerfDirectMode()
{
\timpl_->host_bios_mode = 0;
\timpl_->sgb_authentic = true;
\timpl_->force_model = 3;
\timpl_->joypad.sgb_active = false;
\timpl_->joypad.mlt_players = impl_->sgb_state.mlt_players;
\timpl_->joypad.mlt_index = impl_->sgb_state.mlt_current_player;
\timpl_->ppu.cgb = false;
\timpl_->ppu.dmg_compat = false;
\timpl_->ppu.hold_present_on_enable = false;

\t// If the game's PCT already landed while the BIOS was active, snapshot it
\t// before the first direct composite.
\tif (impl_->border_pct > 0)
\t{
\t\tSgbRenderBorder(impl_->sgb_state, impl_->perf_stable_border);
\t\timpl_->perf_stable_border_valid = true;
\t}
}
#endif
"""
sc = replace_once(sc, handoff_anchor, handoff_new,
                  "sgb.cpp PERF2 handoff method")

# C facade near the other boot-state helpers.
facade_anchor = """bool S9xSGBScreenVisible(void)
{
\treturn SGB::Instance().IsScreenVisible();
}
"""
facade_new = """bool S9xSGBScreenVisible(void)
{
\treturn SGB::Instance().IsScreenVisible();
}
#ifdef IKCORE_SGB_HYBRID_AUDIO
void S9xSGBEnterPerfDirectMode(void)
{
\tSGB::Instance().EnterPerfDirectMode();
}
#endif
"""
sc = replace_once(sc, facade_anchor, facade_new,
                  "sgb.cpp PERF2 handoff facade")
SGBCPP.write_text(sc, encoding="utf-8")

# ---- Loader: full BIOS bootstrap, then runtime switches to direct ----------
MMC = ROOT / "supersnes9x" / "memmap.cpp"
mc = MMC.read_text(encoding="utf-8-sig")

lite_anchor = """#ifdef SGBPACK_LITE
    // NES/SNES Classic fast path: use the dedicated GB/SGB engine directly
"""
lite_new = """#ifdef SGBPACK_LITE
#ifdef IKCORE_SGB_HYBRID_AUDIO
    // PERF2 starts through the real SGB BIOS so its N-SPC program, BRR sample
    // tables and DSP state are initialized exactly by the console software.
    // cpuexec switches to the direct GB/SGB engine after the cart finishes
    // its power-on SGB setup, preserving this APU state.
    S9xSGBSetForceModel(3);
    S9xSGBSetRunMode(mode);
    if (!S9xSGBLoadBootROMBytes(boot.data(), boot.size()))
    {
        S9xSGBDeinit();
        return -1;
    }
    if (!S9xSGBLoadROMBytes(gb.data(), gb.size(), pack_path))
    {
        S9xSGBDeinit();
        return -1;
    }
    S9xSGBPrepareBiosCart();
    S9xSGBSetAudioRate(Settings.SoundPlaybackRate);

    if (!LoadROMMem(sgb.data(), (uint32) sgb.size(), pack_path))
    {
        S9xSGBDeinit();
        return -1;
    }

    S9xDeleteCheats();
    Settings.SuperGameBoy       = FALSE;
    Settings.SGB_BIOSModeActive = TRUE;
    Settings.GameBoyRunMode     = mode;
    Settings.GBClockMultiplier  = 1.0f;
    S9xSGBSetRunMode(mode);
    S9xMessage(S9X_INFO, S9X_ROM_INFO,
               "IKCORE PERF2 hybrid: real SGB BIOS boot + retained SPC/DSP.");
#else
    // NES/SNES Classic fast path: use the dedicated GB/SGB engine directly
"""
mc = replace_once(mc, lite_anchor, lite_new,
                  "memmap PERF2 hybrid bootstrap")

lite_close_anchor = """    ROMFramesPerSecond          = 60;
#else
"""
lite_close_new = """    ROMFramesPerSecond          = 60;
#endif
#else
"""
# The first occurrence after our new hybrid section is the direct-lite close.
pos = mc.find("IKCORE PERF2 hybrid")
idx = mc.find(lite_close_anchor, pos)
if idx < 0:
    raise SystemExit("memmap PERF2 direct-lite close anchor not found")
mc = mc[:idx] + mc[idx:].replace(lite_close_anchor, lite_close_new, 1)
MMC.write_text(mc, encoding="utf-8")

# ---- CPU loop: switch after setup; advance retained SPC every direct frame --
CPU = ROOT / "supersnes9x" / "cpuexec.cpp"
cc = CPU.read_text(encoding="utf-8-sig")

main_anchor = """\t// Super Game Boy mode — run the GB core for one frame and return.
"""
main_new = """#ifdef IKCORE_SGB_HYBRID_AUDIO
\t// Once the real BIOS has initialized N-SPC and the cart has completed its
\t// SGB setup, retire only the SNES CPU/PPU. The same GB/SGB instance and
\t// live SPC700/DSP continue.
\tif (Settings.SGB_BIOSModeActive &&
\t    S9xSGBBIOSGBIsReleased() &&
\t    S9xSGBBootHandoffCaptured() &&
\t    S9xSGBBootSetupComplete() &&
\t    S9xSGBScreenVisible())
\t{
\t\tS9xSGBEnterPerfDirectMode();
\t\tS9xSGBPerfAudioEnable();
\t\tSettings.SGB_BIOSModeActive = FALSE;
\t\tSettings.SuperGameBoy = TRUE;
\t\tSettings.PAL = FALSE;
\t\tSettings.FrameTime = Settings.FrameTimeNTSC;
\t\tS9xMessage(S9X_INFO, S9X_ROM_INFO,
\t\t           "IKCORE PERF2 switch: direct GB/SGB + live SNES SPC/DSP.");
\t}
#endif

\t// Super Game Boy mode — run the GB core for one frame and return.
"""
cc = replace_once(cc, main_anchor, main_new,
                  "cpuexec PERF2 runtime switch")

run_anchor = """\t\tS9xSGBRunFrame();
\t\tif (!Settings.InRunAhead)
"""
run_new = """\t\tS9xSGBRunFrame();
#ifdef IKCORE_SGB_HYBRID_AUDIO
\t\tif (!Settings.InRunAhead && S9xSGBPerfAudioActive())
\t\t\tS9xSGBPerfAudioFrame();
#endif
\t\tif (!Settings.InRunAhead)
"""
cc = replace_once(cc, run_anchor, run_new,
                  "cpuexec PERF2 SPC frame step")
CPU.write_text(cc, encoding="utf-8")

# ---- PERF PPU: accurate during BIOS bootstrap and SGB transfer frames -------
# The event-driven path remains the gameplay default. While BIOS is active,
# keep the exact dual-FIFO path so initialization/transfer images are not
# corrupted before the handoff.
GBPPU = ROOT / "supersnes9x" / "sgb" / "gb_ppu.cpp"
gp = GBPPU.read_text(encoding="utf-8-sig")
gp = replace_once(gp, '#include "sgb.h"\n',
                  '#include "sgb.h"\n#ifdef IKCORE_SGB_HYBRID_AUDIO\n#include "../snes9x.h"\n#endif\n',
                  "gb_ppu PERF2 Settings include")

perf_branch_old = """#ifdef IKCORE_SGB_PERF_PPU
\t\t// NES Mini performance path: preserve mode timing/STAT/OAM locks but
"""
perf_branch_new = """#if defined(IKCORE_SGB_PERF_PPU)
\t\tif (!Settings.SGB_BIOSModeActive)
\t\t{
\t\t// NES Mini performance path: preserve mode timing/STAT/OAM locks but
"""
gp = replace_once(gp, perf_branch_old, perf_branch_new,
                  "gb_ppu PERF2 runtime fast open")

perf_else_old = """\t\t\ttransitioned = Mode3Exit(p, p.tm, mem);
\t\t}
#else
// Both machines advance on every mode-3 dot."""
perf_else_new = """\t\t\ttransitioned = Mode3Exit(p, p.tm, mem);
\t\t}
\t\t}
\t\telse
\t\t{
// Both machines advance on every mode-3 dot."""
gp = replace_once(gp, perf_else_old, perf_else_new,
                  "gb_ppu PERF2 runtime accurate else")

perf_end_old = """\t\tp.window_active = p.om.fetch_is_window || p.om.win_carry;
#endif
\t\tbreak;
"""
perf_end_new = """\t\tp.window_active = p.om.fetch_is_window || p.om.win_carry;
\t\t}
#else
// Non-PERF build: exact FIFO path.
\t\tif (!p.tm.done && Mode3Dot(p, p.tm, mem))
\t\t{
\t\t\tp.tm.done = true;
\t\t\ttransitioned = Mode3Exit(p, p.tm, mem);
\t\t}
\t\tif (!p.om.done && Mode3Dot(p, p.om, mem))
\t\t{
\t\t\tp.om.done = true;
\t\t\tMode3WxCarry(p, p.om);
\t\t\tMode3OutputExit(p, p.om);
\t\t}
\t\tp.draw_x        = p.om.lcd_x;
\t\tp.window_active = p.om.fetch_is_window || p.om.win_carry;
#endif
\t\tbreak;
"""
gp = replace_once(gp, perf_end_old, perf_end_new,
                  "gb_ppu PERF2 runtime fast close")
GBPPU.write_text(gp, encoding="utf-8")

print("IK Core PERF2 hybrid SNES audio + atomic border applied.")


# ---- PERF2 follow-up: exact GB PPU only while a transfer frame is captured --
# Gameplay remains event-driven. CHR_TRN/PCT_TRN/SOU_TRN capture frames use the
# exact FIFO path so transfer payloads are never decoded from a simplified line.

SGBH = ROOT / "supersnes9x" / "sgb" / "sgb.h"
sh = SGBH.read_text(encoding="utf-8-sig")
a = """\tvoid    EnterPerfDirectMode();
#endif
"""
b = """\tvoid    EnterPerfDirectMode();
\tbool    PerfNeedsAccuratePpu() const;
#endif
"""
sh = replace_once(sh, a, b, "sgb.h PERF2 accurate-transfer method")
a = """void          S9xSGBEnterPerfDirectMode(void);
#endif
"""
b = """void          S9xSGBEnterPerfDirectMode(void);
bool          S9xSGBPerfNeedsAccuratePpu(void);
#endif
"""
sh = replace_once(sh, a, b, "sgb.h PERF2 accurate-transfer facade")
SGBH.write_text(sh, encoding="utf-8")

SGBCPP = ROOT / "supersnes9x" / "sgb" / "sgb.cpp"
sc = SGBCPP.read_text(encoding="utf-8-sig")
a = """void Emulator::EnterPerfDirectMode()
{
"""
# Add method after EnterPerfDirectMode body using the closing marker nearby.
end = """\tif (impl_->border_pct > 0)
\t{
\t\tSgbRenderBorder(impl_->sgb_state, impl_->perf_stable_border);
\t\timpl_->perf_stable_border_valid = true;
\t}
}
#endif
"""
rep = """\tif (impl_->border_pct > 0)
\t{
\t\tSgbRenderBorder(impl_->sgb_state, impl_->perf_stable_border);
\t\timpl_->perf_stable_border_valid = true;
\t}
}

bool Emulator::PerfNeedsAccuratePpu() const
{
\treturn impl_->border_capture.stage != Impl::BorderCapture::Idle ||
\t       impl_->perf_sou_capture;
}
#endif
"""
sc = replace_once(sc, end, rep, "sgb.cpp PERF2 accurate-transfer method")
fac = """void S9xSGBEnterPerfDirectMode(void)
{
\tSGB::Instance().EnterPerfDirectMode();
}
#endif
"""
fac2 = """void S9xSGBEnterPerfDirectMode(void)
{
\tSGB::Instance().EnterPerfDirectMode();
}
bool S9xSGBPerfNeedsAccuratePpu(void)
{
\treturn SGB::Instance().PerfNeedsAccuratePpu();
}
#endif
"""
sc = replace_once(sc, fac, fac2, "sgb.cpp PERF2 accurate-transfer facade")
SGBCPP.write_text(sc, encoding="utf-8")

GBPPU = ROOT / "supersnes9x" / "sgb" / "gb_ppu.cpp"
gp = GBPPU.read_text(encoding="utf-8-sig")
a = """\t\tif (!Settings.SGB_BIOSModeActive)
\t\t{
\t\t// NES Mini performance path:"""
b = """\t\tif (!Settings.SGB_BIOSModeActive && !S9xSGBPerfNeedsAccuratePpu())
\t\t{
\t\t// NES Mini performance path:"""
gp = replace_once(gp, a, b, "gb_ppu PERF2 transfer fallback")
GBPPU.write_text(gp, encoding="utf-8")

print("IK Core PERF2 exact-transfer PPU fallback applied.")


# ---- PERF2 AUDIO AUDIT: bounded resampling and performance instrumentation --
# This intentionally does not claim perfect SNES audio or real-device FPS.
# It corrects a measurable source of pitch distortion: the former SGB BIOS
# PI controller was also running after the hybrid switch and could alter
# SPC production speed by up to +/-50% when the NES Mini couldn't keep up.
# Direct audio is now fixed-rate; any underflow remains visible in counters.
#
# It also keeps the proven PERF1 deferred GB APU machinery (flushed before
# GB APU register accesses and once per GB frame). The PERF2 workflow enables
# the already-existing IKCORE_SGB_LAZY_APU code, rather than handwaving away
# the 60->42 fps regression.

APUCPP = ROOT / "supersnes9x" / "apu" / "apu.cpp"
ac = APUCPP.read_text(encoding="utf-8-sig")
ac = replace_once(ac, '#include "apu.h"\n',
    '#include "apu.h"\n#ifdef IKCORE_SGB_HYBRID_AUDIO\n#include <chrono>\n#endif\n',
    "PERF2 audio audit chrono header")

audio_enable_old = """    S9xClearSamples();
    S9xSpcSyncReset();
}

bool8 S9xSGBPerfAudioActive(void)
"""
audio_enable_new = """    S9xClearSamples();
    S9xSpcSyncReset();
    // Fixed-rate SPC production after SNES CPU retirement. The normal
    // BIOS-only PI controller permits +/-50% pitch modulation, unsuitable
    // when the host is slow: changing frequency does not recover CPU time.
    S9xSpcResetDrc();
}

bool8 S9xSGBPerfAudioActive(void)
"""
ac = replace_once(ac, audio_enable_old, audio_enable_new,
                  "PERF2 fixed-rate audio activation")

audio_step_old = """void S9xSGBPerfAudioFrame(void)
{
    if (!ik_perf_audio_active) return;

    ik_perf_smp_frac += IK_PERF_SMP_PER_FRAME;
    const int cycles = (int)ik_perf_smp_frac;
    ik_perf_smp_frac -= (double)cycles;
    if (cycles <= 0) return;

    SNES::smp.clock -= cycles;
    SNES::smp.enter();
    SNES::dsp.synchronize();
}
"""
audio_step_new = """void S9xSGBPerfAudioFrame(void)
{
    if (!ik_perf_audio_active) return;

    ik_perf_smp_frac += IK_PERF_SMP_PER_FRAME;
    const int cycles = (int)ik_perf_smp_frac;
    ik_perf_smp_frac -= (double)cycles;
    if (cycles <= 0) return;

    // This measures the isolated SPC700/DSP cost on the ARM device.
    // Only hardware data can tell whether it fits the ~2ms PERF1 margin.
    using IkClock = std::chrono::steady_clock;
    static uint64 frames = 0;
    static double accumulated_us = 0.0;
    static double peak_us = 0.0;
    const auto start = IkClock::now();

    SNES::smp.clock -= cycles;
    SNES::smp.enter();
    SNES::dsp.synchronize();

    const auto stop = IkClock::now();
    const double elapsed_us =
        std::chrono::duration<double, std::micro>(stop - start).count();
    accumulated_us += elapsed_us;
    if (elapsed_us > peak_us) peak_us = elapsed_us;
    if (++frames % 300 == 0)
    {
        char report[192];
        snprintf(report, sizeof report,
                 "IKCORE SPC PROFILE: frames=%llu avg=%.3fms peak=%.3fms "
                 "SOUND=%u SOU_TRN=%u resampler=%d",
                 (unsigned long long)frames,
                 accumulated_us / (1000.0 * (double)frames),
                 peak_us / 1000.0,
                 (unsigned)ik_perf_sound_commands,
                 (unsigned)ik_perf_sou_trn_commands,
                 S9xSpcOutAvailable());
        S9xMessage(S9X_INFO, S9X_ROM_INFO, report);
    }
}
"""
ac = replace_once(ac, audio_step_old, audio_step_new,
                  "PERF2 SPC isolated work cost telemetry")
APUCPP.write_text(ac, encoding="utf-8")

# Stop re-enabling the aggressive BIOS PI controller on every direct frame.
LR = ROOT / "supersnes9x" / "libretro" / "libretro.cpp"
lc = LR.read_text(encoding="utf-8-sig")
sync_old = """    if ((Settings.SGB_BIOSModeActive && S9xSGBBIOSGBIsReleased())
#ifdef IKCORE_SGB_HYBRID_AUDIO
        || S9xSGBPerfAudioActive()
#endif
       )
        S9xSpcSyncToConsumption();
    else
        S9xSpcSyncReset();
"""
sync_new = """    if (Settings.SGB_BIOSModeActive && S9xSGBBIOSGBIsReleased())
        S9xSpcSyncToConsumption();
#ifdef IKCORE_SGB_HYBRID_AUDIO
    else if (S9xSGBPerfAudioActive())
    {
        // Hybrid SPC runs from its own fixed NTSC clock. Preserve its
        // natural pitch and sample ratio instead of chasing a slow host.
    }
#endif
    else
        S9xSpcSyncReset();
"""
lc = replace_once(lc, sync_old, sync_new,
                  "PERF2 suppress wide post-handoff rate controller")
LR.write_text(lc, encoding="utf-8")

print("PERF2 AUDIO AUDIT: fixed-pitch hybrid SPC + isolated SPC timer applied.")


# ---- PERF2 APU DIV EDGE FIX: preserve the GB envelope/sweep timebase -------
# PERF1 deferred GB channel advancement but TimerStep still delivered DIV
# frame-sequencer edges immediately. Flushing accumulated APU cycles first
# prevents envelopes/length/sweep from jumping ahead of the samples that
# lead to those events. Cost: only ~1024 rising/falling DIV edges per second,
# rather than a per-M-cycle APU call (~1,000,000 per second).

GBT = ROOT / "supersnes9x" / "sgb" / "gb_timer.cpp"
gt = GBT.read_text(encoding="utf-8-sig")

old = """\t\t\tif (was && !now)      ApuDivEvent(*mem.apu, mem.double_speed);
\t\t\telse if (!was && now) ApuDivSecondaryEvent(*mem.apu);
"""
new = """\t\t\tif (was && !now)
\t\t\t{
#ifdef IKCORE_SGB_LAZY_APU
\t\t\t\tMemFlushApu(mem);
#endif
\t\t\t\tApuDivEvent(*mem.apu, mem.double_speed);
\t\t\t}
\t\t\telse if (!was && now)
\t\t\t{
#ifdef IKCORE_SGB_LAZY_APU
\t\t\t\tMemFlushApu(mem);
#endif
\t\t\t\tApuDivSecondaryEvent(*mem.apu);
\t\t\t}
"""
gt = replace_once(gt, old, new, "PERF2 APU DIV envelope edge sync")

old = """\t\tif (DivBit(old, abit))
\t\t\tApuDivEvent(*mem.apu, mem.double_speed);
"""
new = """\t\tif (DivBit(old, abit))
\t\t{
#ifdef IKCORE_SGB_LAZY_APU
\t\t\tMemFlushApu(mem);
#endif
\t\t\tApuDivEvent(*mem.apu, mem.double_speed);
\t\t}
"""
gt = replace_once(gt, old, new, "PERF2 APU DIV reset edge sync")
GBT.write_text(gt, encoding="utf-8")
print("PERF2 APU DIV EDGE FIX: lazy GB APU flushes before sequencer events.")


# ---- PERF2 SOU_TRN CHECK: transactional copy, reject malformed payload -----
# The data format is the one specified by Pan Docs: chained little-endian
# [size, destination, data...] records ending with [0, jump_address].
# The previous PERF2 wrote partial APU RAM data before noticing a malformed
# record; validate the complete list first so a corrupt transfer never
# leaves a half-installed sound program in SPC RAM.

APUCPP = ROOT / "supersnes9x" / "apu" / "apu.cpp"
ac = APUCPP.read_text(encoding="utf-8-sig")
old = """static uint32 ik_perf_sou_trn_commands = 0;
"""
new = """static uint32 ik_perf_sou_trn_commands = 0;
static uint32 ik_perf_sou_trn_rejected = 0;
"""
ac = replace_once(ac, old, new, "PERF2 SOU rejected counter")

old = """    size_t off = 0;
    while (off + 4 <= 4096)
    {
        const uint16 n = (uint16)(src[off] | (src[off + 1] << 8));
        const uint16 dst = (uint16)(src[off + 2] | (src[off + 3] << 8));
        off += 4;

        if (n == 0)
        {
            // Jump packet: safely restart/enter the uploaded N-SPC program.
            SNES::smp.regs.pc = dst;
            SNES::smp.opcode_number = 0;
            SNES::smp.opcode_cycle = 0;
            break;
        }

        if (off + n > 4096) break;
        size_t copy_n = n;
        if ((size_t)dst + copy_n > 0x10000)
            copy_n = 0x10000 - (size_t)dst;
        if (copy_n)
            memcpy(SNES::smp.apuram + dst, src + off, copy_n);
        off += n;
    }
    ++ik_perf_sou_trn_commands;
"""
new = """    size_t off = 0;
    bool has_jump = false;
    uint16 jump_addr = 0;

    // Pass 1: validate the entire transfer BEFORE mutating sound RAM.
    while (off + 4 <= 4096)
    {
        const uint16 n = (uint16)(src[off] | (src[off + 1] << 8));
        const uint16 dst = (uint16)(src[off + 2] | (src[off + 3] << 8));
        off += 4;
        if (n == 0)
        {
            has_jump = dst != 0;
            jump_addr = dst;
            break;
        }
        if (off + n > 4096 || (size_t)dst + n > 65536u)
        {
            ++ik_perf_sou_trn_rejected;
            return;
        }
        off += n;
    }
    if (!has_jump)
    {
        ++ik_perf_sou_trn_rejected;
        return;
    }

    // Pass 2: the complete payload is valid, commit all data atomically
    // between SPC execution frames. Do not restart from a partial upload.
    off = 0;
    while (off + 4 <= 4096)
    {
        const uint16 n = (uint16)(src[off] | (src[off + 1] << 8));
        const uint16 dst = (uint16)(src[off + 2] | (src[off + 3] << 8));
        off += 4;
        if (n == 0) break;
        memcpy(SNES::smp.apuram + dst, src + off, n);
        off += n;
    }
    SNES::smp.regs.pc = jump_addr;
    SNES::smp.opcode_number = 0;
    SNES::smp.opcode_cycle = 0;
    ++ik_perf_sou_trn_commands;
"""
ac = replace_once(ac, old, new, "PERF2 SOU atomic 4K validation")
ac = replace_once(ac,
                 '"SOUND=%u SOU_TRN=%u resampler=%d",',
                 '"SOUND=%u SOU_TRN=%u rejected=%u spc_avail=%d",',
                 "PERF2 SOU telemetry format")
ac = replace_once(ac,
                 """                 (unsigned)ik_perf_sou_trn_commands,
                 S9xSpcOutAvailable());""",
                 """                 (unsigned)ik_perf_sou_trn_commands,
                 (unsigned)ik_perf_sou_trn_rejected,
                 S9xSpcOutAvailable());""",
                 "PERF2 SOU telemetry args")
APUCPP.write_text(ac, encoding="utf-8")
print("PERF2 SOU_TRN CHECK: validated atomic sound program transfer.")


# ---- IKCORE VERIFIED SGBPACK FIXES: correct packet layouts and timing -------
# DATA_SND packet: byte1/2 = LE SNES address, byte3 = bank, byte4 = count.
# Original KOF96 ROM bank4 has eight DATA_SND packets $0810..$0867.
SGBCPP = ROOT / "supersnes9x" / "sgb" / "sgb.cpp"
sc = SGBCPP.read_text(encoding="utf-8-sig")
sc = replace_once(sc,
    """\t\t\ticd.last_data_snd_bank = pkt[1];
\t\t\ticd.last_data_snd_addr =
\t\t\t\tstatic_cast<uint16_t>(pkt[2] | (pkt[3] << 8));""",
    """\t\t\ticd.last_data_snd_bank = pkt[3];
\t\t\ticd.last_data_snd_addr =
\t\t\t\tstatic_cast<uint16_t>(pkt[1] | (pkt[2] << 8));""",
    "DATA_SND SNES bank and address diagnostics")
sc = replace_once(sc,
    """\t\t\ticd.last_data_trn_bank = pkt[1];
\t\t\ticd.last_data_trn_addr =
\t\t\t\tstatic_cast<uint16_t>(pkt[2] | (pkt[3] << 8));""",
    """\t\t\ticd.last_data_trn_bank = pkt[3];
\t\t\ticd.last_data_trn_addr =
\t\t\t\tstatic_cast<uint16_t>(pkt[1] | (pkt[2] << 8));""",
    "DATA_TRN SNES bank and address diagnostics")
# Nintendo specifies SOU_TRN completes SIX frames after command frame.
# The next frame_ready may be command frame, hence skip=6 before capturing
# the sixth frame following the command (one frame already counts as skip).
sc = replace_once(sc,
    """\t\timpl_->perf_sou_skip = 1;
\t\timpl_->ppu.frame_ready = false;""",
    """\t\timpl_->perf_sou_skip = 6;
\t\timpl_->ppu.frame_ready = false;""",
    "SOU_TRN 6-frame transfer completion")
SGBCPP.write_text(sc, encoding="utf-8")
print("IKCORE VERIFIED SGBPACK FIXES: DATA_SND map and SOU_TRN timing applied.")


# ---- IKCORE SPC NOMINAL DRIFT: bounded 0.5% resampler fill control ----------
# Fixed SNES clocks and GB audio output rates are not exactly identical.
# Leaving the FIFO fully open loop causes slow systematic overflow or dry
# reads, even if CPU performance is adequate. The old BIOS PI controller
# could compensate with ~50% pitch variation (unacceptable). Use the
# upstream mild 0.5%-bounded servo instead, once per libretro output frame.
LR = ROOT / "supersnes9x" / "libretro" / "libretro.cpp"
lc = LR.read_text(encoding="utf-8-sig")
lc = replace_once(lc,
    """    else if (S9xSGBPerfAudioActive())
    {
        // Hybrid SPC runs from its own fixed NTSC clock. Preserve its
        // natural pitch and sample ratio instead of chasing a slow host.
    }
""",
    """    else if (S9xSGBPerfAudioActive())
    {
        // The SNES clock is nominal/fixed. Only correct small GB/SPC
        // resampler drift (hard bound +/-0.5%), never host FPS deficit.
        S9xSpcAdjustRate(0.005);
    }
""",
    "IKCORE SPC NOMINAL DRIFT bounded servo")
LR.write_text(lc, encoding="utf-8")
print("IKCORE SPC NOMINAL DRIFT: 0.5% bounded SPC resampler controller.")


# ---- IKCORE PARALLEL SPC SAFE DISPATCH (experimental ARM-only opt-in) --------
# A persistent pthread advances the existing BIOS-initialized SNES SPC700/DSP
# alongside the GB emulation. Audio commands are NEVER written from the GB
# thread into SNES::cpu while SPC executes. They are queued in order and
# delivered by the sound worker at the start of the NEXT frame (<=1 frame
# command delay). APU RAM uploads are likewise queued. The GB compositor,
# CHR_TRN/PCT_TRN, input, fade and SNES boot path are completely unchanged.
#
# The worker must finish before ProcessSound reads the SPC resampler, so no
# concurrent read/write of the DSP resampler is possible. Failure to launch
# a worker falls back to the exact sequential PERF2 audio path.
# The SPC thread is cleanly joined during APU shutdown/reset to avoid dlclose
# unloading a live execution context.

APUH = ROOT / "supersnes9x" / "apu" / "apu.h"
ah = APUH.read_text(encoding="utf-8-sig")
ah = replace_once(ah,
    """void  S9xSGBPerfAudioFrame(void);
void  S9xSGBPerfSoundCommand(const uint8 *data, uint32 len);""",
    """void  S9xSGBPerfAudioFrame(void);
#ifdef IKCORE_SGB_PERF_AUDIO_THREADED
void  S9xSGBPerfAudioBeginFrame(void);
void  S9xSGBPerfAudioEndFrame(void);
void  S9xSGBPerfAudioShutdown(void);
#endif
void  S9xSGBPerfSoundCommand(const uint8 *data, uint32 len);""",
    "parallel SPC public interface")
APUH.write_text(ah, encoding="utf-8")

APUCPP = ROOT / "supersnes9x" / "apu" / "apu.cpp"
ac = APUCPP.read_text(encoding="utf-8-sig")

ac = replace_once(ac, '#include "apu.h"\n',
    '#include "apu.h"\n#ifdef IKCORE_SGB_PERF_AUDIO_THREADED\n#include <pthread.h>\n#endif\n',
    "parallel SPC posix header")

# Declaration of the worker's event-push routine: the implementation is
# injected below the existing SPC functions, after the legacy full code.
ac = replace_once(ac,
    """void S9xSGBPerfSoundCommand(const uint8 *data, uint32 len)
{
    if (!ik_perf_audio_active || !data || len < 5) return;
    SNES::cpu.port_write(1, data[1]);
    SNES::cpu.port_write(2, data[2]);
    SNES::cpu.port_write(3, data[3]);
    SNES::cpu.port_write(0, data[4]);
    ++ik_perf_sound_commands;
}""",
    """#ifdef IKCORE_SGB_PERF_AUDIO_THREADED
static void S9xSGBPerfQueueSound(const uint8 *data);
#endif
void S9xSGBPerfSoundCommand(const uint8 *data, uint32 len)
{
    if (!ik_perf_audio_active || !data || len < 5) return;
#ifdef IKCORE_SGB_PERF_AUDIO_THREADED
    // Do NOT touch SNES::cpu.port_write here while the worker is running.
    // Retain all commands FIFO, including those emitted during the current
    // GB frame; next-frame dispatch yields bounded one-frame latency.
    S9xSGBPerfQueueSound(data);
#else
    SNES::cpu.port_write(1, data[1]);
    SNES::cpu.port_write(2, data[2]);
    SNES::cpu.port_write(3, data[3]);
    SNES::cpu.port_write(0, data[4]);
    ++ik_perf_sound_commands;
#endif
}""",
    "parallel SPC SOUND FIFO wrapper")

# Keep the previously validated upload transaction and its rejection logic.
# Move only the mutation to the SPC worker; queue copies of the 4K payload.
ac = replace_once(ac,
    """void S9xSGBPerfSouTrn(const uint8 *src)
{
    if (!ik_perf_audio_active || !src) return;

    size_t off = 0;""",
    """#ifdef IKCORE_SGB_PERF_AUDIO_THREADED
static void S9xSGBPerfQueueSouTrn(const uint8 *data_4k);
static void S9xSGBPerfSouTrnApply(const uint8 *src)
#else
void S9xSGBPerfSouTrn(const uint8 *src)
#endif
{
    if (!ik_perf_audio_active || !src) return;

    size_t off = 0;""",
    "parallel SPC transfer mutation on worker")

# The implementation is placed before the closing #endif of the hybrid APU,
# after the atomic validated SOU_TRN function.
parallel_tail_anchor = """    ++ik_perf_sou_trn_commands;
}
#endif

void S9xAPUTimingSetSpeedup(int ticks)
{
"""
parallel_tail_replacement = r'''    ++ik_perf_sou_trn_commands;
}

#ifdef IKCORE_SGB_PERF_AUDIO_THREADED
namespace {
// FIFO populated ONLY by the GB emulation thread. The dispatch vector is
// handed to the SPC worker only after the worker finished its last frame.
struct IkSgbSoundEvent
{
    uint8_t type; // 0=SOUND, 1=SOU_TRN
    uint8_t data[4];
    std::vector<uint8_t> transfer;
};
static std::vector<IkSgbSoundEvent> ik_audio_pending;
static std::vector<IkSgbSoundEvent> ik_audio_dispatch;
static pthread_t ik_audio_tid;
static pthread_mutex_t ik_audio_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t ik_audio_cv = PTHREAD_COND_INITIALIZER;
static bool ik_audio_thread_ready = false;
static bool ik_audio_stop = false;
static bool ik_audio_requested = false;
static bool ik_audio_done = true;
static bool ik_audio_frame_active = false;
static bool ik_audio_warned = false;
// SFX-only diagnostic. No change to SPC scheduling, mixer, GB frame timing,
// PCM rate-lock or the original sound-command dispatch sequence.
// SGB BIOS uses zero as an explicit effect re-trigger/dummy flag.
// KOF repeatedly sends the SAME A=0x12 sound while the text is drawn.
// Preserve the approved #117 threaded-SPC scheduling and original PCM mixer;
// re-arm only successive identical nonzero A=0x12 commands. Other sounds,
// port 2 (B effects), attributes and port 0 (music) stay byte-identical.
static uint8_t ik_last_sfx_a = 0;

static void IkApplySoundEvents()
{
    for (const auto &e : ik_audio_dispatch)
    {
        if (e.type == 0)
        {
            if (e.data[0] == 0x12 && ik_last_sfx_a == 0x12 &&
                ik_sfx_spc_cycles_advanced < 4096)
            {
                // The #127 zero and 0x12 were written back-to-back. SPC700
                // never ran between them, so the restart was invisible.
                // Let the original N-SPC driver read the zero BEFORE 0x12.
                // Advance within this frame's SPC budget, not extra cycles.
                SNES::cpu.port_write(1, 0x00);
                SNES::smp.clock -= 1024;
                SNES::smp.enter();
                ik_sfx_spc_cycles_advanced += 1024;
            }
            SNES::cpu.port_write(1, e.data[0]);
            SNES::cpu.port_write(2, e.data[1]);
            SNES::cpu.port_write(3, e.data[2]);
            SNES::cpu.port_write(0, e.data[3]);
            ik_last_sfx_a = e.data[0];
            ++ik_perf_sound_commands;
        }
        else if (e.type == 1 && e.transfer.size() == 4096)
            S9xSGBPerfSouTrnApply(e.transfer.data());
    }
}

static void *IkSpcWorkerMain(void *)
{
    for (;;)
    {
        pthread_mutex_lock(&ik_audio_mutex);
        while (!ik_audio_requested && !ik_audio_stop)
            pthread_cond_wait(&ik_audio_cv, &ik_audio_mutex);
        if (ik_audio_stop)
        {
            pthread_mutex_unlock(&ik_audio_mutex);
            break;
        }
        ik_audio_requested = false;
        pthread_mutex_unlock(&ik_audio_mutex);

        // All SPC state and its resampler are exclusively touched here
        // until the GB thread waits for ik_audio_done in EndFrame.
        IkApplySoundEvents();
        S9xSGBPerfAudioFrame();

        pthread_mutex_lock(&ik_audio_mutex);
        ik_audio_done = true;
        pthread_cond_signal(&ik_audio_cv);
        pthread_mutex_unlock(&ik_audio_mutex);
    }
    return nullptr;
}
} // anonymous namespace

static void S9xSGBPerfQueueSound(const uint8 *data)
{
    IkSgbSoundEvent event{};
    event.type = 0;
    event.data[0] = data[1];
    event.data[1] = data[2];
    event.data[2] = data[3];
    event.data[3] = data[4];
    ik_audio_pending.emplace_back(std::move(event));
}

static void S9xSGBPerfQueueSouTrn(const uint8 *data_4k)
{
    IkSgbSoundEvent event{};
    event.type = 1;
    event.transfer.assign(data_4k, data_4k + 4096);
    ik_audio_pending.emplace_back(std::move(event));
}

void S9xSGBPerfSouTrn(const uint8 *src)
{
    if (!ik_perf_audio_active || !src) return;
    S9xSGBPerfQueueSouTrn(src);
}

void S9xSGBPerfAudioBeginFrame(void)
{
    if (!ik_perf_audio_active) return;
    // Every EndFrame waits for the previous job, so these vectors cannot
    // be accessed by the worker while being swapped here.
    ik_audio_dispatch.clear();
    ik_audio_dispatch.swap(ik_audio_pending);
    ik_audio_frame_active = true;
    if (ik_audio_thread_ready)
    {
        pthread_mutex_lock(&ik_audio_mutex);
        ik_audio_done = false;
        ik_audio_requested = true;
        pthread_cond_signal(&ik_audio_cv);
        pthread_mutex_unlock(&ik_audio_mutex);
    }
}

void S9xSGBPerfAudioEndFrame(void)
{
    if (!ik_perf_audio_active || !ik_audio_frame_active) return;
    if (ik_audio_thread_ready)
    {
        pthread_mutex_lock(&ik_audio_mutex);
        while (!ik_audio_done)
            pthread_cond_wait(&ik_audio_cv, &ik_audio_mutex);
        pthread_mutex_unlock(&ik_audio_mutex);
    }
    else
    {
        // Worker creation failure: exactly the previous sequential path.
        IkApplySoundEvents();
        S9xSGBPerfAudioFrame();
    }
    ik_audio_dispatch.clear();
    ik_audio_frame_active = false;
}

void S9xSGBPerfAudioShutdown(void)
{
    if (ik_audio_frame_active)
        S9xSGBPerfAudioEndFrame();
    if (ik_audio_thread_ready)
    {
        pthread_mutex_lock(&ik_audio_mutex);
        ik_audio_stop = true;
        pthread_cond_signal(&ik_audio_cv);
        pthread_mutex_unlock(&ik_audio_mutex);
        pthread_join(ik_audio_tid, nullptr);
        ik_audio_thread_ready = false;
    }
    ik_last_sfx_a = 0;
    ik_sfx_spc_cycles_advanced = 0;
    ik_audio_pending.clear();
    ik_audio_dispatch.clear();
    ik_audio_stop = false;
    ik_audio_requested = false;
    ik_audio_done = true;
    ik_audio_frame_active = false;
    ik_perf_audio_active = false;
}

void S9xSGBPerfAudioStartThread(void)
{
    if (ik_audio_thread_ready) return;
    ik_audio_stop = false;
    ik_audio_requested = false;
    ik_audio_done = true;
    int rc = pthread_create(&ik_audio_tid, nullptr, IkSpcWorkerMain, nullptr);
    ik_audio_thread_ready = (rc == 0);
    if (!ik_audio_thread_ready && !ik_audio_warned)
    {
        ik_audio_warned = true;
        S9xMessage(S9X_INFO, S9X_ROM_INFO,
                   "IKCORE: SPC audio worker unavailable; using serial fallback.");
    }
    else if (ik_audio_thread_ready)
        S9xMessage(S9X_INFO, S9X_ROM_INFO,
                   "IKCORE: parallel SNES SPC/DSP active, GB and border unchanged.");
}
#endif
#endif

void S9xAPUTimingSetSpeedup(int ticks)
{
'''
ac = replace_once(ac, parallel_tail_anchor, parallel_tail_replacement,
                  "parallel SPC append worker with atomic SOU_TRN")

# Thread starts when the already-correct full-BIOS -> direct handoff executes.
# The prior enable routine deliberately did not reset SPC RAM/DSP contents.
ac = replace_once(ac,
    """void S9xSGBPerfAudioEnable(void)
{
    ik_perf_audio_active = true;""",
    """#ifdef IKCORE_SGB_PERF_AUDIO_THREADED
void S9xSGBPerfAudioStartThread(void);
#endif
void S9xSGBPerfAudioEnable(void)
{
#ifdef IKCORE_SGB_PERF_AUDIO_THREADED
    S9xSGBPerfAudioShutdown();
#endif
    ik_perf_audio_active = true;""",
    "parallel SPC restart-safe enable")
ac = replace_once(ac,
    """    S9xSpcResetDrc();
}

bool8 S9xSGBPerfAudioActive(void)""",
    """    S9xSpcResetDrc();
#ifdef IKCORE_SGB_PERF_AUDIO_THREADED
    S9xSGBPerfAudioStartThread();
#endif
}

bool8 S9xSGBPerfAudioActive(void)""",
    "parallel SPC enable worker after fixed audio rate")

# Ensure the libretro core cannot unload a live worker; handle both normal
# unload and in-game reset without changing the SNES or SGB code.
ac = replace_once(ac,
    """void S9xDeinitAPU(void)
{
""",
    """void S9xDeinitAPU(void)
{
#if defined(IKCORE_SGB_HYBRID_AUDIO) && defined(IKCORE_SGB_PERF_AUDIO_THREADED)
    S9xSGBPerfAudioShutdown();
#endif
""",
    "parallel SPC unload join")
ac = replace_once(ac,
    """void S9xResetAPU(void)
{
""",
    """void S9xResetAPU(void)
{
#if defined(IKCORE_SGB_HYBRID_AUDIO) && defined(IKCORE_SGB_PERF_AUDIO_THREADED)
    S9xSGBPerfAudioShutdown();
#endif
""",
    "parallel SPC hard reset join")
ac = replace_once(ac,
    """void S9xSoftResetAPU(void)
{
""",
    """void S9xSoftResetAPU(void)
{
#if defined(IKCORE_SGB_HYBRID_AUDIO) && defined(IKCORE_SGB_PERF_AUDIO_THREADED)
    S9xSGBPerfAudioShutdown();
#endif
""",
    "parallel SPC soft reset join")

APUCPP.write_text(ac, encoding="utf-8")

CPU = ROOT / "supersnes9x" / "cpuexec.cpp"
cc = CPU.read_text(encoding="utf-8-sig")
cc = replace_once(cc,
    """\t\tS9xSGBRunFrame();
#ifdef IKCORE_SGB_HYBRID_AUDIO
\t\tif (!Settings.InRunAhead && S9xSGBPerfAudioActive())
\t\t\tS9xSGBPerfAudioFrame();
#endif""",
    """#if defined(IKCORE_SGB_HYBRID_AUDIO) && defined(IKCORE_SGB_PERF_AUDIO_THREADED)
\t\tif (!Settings.InRunAhead && S9xSGBPerfAudioActive())
\t\t\tS9xSGBPerfAudioBeginFrame();
#endif
\t\tS9xSGBRunFrame();
#ifdef IKCORE_SGB_HYBRID_AUDIO
\t\tif (!Settings.InRunAhead && S9xSGBPerfAudioActive())
#ifdef IKCORE_SGB_PERF_AUDIO_THREADED
\t\t\tS9xSGBPerfAudioEndFrame();
#else
\t\t\tS9xSGBPerfAudioFrame();
#endif
#endif""",
    "parallel SPC begin/end sandwich around GB frame")
CPU.write_text(cc, encoding="utf-8")
print("IKCORE PARALLEL SPC SAFE DISPATCH: independent SNES audio worker applied.")


# ---- IKCORE AUDIO RATE LOCK: fixed frame-locked GB sample cadence -----------
# RunFrame() frame-locks to 70224 emulated T-cycles per SNES VBlank, at
# 60.09881389744051 fps. The upstream GB-APU DRC, however, steers to a
# 12.5%-full GB ring BEFORE S9xLandSamples completely drains that ring each
# frame. The pre-drain fill is ~533 stereo frames, not 1024, so the
# integrator rails negative, oversamples, then overflows the frontend ALSA
# ring. On the physical test this was ~32,450 produced vs 32,040 consumed.
#
# In this opt-in standalone NES Mini hybrid core only: derive the APU's
# *sampling* clock from 70224 GB T-cycles per 60.0988 Hz host frame. This
# changes neither GB channel frequency/timers nor SNES/SPC DSP rate; it
# ensures that a fixed-rate output device consumes ~exactly as many PCM
# samples as the frame-locked emulation generates, with no pitch-shifting
# host resampler, no sample deletion and no extra frame/render work.
#
# BIOS startup never calls the direct-mode RunFrame(), so this cannot
# accelerate, skip or alter the already-approved Super Game Boy boot fade.
# If LCD is off and a different cycle budget is run, leave the audio ring
# safety counters live to catch the rare non-frame-locked case.

GBSRC = ROOT / "supersnes9x" / "sgb" / "sgb.cpp"
gc = GBSRC.read_text(encoding="utf-8-sig")
gc = replace_once(gc,
    """\tconst uint32_t head = impl_->apu.sample_head;
\tconst uint32_t tail = impl_->apu.sample_tail;
\tconst uint32_t fill = (head >= tail) ? (head - tail)
\t                                     : (APU_SAMPLE_BUF_SIZE - tail + head);
\tconst double err = static_cast<double>(fill) / APU_SAMPLE_BUF_SIZE - 0.125;
\timpl_->drc_integ += 5e-5 * err;
\tif (impl_->drc_integ >  0.03) impl_->drc_integ =  0.03;
\tif (impl_->drc_integ < -0.03) impl_->drc_integ = -0.03;
\tdouble corr = 0.02 * err + impl_->drc_integ;
\tif (corr >  0.03) corr =  0.03;
\tif (corr < -0.03) corr = -0.03;
\tApuSetClockHz(impl_->apu, static_cast<int32_t>(base_hz * (1.0 + corr) + 0.5));""",
    """#ifdef IKCORE_SGB_PERF_AUDIO_RATE_LOCK
\t// Only the APU sample period is changed. Emulated GB timer and
\t// pitch/sweep/length events continue to run on authentic T-cycles.
\t// Since this direct renderer locks one 70224-T-cycle GB frame to
\t// each 60.0988-Hz SNES frame, this yields 32040 PCM stereo frames/s.
\t// No PI feedback from a ring that is completely drained each frame.
\tconstexpr double AUDIO_CYCLES_PER_HOST_FRAME = 70224.0;
\tconst int32_t pcm_clock_hz = static_cast<int32_t>(
\t\tAUDIO_CYCLES_PER_HOST_FRAME * SNES_FPS + 0.5);
\tApuSetClockHz(impl_->apu, pcm_clock_hz);
#else
\tconst uint32_t head = impl_->apu.sample_head;
\tconst uint32_t tail = impl_->apu.sample_tail;
\tconst uint32_t fill = (head >= tail) ? (head - tail)
\t                                     : (APU_SAMPLE_BUF_SIZE - tail + head);
\tconst double err = static_cast<double>(fill) / APU_SAMPLE_BUF_SIZE - 0.125;
\timpl_->drc_integ += 5e-5 * err;
\tif (impl_->drc_integ >  0.03) impl_->drc_integ =  0.03;
\tif (impl_->drc_integ < -0.03) impl_->drc_integ = -0.03;
\tdouble corr = 0.02 * err + impl_->drc_integ;
\tif (corr >  0.03) corr =  0.03;
\tif (corr < -0.03) corr = -0.03;
\tApuSetClockHz(impl_->apu, static_cast<int32_t>(base_hz * (1.0 + corr) + 0.5));
#endif""",
    "IKCORE AUDIO RATE LOCK direct SGB frame-locked PCM production")
GBSRC.write_text(gc, encoding="utf-8")
print("IKCORE AUDIO RATE LOCK: fixed 32040Hz GB APU PCM clock in direct mode.")
