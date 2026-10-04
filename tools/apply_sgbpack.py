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

print("SGBPACK source integration applied successfully.")
