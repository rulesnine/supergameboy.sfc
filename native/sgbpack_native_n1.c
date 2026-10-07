/*
 * Ik Core Native / NES Mini frontend probe N1
 *
 * Direct Linux framebuffer + evdev test. No RetroArch, no libretro.
 * It validates SGBPACK1, saves the framebuffer, renders a 256x224
 * synthetic SGB surface for a short benchmark, samples input events,
 * prints measured presentation FPS, and restores the framebuffer.
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
#define MAX_INPUTS 16

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

static void make_test_frame(uint32_t *frame, unsigned frame_no) {
    int x, y;
    for (y = 0; y < SGB_H; y++) {
        for (x = 0; x < SGB_W; x++) {
            uint8_t r = (uint8_t)((x + frame_no * 2) & 255);
            uint8_t g = (uint8_t)((y + frame_no) & 255);
            uint8_t b = (uint8_t)(((x ^ y) + frame_no * 3) & 255);
            /* Game Boy viewport gets a visibly different moving pattern. */
            if (x >= 48 && x < 208 && y >= 40 && y < 184) {
                unsigned cell = (unsigned)((x / 8 + y / 8 + frame_no / 4) & 3);
                static const uint8_t shade[4] = { 232, 176, 104, 32 };
                r = (uint8_t)(shade[cell]);
                g = (uint8_t)(shade[cell] + (cell == 0 ? 15 : 0));
                b = (uint8_t)(shade[cell] / 2);
            }
            frame[y * SGB_W + x] = ((uint32_t)r << 16) | ((uint32_t)g << 8) | b;
        }
    }
}

static void blit_scaled(void *fb, const struct fb_fix_screeninfo *fix,
                        const struct fb_var_screeninfo *var,
                        const uint32_t *src) {
    unsigned x, y;
    unsigned out_w = var->xres, out_h = var->yres;
    unsigned scale_x = out_w / SGB_W;
    unsigned scale_y = out_h / SGB_H;
    unsigned scale = scale_x < scale_y ? scale_x : scale_y;
    unsigned draw_w, draw_h, ox, oy;

    if (scale < 1) scale = 1;
    draw_w = SGB_W * scale;
    draw_h = SGB_H * scale;
    if (draw_w > out_w) draw_w = out_w;
    if (draw_h > out_h) draw_h = out_h;
    ox = (out_w - draw_w) / 2;
    oy = (out_h - draw_h) / 2;

    for (y = 0; y < draw_h; y++) {
        unsigned sy = (unsigned)((uint64_t)y * SGB_H / draw_h);
        uint8_t *row = (uint8_t *)fb + (uint64_t)(y + oy) * fix->line_length;
        for (x = 0; x < draw_w; x++) {
            unsigned sx = (unsigned)((uint64_t)x * SGB_W / draw_w);
            uint32_t c = src[sy * SGB_W + sx];
            uint8_t r = (uint8_t)(c >> 16), g = (uint8_t)(c >> 8), b = (uint8_t)c;
            uint32_t p = pack_rgb(var, r, g, b);
            unsigned dx = x + ox;
            if (var->bits_per_pixel == 16) {
                ((uint16_t *)row)[dx] = (uint16_t)p;
            } else if (var->bits_per_pixel == 32) {
                ((uint32_t *)row)[dx] = p;
            }
        }
    }
}

static int open_inputs(int fds[MAX_INPUTS]) {
    int n = 0, i;
    for (i = 0; i < MAX_INPUTS; i++) fds[i] = -1;
    for (i = 0; i < 32 && n < MAX_INPUTS; i++) {
        char path[64];
        int fd;
        snprintf(path, sizeof(path), "/dev/input/event%d", i);
        fd = open(path, O_RDONLY | O_NONBLOCK);
        if (fd >= 0) {
            fds[n++] = fd;
            printf("input      : %s abierto\n", path);
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
                if (ev[j].type == EV_KEY) {
                    events++;
                    printf("key event  : code=%u value=%d\n",
                           (unsigned)ev[j].code, ev[j].value);
                }
            }
        }
    }
    return events;
}

