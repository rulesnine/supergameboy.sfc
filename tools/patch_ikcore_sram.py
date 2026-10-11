#!/usr/bin/env python3
"""Isolated battery-backed/internal SRAM persistence for Ik Core Standalone.

Apply AFTER prepare_ikcore_standalone.py and patch_ikcore_hakchi_loader.py.
No changes to #137 SNES/GB/SPC/DSP core. Per-game CLV ID always comes from
Hakchi's original argv/cwd, NEVER the transient .7z extraction filename.

Save files: /var/lib/hakchi/ikcore-saves/<CLV-ID>.srm
 - restore before the first emulated frame
 - autosave only on changed RAM, at 5-second checks
 - force a final write on normal exit
 - atomic temp+fsync+rename to avoid truncating a good save
 - reject wrong-size/corrupted existing saves instead of overwriting
"""
from pathlib import Path
import sys

p = Path(sys.argv[1])
src = p.read_text(encoding="utf-8")

def once(before, after):
    global src
    n = src.count(before)
    if n != 1:
        raise SystemExit(f"SRAM anchor mismatch {n}: {before[:160]!r}")
    src = src.replace(before, after, 1)

once('#define IKCORE_STATE_DIR "/var/lib/hakchi/sgb-native-test"\n',
     '#define IKCORE_STATE_DIR "/var/lib/hakchi/sgb-native-test"\n'
     '#define IKCORE_SAVE_DIR "/var/lib/hakchi/ikcore-saves"\n')
once('static void (*core_retro_unload_game)(void);\n',
     'static void (*core_retro_unload_game)(void);\n'
     'static void *(*core_retro_get_memory_data)(unsigned);\n'
     'static size_t (*core_retro_get_memory_size)(unsigned);\n')

once('    LOAD_CORE(retro_unload_game);\n',
     '    LOAD_CORE(retro_unload_game);\n'
     '    LOAD_CORE(retro_get_memory_data);\n'
     '    LOAD_CORE(retro_get_memory_size);\n')

