/*
 * Ik Core Native / SGBPACK native probe for NES Mini
 * Phase N0: no RetroArch, no libretro.
 *
 * This program validates an SGBPACK1 container directly under Linux ARMv7.
 * It performs no writes to the console filesystem apart from normal stdout.
 */
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#define FOOTER_SIZE 0x100u
#define MAGIC "SGBPACK1"
#define MAGIC_LEN 8u

static uint32_t le32(const unsigned char *p) {
    return (uint32_t)p[0] |
           ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static int range_ok(uint64_t off, uint64_t size, uint64_t file_size) {
    return off <= file_size && size <= file_size - off;
}

int main(int argc, char **argv) {
    FILE *f;
    struct stat st;
    unsigned char footer[FOOTER_SIZE];
    uint64_t footer_off;
    uint32_t sgb_off, sgb_size, gb_off, gb_size, boot_off, boot_size;

    if (argc != 2) {
        fprintf(stderr, "uso: %s archivo.sfc\n", argv[0]);
        return 2;
    }

    if (stat(argv[1], &st) != 0) {
        fprintf(stderr, "stat: %s\n", strerror(errno));
        return 3;
    }
    if ((uint64_t)st.st_size < FOOTER_SIZE) {
        fprintf(stderr, "ERROR: archivo demasiado pequeno\n");
        return 4;
    }

    f = fopen(argv[1], "rb");
    if (!f) {
        fprintf(stderr, "fopen: %s\n", strerror(errno));
        return 5;
    }

    footer_off = (uint64_t)st.st_size - FOOTER_SIZE;
    if (fseeko(f, (off_t)footer_off, SEEK_SET) != 0 ||
        fread(footer, 1, FOOTER_SIZE, f) != FOOTER_SIZE) {
        fprintf(stderr, "ERROR: no se pudo leer footer\n");
        fclose(f);
        return 6;
    }
    fclose(f);

    if (memcmp(footer, MAGIC, MAGIC_LEN) != 0) {
        fprintf(stderr, "ERROR: firma SGBPACK1 no encontrada\n");
        return 7;
    }

    /*
     * SGBPACK1 layout used by this project:
     * 0x10 SGB offset, 0x14 SGB size
     * 0x18 GB offset,  0x1C GB size
     * 0x20 boot offset,0x24 boot size
     */
    sgb_off   = le32(footer + 0x10);
    sgb_size  = le32(footer + 0x14);
    gb_off    = le32(footer + 0x18);
    gb_size   = le32(footer + 0x1c);
    boot_off  = le32(footer + 0x20);
    boot_size = le32(footer + 0x24);

    if (!range_ok(sgb_off, sgb_size, footer_off) ||
        !range_ok(gb_off, gb_size, footer_off) ||
        !range_ok(boot_off, boot_size, footer_off)) {
        fprintf(stderr, "ERROR: offsets/tamanos fuera del contenedor\n");
        return 8;
    }

    printf("Ik Core Native probe N0\n");
    printf("CPU target : ARMv7 Linux\n");
    printf("SGBPACK1   : OK\n");
    printf("file size  : %" PRIu64 " bytes\n", (uint64_t)st.st_size);
    printf("SGB ROM    : off=0x%08" PRIx32 " size=%" PRIu32 "\n", sgb_off, sgb_size);
    printf("GB ROM     : off=0x%08" PRIx32 " size=%" PRIu32 "\n", gb_off, gb_size);
    printf("BOOT ROM   : off=0x%08" PRIx32 " size=%" PRIu32 "\n", boot_off, boot_size);
    printf("RESULT     : native Linux path ready\n");
    return 0;
}
