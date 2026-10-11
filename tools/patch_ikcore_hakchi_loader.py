#!/usr/bin/env python3
"""Fix ONLY the Hakchi-side content path resolver in the standalone frontend.

On NES Mini, Clover may launch custom executables with stock extra arguments
(e.g. --save-data-backing-file /.../CLV-U-XXXXX/save.sram) but omit the
custom game's ROM argument. Detect the *selected* CLV game ID in those
arguments; resolve exactly one SGBPACK1 file inside that game's own folder.
This never uses a global/default KOF96 image and never alters the core.
"""
from pathlib import Path
import sys

p = Path(sys.argv[1])
src = p.read_text("utf-8")

def once(before, after):
    global src
    n = src.count(before)
    if n != 1:
        raise SystemExit(f"patch anchor count {n} != 1: {before[:100]!r}")
    src = src.replace(before, after, 1)

once("#include <errno.h>\n", "#include <errno.h>\n#include <dirent.h>\n")

start = src.index("static const char *select_pack_path(int argc, char **argv)\n{")
end = src.index("\nint main(int argc, char **argv)\n{", start)
new = r"""
/*
 * Recognize a CLV-X-XXXXX game code only when it is actually present in
 * Clover-supplied argv or cwd (usually --save-data-backing-file's value).
 * Never enumerate the global games directory or guess a default game.
 */
static int ikcore_extract_clv_id(const char *text, char id[16])
{
    const char *p;
    if (!text) return 0;
    for (p = text; (p = strstr(p, "CLV-")) != NULL; ++p) {
        int i, ok = (p[4] >= 'A' && p[4] <= 'Z') && p[5] == '-';
        if (!ok) continue;
        for (i = 6; i < 11; ++i) {
            char ch = p[i];
            if (!((ch >= 'A' && ch <= 'Z') ||
                  (ch >= '0' && ch <= '9'))) {
                ok = 0;
                break;
            }
        }
        if (!ok || ((p[11] >= 'A' && p[11] <= 'Z') ||
                    (p[11] >= '0' && p[11] <= '9'))) continue;
        memcpy(id, p, 11);
        id[11] = 0;
        return 1;
    }
    return 0;
}

static char ikcore_resolved_pack[4096];

static int ikcore_is_sgbpack1(const char *path)
{
    struct stat st;
    unsigned char sig[8];
    FILE *f;
    if (!has_rom_extension(path) || stat(path, &st) != 0 ||
        !S_ISREG(st.st_mode) || st.st_size < 256) return 0;
    f = fopen(path, "rb");
    if (!f) return 0;
    if (fseek(f, -256L, SEEK_END) != 0 || fread(sig, 1, 8, f) != 8) {
        fclose(f);
        return 0;
    }
    fclose(f);
    return memcmp(sig, "SGBPACK1", 8) == 0;
}

/* Search ONE specific game directory, selecting only one valid SGBPACK1.
 * Return: 1 found, 0 none, -1 ambiguous, never silently pick a wrong ROM.
 */
static int ikcore_find_pack_in_dir(const char *dir)
{
    DIR *d = opendir(dir);
    struct dirent *entry;
    char candidate[4096];
    int found = 0;
    if (!d) return 0;
    while ((entry = readdir(d)) != NULL) {
        int n;
        if (!has_rom_extension(entry->d_name)) continue;
        n = snprintf(candidate, sizeof candidate, "%s/%s", dir, entry->d_name);
        if (n <= 0 || (size_t)n >= sizeof candidate) continue;
        if (!ikcore_is_sgbpack1(candidate)) continue;
        if (++found > 1) {
            log_printf("ERROR: hay varios SGBPACK1 en %s; indicar ruta exacta.\n", dir);
            closedir(d);
            return -1;
        }
        memcpy(ikcore_resolved_pack, candidate, (size_t)n + 1);
    }
    closedir(d);
    if (found == 1)
        log_printf("Hakchi ROM  : %s (carpeta de juego)\n", ikcore_resolved_pack);
    return found;
}

static const char *select_pack_path(int argc, char **argv)
{
    int i, state;
    char id[16] = {0};
    char next_id[16] = {0};
    char cwd[4096] = {0};
    char dir[4096];
    static const char *game_roots[] = {
        "/var/games/%s",
        "/var/lib/hakchi/games/%s",
        "/var/lib/hakchi/games_snes/%s",
        "/usr/share/games/%s",
        "/var/lib/hakchi/games/nes-usa/.storage/%s",
        "/var/lib/hakchi/games/snes-eur/.storage/%s"
    };

    log_printf("Hakchi argc : %d\n", argc);
    for (i = 0; i < argc; ++i) {
        const char *arg = argv[i] ? argv[i] : "";
        log_printf("Hakchi argv[%d]: %s\n", i, arg);
        if (ikcore_extract_clv_id(arg, next_id)) {
            if (id[0] && strcmp(id, next_id)) {
                log_printf("ERROR: varios codigos CLV diferentes; no elegir ROM.\n");
                return NULL;
            }
            strcpy(id, next_id);
        }
    }

    /* Preferred: Hakchi passed an actual ROM path. */
    for (i = 1; i < argc; ++i) {
        const char *arg = argv[i];
        if (!arg || !arg[0]) continue;
        if ((strcmp(arg, "--rom") == 0 || strcmp(arg, "-rom") == 0 ||
             strcmp(arg, "--game") == 0) && i + 1 < argc) {
            const char *path = argv[++i];
            if (has_rom_extension(path) && access(path, R_OK) == 0) {
                log_printf("Hakchi ROM  : %s (argumento)\n", path);
                return path;
            }
        }
        if (!strncmp(arg, "--rom=", 6) || !strncmp(arg, "--game=", 7)) {
            const char *path = strchr(arg, '=') + 1;
            if (has_rom_extension(path) && access(path, R_OK) == 0) {
                log_printf("Hakchi ROM  : %s (argumento)\n", path);
                return path;
            }
        }
        if (has_rom_extension(arg)) {
            if (access(arg, R_OK) == 0) {
                log_printf("Hakchi ROM  : %s (argumento)\n", arg);
                return arg;
            }
            log_printf("WARN: argumento ROM no accesible: %s\n", arg);
        }
    }

    if (getcwd(cwd, sizeof cwd)) {
        log_printf("Hakchi cwd  : %s\n", cwd);
        if (!id[0] && ikcore_extract_clv_id(cwd, next_id))
            strcpy(id, next_id);
    }

    /* Exactly the selected game ID, determined from Clover launch context. */
    if (id[0]) {
        size_t k;
        log_printf("Hakchi ID   : %s\n", id);
        for (k = 0; k < sizeof game_roots / sizeof game_roots[0]; ++k) {
            int n = snprintf(dir, sizeof dir, game_roots[k], id);
            if (n <= 0 || (size_t)n >= sizeof dir) continue;
            state = ikcore_find_pack_in_dir(dir);
            if (state == 1) return ikcore_resolved_pack;
            if (state < 0) return NULL;
        }
    }

    /* Last resort: only the process working directory, never a global scan. */
    if (cwd[0]) {
        state = ikcore_find_pack_in_dir(cwd);
        if (state == 1) return ikcore_resolved_pack;
    }

    log_printf("ERROR: Hakchi no entrego una ROM legible y no hay un unico "
               "SGBPACK1 en la carpeta del juego seleccionado.\n");
    return NULL;
}
"""
src = src[:start] + new + src[end:]

# Clarify failure without advertising a fixed ROM or misleading 120s test.
once('log_printf("IK CORE: no SGBPACK1 .sfc/.smc was specified.\\n");',
     'log_printf("IK CORE: no se pudo resolver el SGBPACK1 del juego de Hakchi.\\n");')
p.write_text(src, "utf-8")
print("IKCORE HAKCHI ROUTE: argv/Clover ID/cwd fallback, SGBPACK1-only, no fixed KOF96.")