helper = r'''
/* Dedicated native SRAM writer. The upstream libretro core intentionally
 * exposes SGB Game Boy cart RAM as RETRO_MEMORY_SAVE_RAM. It does not perform
 * persistence for this minimal standalone frontend; Hakchi's command-line
 * --save-data-backing-file is otherwise ignored. No save-state behavior here.
 */
static unsigned char *ik_sram_shadow = NULL;
static size_t ik_sram_size = 0;
static char ik_sram_path[512] = {0};
static double ik_sram_next_check = 0.0;
static int ik_sram_disabled = 0;
static unsigned ik_sram_write_count = 0;

static int ik_sram_atomic_write(const char *path,
                                const unsigned char *data, size_t bytes)
{
    char tmp[600];
    int fd, n;
    size_t written = 0;
    n = snprintf(tmp, sizeof tmp, "%s.tmp.%ld", path, (long)getpid());
    if (n <= 0 || (size_t)n >= sizeof tmp) return 0;
    fd = open(tmp, O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0) return 0;
    while (written < bytes) {
        ssize_t rc = write(fd, data + written, bytes - written);
        if (rc < 0 && errno == EINTR) continue;
        if (rc <= 0) {
            int saved_errno = errno;
            close(fd);
            unlink(tmp);
            errno = saved_errno;
            return 0;
        }
        written += (size_t)rc;
    }
    if (fsync(fd) != 0) {
        int saved_errno = errno;
        close(fd);
        unlink(tmp);
        errno = saved_errno;
        return 0;
    }
    if (close(fd) != 0) {
        unlink(tmp);
        return 0;
    }
    if (rename(tmp, path) != 0) {
        int saved_errno = errno;
        unlink(tmp);
        errno = saved_errno;
        return 0;
    }
    return 1;
}

static void ik_sram_initialize(int argc, char **argv)
{
    int i;
    char id[16] = {0}, next[16] = {0}, cwd[4096] = {0};
    struct stat st;
    void *ram;
    size_t size;
    FILE *f;

    if (!core_retro_get_memory_data || !core_retro_get_memory_size) {
        log_printf("SRAM         : núcleo no expone interfaz de RAM.\n");
        return;
    }
    ram = core_retro_get_memory_data(RETRO_MEMORY_SAVE_RAM);
    size = core_retro_get_memory_size(RETRO_MEMORY_SAVE_RAM);
    if (!ram || size == 0) {
        log_printf("SRAM         : cartucho sin RAM de guardado.\n");
        return;
    }
    if (size > 1024u * 1024u) {
        log_printf("SRAM ERROR   : tamaño inesperado %zu; no guardar.\n", size);
        return;
    }

    /* Prefer the official game code in Clover argv over the extracted .sfc.
     * Refuse to mix games when the launch context contains multiple IDs. */
    for (i = 1; i < argc; ++i) {
        if (!ikcore_extract_clv_id(argv[i], next)) continue;
        if (id[0] && strcmp(id, next) != 0) {
            log_printf("SRAM ERROR   : IDs diferentes en los argumentos; "
                       "guardado deshabilitado para proteger partidas.\n");
            return;
        }
        memcpy(id, next, sizeof id);
    }
    if (!id[0] && getcwd(cwd, sizeof cwd))
        (void)ikcore_extract_clv_id(cwd, id);
    if (!id[0]) {
        log_printf("SRAM ERROR   : falta ID estable de Hakchi; "
                   "nunca guardar en la carpeta temporal del .7z.\n");
        return;
    }

    if (mkdir(IKCORE_SAVE_DIR, 0755) != 0 && errno != EEXIST) {
        log_printf("SRAM ERROR   : no se puede crear %s: %s\n",
                   IKCORE_SAVE_DIR, strerror(errno));
        return;
    }
    if (snprintf(ik_sram_path, sizeof ik_sram_path,
                 IKCORE_SAVE_DIR "/%s.srm", id) >= (int)sizeof ik_sram_path) {
        ik_sram_path[0] = 0;
        return;
    }

    ik_sram_shadow = (unsigned char *)malloc(size);
    if (!ik_sram_shadow) {
        log_printf("SRAM ERROR   : sin memoria para referencia de %zu bytes.\n", size);
        ik_sram_path[0] = 0;
        return;
    }
    ik_sram_size = size;
    memcpy(ik_sram_shadow, ram, size);

    /* Never overwrite an existing backup with a different SRAM size.
     * Read the entire save to temporary RAM before touching the live game.
     */
    if (stat(ik_sram_path, &st) == 0) {
        unsigned char *saved;
        if (!S_ISREG(st.st_mode) || st.st_size != (off_t)size) {
            log_printf("SRAM ERROR   : guardado existente con tamaño incorrecto "
                       "(%lld, esperado %zu). Se protege; escritura BLOQUEADA: %s\n",
                       (long long)st.st_size, size, ik_sram_path);
            ik_sram_disabled = 1;
            return;
        }
        saved = (unsigned char *)malloc(size);
        if (!saved) {
            ik_sram_disabled = 1;
            return;
        }
        f = fopen(ik_sram_path, "rb");
        if (!f || fread(saved, 1, size, f) != size) {
            log_printf("SRAM ERROR   : imposible leer %s; escritura BLOQUEADA.\n",
                       ik_sram_path);
            if (f) fclose(f);
            free(saved);
            ik_sram_disabled = 1;
            return;
        }
        if (fclose(f) != 0) {
            free(saved);
            ik_sram_disabled = 1;
            return;
        }
        memcpy(ram, saved, size);
        memcpy(ik_sram_shadow, saved, size);
        free(saved);
        log_printf("SRAM LOAD    : %zu bytes restaurados, %s\n", size, ik_sram_path);
    } else if (errno == ENOENT) {
        log_printf("SRAM NEW     : %zu bytes, %s\n", size, ik_sram_path);
    } else {
        log_printf("SRAM ERROR   : no se puede consultar %s; escritura BLOQUEADA.\n",
                   ik_sram_path);
        ik_sram_disabled = 1;
    }
    ik_sram_next_check = now_s() + 5.0;
}

/* At most one tiny RAM comparison every five seconds. Avoid flash writes if
 * the game hasn't updated the save. Also flush before the core is unloaded.
 */
static void ik_sram_flush(int force)
{
    void *ram;
    size_t size;
    double t;
    if (!ik_sram_shadow || ik_sram_disabled || !ik_sram_path[0]) return;
    t = now_s();
    if (!force && t < ik_sram_next_check) return;
    ik_sram_next_check = t + 5.0;
    ram = core_retro_get_memory_data(RETRO_MEMORY_SAVE_RAM);
    size = core_retro_get_memory_size(RETRO_MEMORY_SAVE_RAM);
    if (!ram || size != ik_sram_size) {
        log_printf("SRAM ERROR   : RAM cambió de tamaño; guardado BLOQUEADO.\n");
        ik_sram_disabled = 1;
        return;
    }
    if (!memcmp(ram, ik_sram_shadow, size)) return;
    if (!ik_sram_atomic_write(ik_sram_path, (const unsigned char *)ram, size)) {
        log_printf("SRAM ERROR   : no se pudo guardar %s: %s\n",
                   ik_sram_path, strerror(errno));
        ik_sram_disabled = 1;
        return;
    }
    memcpy(ik_sram_shadow, ram, size);
    ++ik_sram_write_count;
    log_printf("SRAM SAVE    : %zu bytes, escritura #%u (%s), %s\n",
               size, ik_sram_write_count,
               force ? "al salir" : "autoguardado", ik_sram_path);
}

static void ik_sram_finish(void)
{
    free(ik_sram_shadow);
    ik_sram_shadow = NULL;
    ik_sram_size = 0;
    ik_sram_path[0] = 0;
}
'''
once('int main(int argc, char **argv)\n{\n', helper+'\nint main(int argc, char **argv)\n{\n')
once('    game_loaded = 1;\n',
     '    game_loaded = 1;\n'
     '    ik_sram_initialize(argc, argv);\n')
once('        core_retro_run();\n        work_end = now_s();',
     '        core_retro_run();\n'
     '        ik_sram_flush(0);\n'
     '        work_end = now_s();')
once('cleanup:\n    if (game_loaded && core_retro_unload_game) core_retro_unload_game();',
     'cleanup:\n'
     '    if (game_loaded) ik_sram_flush(1);\n'
     '    ik_sram_finish();\n'
     '    if (game_loaded && core_retro_unload_game) core_retro_unload_game();')

p.write_text(src, encoding="utf-8")
print("Ik Core SRAM persistence patch applied: per-CLV ID, restore, periodic+exit flush, atomic.")