int main(int argc, char **argv) {
    PackInfo pi;
    int fbfd = -1, inputs[MAX_INPUTS], input_count = 0;
    struct fb_fix_screeninfo fix;
    struct fb_var_screeninfo var;
    void *fb = MAP_FAILED;
    void *backup = NULL;
    uint32_t *frame = NULL;
    size_t map_len;
    unsigned frame_no = 0, input_events = 0;
    double t0, last, end, next_tick;
    const double duration = 10.0;
    const double target_dt = 1.0 / 60.0;

    if (argc != 2) {
        fprintf(stderr, "uso: %s archivo_SGBPACK.sfc\n", argv[0]);
        return 2;
    }
    if (load_pack_info(argv[1], &pi) != 0) return 3;

    printf("Ik Core Native N1 - frontend directo Linux\n");
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

    printf("framebuffer: %ux%u, %u bpp, stride=%u, smem=%u\n",
           var.xres, var.yres, var.bits_per_pixel, fix.line_length, fix.smem_len);

    if (var.bits_per_pixel != 16 && var.bits_per_pixel != 32) {
        fprintf(stderr, "ERROR: N1 soporta framebuffer 16/32 bpp; detectado %u\n",
                var.bits_per_pixel);
        close(fbfd);
        return 6;
    }

    map_len = fix.smem_len;
    fb = mmap(NULL, map_len, PROT_READ | PROT_WRITE, MAP_SHARED, fbfd, 0);
    if (fb == MAP_FAILED) {
        fprintf(stderr, "ERROR: mmap framebuffer: %s\n", strerror(errno));
        close(fbfd);
        return 7;
    }

    backup = malloc(map_len);
    frame = (uint32_t *)malloc(SGB_W * SGB_H * sizeof(uint32_t));
    if (!backup || !frame) {
        fprintf(stderr, "ERROR: sin memoria para prueba N1\n");
        if (backup) free(backup);
        if (frame) free(frame);
        munmap(fb, map_len);
        close(fbfd);
        return 8;
    }
    memcpy(backup, fb, map_len);

    input_count = open_inputs(inputs);
    printf("input count : %d\n", input_count);
    printf("benchmark   : 10 s, objetivo 60 presentaciones/s\n");
    fflush(stdout);

    t0 = last = now_s();
    end = t0 + duration;
    next_tick = t0;

    while (now_s() < end) {
        double n = now_s();
        if (n < next_tick) {
            struct timespec req;
            double rem = next_tick - n;
            req.tv_sec = (time_t)rem;
            req.tv_nsec = (long)((rem - (double)req.tv_sec) * 1000000000.0);
            if (req.tv_nsec > 0) nanosleep(&req, NULL);
        }

        make_test_frame(frame, frame_no);
        blit_scaled(fb, &fix, &var, frame);
        input_events += poll_inputs(inputs, input_count);
        frame_no++;
        next_tick += target_dt;

        n = now_s();
        if (n - last >= 1.0) {
            double fps = (double)frame_no / (n - t0);
            printf("native FPS : %.2f (frames=%u)\n", fps, frame_no);
            fflush(stdout);
            last = n;
        }
    }

    memcpy(fb, backup, map_len);
    msync(fb, map_len, MS_SYNC);

    {
        double elapsed = now_s() - t0;
        printf("RESULT      : %.2f FPS promedio (%u frames / %.3f s)\n",
               (double)frame_no / elapsed, frame_no, elapsed);
        printf("input events: %u\n", input_events);
        printf("framebuffer : restaurado\n");
    }

    for (int i = 0; i < input_count; i++) close(inputs[i]);
    free(frame);
    free(backup);
    munmap(fb, map_len);
    close(fbfd);
    return 0;
}
