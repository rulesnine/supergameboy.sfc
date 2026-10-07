/*
 * Ik Core Native / NES Mini frontend probe N1.1
 *
 * Direct Linux framebuffer + evdev benchmark. No RetroArch, no libretro.
 *
 * Improvements over N1:
 * - clears the full screen to black before drawing
 * - integer 3x SGB scaling (256x224 -> 768x672) centered in 1280x720
 * - no per-destination-pixel division
 * - RGB conversion once per source pixel, then replicated 3x3
 * - separate raw framebuffer and SGB blitter benchmarks
 * - restores the original framebuffer on exit
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define FOOTER_SIZE 0x100u
#define MAGIC "SGBPACK1"
#define MAGIC_LEN 8u
#define SGB_W 256
#define SGB_H 224
#define SCALE 3
#define DRAW_W (SGB_W * SCALE)
#define DRAW_H (SGB_H * SCALE)
#define MAX_INPUTS 32

typedef struct {
    uint32_t sgb_off, sgb_size;
    uint32_t gb_off, gb_size;
    uint32_t boot_off, boot_size;
    uint64_t file_size;
} PackInfo;

static uint32_t le32(const unsigned char *p) {
    return (uint32_t)p[0] |
           ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static int range_ok(uint64_t off, uint64_t size, uint64_t limit) {
    return off <= limit && size <= limit - off;
}

static int load_pack_info(const char *path, PackInfo *pi) {
    FILE *f;
    struct stat st;
    unsigned char footer[FOOTER_SIZE];
    uint64_t footer_off;

    memset(pi, 0, sizeof(*pi));
    if (stat(path, &st) != 0) {
        fprintf(stderr, "stat(%s): %s\n", path, strerror(errno));
        return -1;
    }
    if ((uint64_t)st.st_size < FOOTER_SIZE) {
        fprintf(stderr, "ERROR: archivo demasiado pequeno\n");
        return -1;
    }

    f = fopen(path, "rb");
    if (!f) {
        fprintf(stderr, "fopen(%s): %s\n", path, strerror(errno));
        return -1;
    }

    footer_off = (uint64_t)st.st_size - FOOTER_SIZE;
    if (fseeko(f, (off_t)footer_off, SEEK_SET) != 0 ||
        fread(footer, 1, FOOTER_SIZE, f) != FOOTER_SIZE) {
        fprintf(stderr, "ERROR: no se pudo leer footer SGBPACK1\n");
        fclose(f);
        return -1;
    }
    fclose(f);

    if (memcmp(footer, MAGIC, MAGIC_LEN) != 0) {
        fprintf(stderr, "ERROR: firma SGBPACK1 no encontrada\n");
        return -1;
    }

    pi->sgb_off   = le32(footer + 0x10);
    pi->sgb_size  = le32(footer + 0x14);
    pi->gb_off    = le32(footer + 0x18);
    pi->gb_size   = le32(footer + 0x1c);
    pi->boot_off  = le32(footer + 0x20);
    pi->boot_size = le32(footer + 0x24);
    pi->file_size = (uint64_t)st.st_size;

    if (!range_ok(pi->sgb_off, pi->sgb_size, footer_off) ||
        !range_ok(pi->gb_off, pi->gb_size, footer_off) ||
        !range_ok(pi->boot_off, pi->boot_size, footer_off)) {
        fprintf(stderr, "ERROR: offsets/tamanos fuera del contenedor\n");
        return -1;
    }
    return 0;
}

static double now_s(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1000000000.0;
}

static uint32_t scale_chan(uint8_t v, uint32_t bits) {
    if (!bits) return 0;
    if (bits >= 8) return (uint32_t)v << (bits - 8);
    return (uint32_t)(v >> (8 - bits));
}

static uint32_t pack_rgb(const struct fb_var_screeninfo *v, uint8_t r, uint8_t g, uint8_t b) {
    uint32_t p = 0;
    p |= scale_chan(r, v->red.length)   << v->red.offset;
    p |= scale_chan(g, v->green.length) << v->green.offset;
    p |= scale_chan(b, v->blue.length)  << v->blue.offset;
    return p;
}

static void clear_screen(void *fb, const struct fb_fix_screeninfo *fix,
                         const struct fb_var_screeninfo *var) {
    unsigned y;
    size_t visible = (size_t)var->yres * fix->line_length;
    memset(fb, 0, visible);
    for (y = var->yres; y < var->yres_virtual; y++) {
        uint8_t *row = (uint8_t *)fb + (size_t)y * fix->line_length;
        memset(row, 0, fix->line_length);
    }
}

static void make_test_frame(uint32_t *frame, unsigned frame_no) {
    int x, y;
    for (y = 0; y < SGB_H; y++) {
        for (x = 0; x < SGB_W; x++) {
            uint8_t r = (uint8_t)((x + frame_no * 2) & 255);
            uint8_t g = (uint8_t)((y + frame_no) & 255);
            uint8_t b = (uint8_t)(((x ^ y) + frame_no * 3) & 255);
            if (x >= 48 && x < 208 && y >= 40 && y < 184) {
                unsigned cell = (unsigned)((x / 8 + y / 8 + frame_no / 4) & 3);
                static const uint8_t shade[4] = { 232, 176, 104, 32 };
                r = shade[cell];
                g = (uint8_t)(shade[cell] + (cell == 0 ? 15 : 0));
                b = (uint8_t)(shade[cell] / 2);
            }
            frame[y * SGB_W + x] = ((uint32_t)r << 16) | ((uint32_t)g << 8) | b;
        }
    }
}

static void blit_3x_32(void *fb, const struct fb_fix_screeninfo *fix,
                       const struct fb_var_screeninfo *var,
                       const uint32_t *src, uint32_t *packed_line) {
    const unsigned ox = (var->xres - DRAW_W) / 2;
    const unsigned oy = (var->yres - DRAW_H) / 2;
    unsigned sy, sx, k;

    for (sy = 0; sy < SGB_H; sy++) {
        uint32_t *d = packed_line;
        const uint32_t *s = src + sy * SGB_W;

        for (sx = 0; sx < SGB_W; sx++) {
            uint32_t c = s[sx];
            uint8_t r = (uint8_t)(c >> 16);
            uint8_t g = (uint8_t)(c >> 8);
            uint8_t b = (uint8_t)c;
            uint32_t p = pack_rgb(var, r, g, b);
            *d++ = p;
            *d++ = p;
            *d++ = p;
        }

        for (k = 0; k < SCALE; k++) {
            uint8_t *row = (uint8_t *)fb +
                           (size_t)(oy + sy * SCALE + k) * fix->line_length +
                           (size_t)ox * 4u;
            memcpy(row, packed_line, DRAW_W * sizeof(uint32_t));
        }
    }
}

static void blit_3x_16(void *fb, const struct fb_fix_screeninfo *fix,
                       const struct fb_var_screeninfo *var,
                       const uint32_t *src, uint16_t *packed_line) {
    const unsigned ox = (var->xres - DRAW_W) / 2;
    const unsigned oy = (var->yres - DRAW_H) / 2;
    unsigned sy, sx, k;

    for (sy = 0; sy < SGB_H; sy++) {
        uint16_t *d = packed_line;
        const uint32_t *s = src + sy * SGB_W;

        for (sx = 0; sx < SGB_W; sx++) {
            uint32_t c = s[sx];
            uint8_t r = (uint8_t)(c >> 16);
            uint8_t g = (uint8_t)(c >> 8);
            uint8_t b = (uint8_t)c;
            uint16_t p = (uint16_t)pack_rgb(var, r, g, b);
            *d++ = p;
            *d++ = p;
            *d++ = p;
        }

        for (k = 0; k < SCALE; k++) {
            uint8_t *row = (uint8_t *)fb +
                           (size_t)(oy + sy * SCALE + k) * fix->line_length +
                           (size_t)ox * 2u;
            memcpy(row, packed_line, DRAW_W * sizeof(uint16_t));
        }
    }
}

static int open_inputs(int fds[MAX_INPUTS], char names[MAX_INPUTS][128]) {
    int n = 0, i;
    for (i = 0; i < MAX_INPUTS; i++) {
        fds[i] = -1;
        names[i][0] = 0;
    }

    for (i = 0; i < 32 && n < MAX_INPUTS; i++) {
        char path[64];
        int fd;
        snprintf(path, sizeof(path), "/dev/input/event%d", i);
        fd = open(path, O_RDONLY | O_NONBLOCK);
        if (fd >= 0) {
            char name[128] = {0};
            ioctl(fd, EVIOCGNAME(sizeof(name)), name);
            fds[n] = fd;
            snprintf(names[n], 128, "%s", name[0] ? name : "(sin nombre)");
            printf("input      : %s  [%s]\n", path, names[n]);
            n++;
        }
    }
    return n;
}

static unsigned poll_inputs(int *fds, int n) {
    unsigned events = 0;
    int i;
    for (i = 0; i < n; i++) {
        struct input_event ev[16];
        ssize_t got;
        while ((got = read(fds[i], ev, sizeof(ev))) > 0) {
            size_t count = (size_t)got / sizeof(ev[0]), j;
            for (j = 0; j < count; j++) {
                if (ev[j].type == EV_KEY || ev[j].type == EV_ABS) {
                    events++;
                    printf("input event: dev=%d type=%u code=%u value=%d\n",
                           i, (unsigned)ev[j].type,
                           (unsigned)ev[j].code, ev[j].value);
                }
            }
        }
    }
    return events;
}

static double benchmark_raw(void *fb, size_t visible_bytes, int *fds, int input_count,
                            unsigned *input_events) {
    const double duration = 3.0;
    const double target_dt = 1.0 / 60.0;
    double t0 = now_s(), end = t0 + duration, next = t0;
    unsigned frames = 0;
    uint8_t value = 0;

    while (now_s() < end) {
        double n = now_s();
        if (n < next) {
            struct timespec req;
            double rem = next - n;
            req.tv_sec = (time_t)rem;
            req.tv_nsec = (long)((rem - (double)req.tv_sec) * 1000000000.0);
            if (req.tv_nsec > 0) nanosleep(&req, NULL);
        }
        value ^= 0x08;
        memset(fb, value, visible_bytes);
        *input_events += poll_inputs(fds, input_count);
        frames++;
        next += target_dt;
    }

    return (double)frames / (now_s() - t0);
}

static double benchmark_sgb(void *fb, const struct fb_fix_screeninfo *fix,
                            const struct fb_var_screeninfo *var,
                            uint32_t *frame, void *packed_line,
                            int *fds, int input_count, unsigned *input_events) {
    const double duration = 7.0;
    const double target_dt = 1.0 / 60.0;
    double t0 = now_s(), end = t0 + duration, next = t0, last = t0;
    unsigned frames = 0;

    clear_screen(fb, fix, var);

    while (now_s() < end) {
        double n = now_s();
        if (n < next) {
            struct timespec req;
            double rem = next - n;
            req.tv_sec = (time_t)rem;
            req.tv_nsec = (long)((rem - (double)req.tv_sec) * 1000000000.0);
            if (req.tv_nsec > 0) nanosleep(&req, NULL);
        }

        make_test_frame(frame, frames);

        if (var->bits_per_pixel == 32)
            blit_3x_32(fb, fix, var, frame, (uint32_t *)packed_line);
        else
            blit_3x_16(fb, fix, var, frame, (uint16_t *)packed_line);

        *input_events += poll_inputs(fds, input_count);
        frames++;
        next += target_dt;

        n = now_s();
        if (n - last >= 1.0) {
            printf("SGB blit FPS: %.2f (frames=%u)\n", (double)frames / (n - t0), frames);
            fflush(stdout);
            last = n;
        }
    }

    return (double)frames / (now_s() - t0);
}

int main(int argc, char **argv) {
    PackInfo pi;
    int fbfd = -1, inputs[MAX_INPUTS], input_count = 0;
    char input_names[MAX_INPUTS][128];
    struct fb_fix_screeninfo fix;
    struct fb_var_screeninfo var;
    void *fb = MAP_FAILED, *backup = NULL, *packed_line = NULL;
    uint32_t *frame = NULL;
    size_t map_len, visible_bytes;
    unsigned input_events = 0;
    double raw_fps, sgb_fps;

    if (argc != 2) {
        fprintf(stderr, "uso: %s archivo_SGBPACK.sfc\n", argv[0]);
        return 2;
    }
    if (load_pack_info(argv[1], &pi) != 0) return 3;

    printf("Ik Core Native N1.1 - framebuffer optimizado\n");
    printf("SGBPACK1   : OK\n");
    printf("SGB ROM    : off=0x%08" PRIx32 " size=%" PRIu32 "\n", pi.sgb_off, pi.sgb_size);
    printf("GB ROM     : off=0x%08" PRIx32 " size=%" PRIu32 "\n", pi.gb_off, pi.gb_size);
    printf("BOOT ROM   : off=0x%08" PRIx32 " size=%" PRIu32 "\n", pi.boot_off, pi.boot_size);

    fbfd = open("/dev/fb0", O_RDWR);
    if (fbfd < 0) {
        fprintf(stderr, "ERROR: /dev/fb0: %s\n", strerror(errno));
        return 4;
    }
    if (ioctl(fbfd, FBIOGET_FSCREENINFO, &fix) < 0 ||
        ioctl(fbfd, FBIOGET_VSCREENINFO, &var) < 0) {
        fprintf(stderr, "ERROR: ioctl framebuffer: %s\n", strerror(errno));
        close(fbfd);
        return 5;
    }

    printf("framebuffer: %ux%u virt=%ux%u, %u bpp, stride=%u, smem=%u\n",
           var.xres, var.yres, var.xres_virtual, var.yres_virtual,
           var.bits_per_pixel, fix.line_length, fix.smem_len);

    if (var.xres < DRAW_W || var.yres < DRAW_H ||
        (var.bits_per_pixel != 16 && var.bits_per_pixel != 32)) {
        fprintf(stderr, "ERROR: modo framebuffer no compatible con N1.1\n");
        close(fbfd);
        return 6;
    }

    map_len = fix.smem_len;
    visible_bytes = (size_t)var.yres * fix.line_length;
    fb = mmap(NULL, map_len, PROT_READ | PROT_WRITE, MAP_SHARED, fbfd, 0);
    if (fb == MAP_FAILED) {
        fprintf(stderr, "ERROR: mmap framebuffer: %s\n", strerror(errno));
        close(fbfd);
        return 7;
    }

    backup = malloc(map_len);
    frame = (uint32_t *)malloc(SGB_W * SGB_H * sizeof(uint32_t));
    packed_line = malloc(DRAW_W * (var.bits_per_pixel / 8));
    if (!backup || !frame || !packed_line) {
        fprintf(stderr, "ERROR: sin memoria para N1.1\n");
        free(backup); free(frame); free(packed_line);
        munmap(fb, map_len); close(fbfd);
        return 8;
    }
    memcpy(backup, fb, map_len);

    input_count = open_inputs(inputs, input_names);
    printf("input count : %d\n", input_count);
    printf("video path  : 256x224 -> 768x672 (3x entero), centrado\n");
    printf("pantalla    : limpia a negro durante la prueba\n");
    fflush(stdout);

    printf("\n[1/2] benchmark memoria/framebuffer, 3 s\n");
    raw_fps = benchmark_raw(fb, visible_bytes, inputs, input_count, &input_events);
    printf("RAW RESULT  : %.2f FPS\n", raw_fps);

    printf("\n[2/2] benchmark blitter SGB 3x, 7 s\n");
    sgb_fps = benchmark_sgb(fb, &fix, &var, frame, packed_line,
                            inputs, input_count, &input_events);
    printf("SGB RESULT  : %.2f FPS\n", sgb_fps);

    memcpy(fb, backup, map_len);
    msync(fb, map_len, MS_SYNC);

    printf("\nFINAL\n");
    printf("RAW FPS     : %.2f\n", raw_fps);
    printf("SGB BLIT FPS: %.2f\n", sgb_fps);
    printf("input events: %u\n", input_events);
    printf("framebuffer : restaurado\n");

    for (int i = 0; i < input_count; i++) close(inputs[i]);
    free(packed_line);
    free(frame);
    free(backup);
    munmap(fb, map_len);
    close(fbfd);
    return 0;
}
