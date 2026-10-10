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
