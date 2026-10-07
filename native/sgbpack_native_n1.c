/*
 * Ik Core Native N1.7 — Clover-native EGL lifecycle probe
 *
 * Purpose:
 * - launch from Clover/Hakchi as a native application
 * - acquire display through EGL instead of writing /dev/fb0 directly
 * - DO NOT open ALSA in this probe
 * - grab Nintendo Clovercon with evdev
 * - render a fullscreen moving color-bar test for 10 seconds
 * - release input + EGL cleanly, then return to Clover
 *
 * This is intentionally not the SGB engine yet.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

#include <EGL/egl.h>
#include <GLES2/gl2.h>

typedef struct {
    unsigned short width;
    unsigned short height;
} NativeFBWindow;

static double now_s(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1000000000.0;
}

static int get_fb_size(NativeFBWindow *w) {
    int fd;
    struct fb_var_screeninfo v;

    fd = open("/dev/fb0", O_RDONLY);
    if (fd < 0) return -1;
    if (ioctl(fd, FBIOGET_VSCREENINFO, &v) < 0) {
        close(fd);
        return -1;
    }
    close(fd);

    w->width = (unsigned short)v.xres;
    w->height = (unsigned short)v.yres;
    return 0;
}

static int open_clovercon(void) {
    int i;
    for (i = 0; i < 32; i++) {
        char path[64];
        char name[128] = {0};
        int fd;

        snprintf(path, sizeof(path), "/dev/input/event%d", i);
        fd = open(path, O_RDONLY | O_NONBLOCK);
        if (fd < 0) continue;

        ioctl(fd, EVIOCGNAME(sizeof(name)), name);
        if (strstr(name, "Nintendo Clovercon")) {
            printf("controller  : %s [%s]\n", path, name);
            if (ioctl(fd, EVIOCGRAB, 1) == 0)
                printf("controller  : EVIOCGRAB OK\n");
            else
                printf("controller  : EVIOCGRAB fallo: %s\n", strerror(errno));
            return fd;
        }
        close(fd);
    }
    return -1;
}

static unsigned poll_pad(int fd) {
    struct input_event ev[32];
    ssize_t got;
    unsigned n = 0;

    if (fd < 0) return 0;

    while ((got = read(fd, ev, sizeof(ev))) > 0) {
        size_t i;
        size_t count = (size_t)got / sizeof(ev[0]);
        for (i = 0; i < count; i++) {
            if (ev[i].type == EV_KEY || ev[i].type == EV_ABS) {
                printf("pad event   : type=%u code=%u value=%d\n",
                       (unsigned)ev[i].type,
                       (unsigned)ev[i].code,
                       ev[i].value);
                n++;
            }
        }
    }
    return n;
}

static void draw_test(unsigned frame, int w, int h) {
    static const GLfloat bars[6][3] = {
        {0.90f, 0.20f, 0.15f},
        {0.95f, 0.70f, 0.10f},
        {0.20f, 0.75f, 0.25f},
        {0.10f, 0.65f, 0.90f},
        {0.25f, 0.30f, 0.90f},
        {0.75f, 0.20f, 0.85f}
    };
    int i;
    int bw = w / 6;
    int shift = (int)(frame % 6);

    glDisable(GL_DITHER);
    glEnable(GL_SCISSOR_TEST);

    glScissor(0, 0, w, h);
    glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);

    for (i = 0; i < 6; i++) {
        int x = i * bw;
        int width = (i == 5) ? (w - x) : bw;
        const GLfloat *c = bars[(i + shift) % 6];
        glScissor(x, 0, width, h);
        glClearColor(c[0], c[1], c[2], 1.0f);
        glClear(GL_COLOR_BUFFER_BIT);
    }

    /* Black inner rectangle approximating SGB 256x224 aspect. */
    {
        int rw = (w * 3) / 5;
        int rh = (h * 7) / 9;
        int rx = (w - rw) / 2;
        int ry = (h - rh) / 2;
        glScissor(rx, ry, rw, rh);
        glClearColor(0.02f, 0.02f, 0.02f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT);
    }

    glDisable(GL_SCISSOR_TEST);
}

int main(int argc, char **argv) {
    NativeFBWindow native;
    EGLDisplay display = EGL_NO_DISPLAY;
    EGLSurface surface = EGL_NO_SURFACE;
    EGLContext context = EGL_NO_CONTEXT;
    EGLConfig config;
    EGLint config_count = 0;
    int padfd = -1;
    unsigned events = 0;
    unsigned frames = 0;
    double start, last, end, next;

    (void)argc;
    (void)argv;

    printf("Ik Core Native N1.7 - Clover EGL lifecycle\n");
    printf("audio       : NO se abre ALSA en esta prueba\n");

    if (get_fb_size(&native) != 0) {
        fprintf(stderr, "ERROR: no se pudo leer /dev/fb0\n");
        return 10;
    }

    printf("display     : %ux%u\n", native.width, native.height);

    {
        static const EGLint cfg_attrs[] = {
            EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
            EGL_SURFACE_TYPE, EGL_WINDOW_BIT,
            EGL_RED_SIZE, 8,
            EGL_GREEN_SIZE, 8,
            EGL_BLUE_SIZE, 8,
            EGL_ALPHA_SIZE, 8,
            EGL_NONE
        };
        static const EGLint ctx_attrs[] = {
            EGL_CONTEXT_CLIENT_VERSION, 2,
            EGL_NONE
        };

        display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
        if (display == EGL_NO_DISPLAY) {
            fprintf(stderr, "ERROR: eglGetDisplay\n");
            return 11;
        }

        if (!eglInitialize(display, NULL, NULL)) {
            fprintf(stderr, "ERROR: eglInitialize 0x%04x\n", eglGetError());
            return 12;
        }

        if (!eglChooseConfig(display, cfg_attrs, &config, 1, &config_count) ||
            config_count < 1) {
            fprintf(stderr, "ERROR: eglChooseConfig 0x%04x\n", eglGetError());
            eglTerminate(display);
            return 13;
        }

        surface = eglCreateWindowSurface(display, config,
                                         (EGLNativeWindowType)&native, NULL);
        if (surface == EGL_NO_SURFACE) {
            fprintf(stderr, "ERROR: eglCreateWindowSurface 0x%04x\n", eglGetError());
            eglTerminate(display);
            return 14;
        }

        context = eglCreateContext(display, config, EGL_NO_CONTEXT, ctx_attrs);
        if (context == EGL_NO_CONTEXT) {
            fprintf(stderr, "ERROR: eglCreateContext 0x%04x\n", eglGetError());
            eglDestroySurface(display, surface);
            eglTerminate(display);
            return 15;
        }

        if (!eglMakeCurrent(display, surface, surface, context)) {
            fprintf(stderr, "ERROR: eglMakeCurrent 0x%04x\n", eglGetError());
            eglDestroyContext(display, context);
            eglDestroySurface(display, surface);
            eglTerminate(display);
            return 16;
        }
    }

    printf("EGL         : OK\n");
    printf("GL vendor   : %s\n", (const char *)glGetString(GL_VENDOR));
    printf("GL renderer : %s\n", (const char *)glGetString(GL_RENDERER));

    glViewport(0, 0, native.width, native.height);

    /* 0 = no vsync wait, we pace ourselves at 60 Hz for this probe. */
    eglSwapInterval(display, 0);

    padfd = open_clovercon();

    printf("benchmark   : 10 s @ objetivo 60 Hz\n");
    fflush(stdout);

    start = last = now_s();
    end = start + 10.0;
    next = start;

    while (now_s() < end) {
        double n = now_s();

        if (n < next) {
            struct timespec req;
            double rem = next - n;
            req.tv_sec = (time_t)rem;
            req.tv_nsec = (long)((rem - (double)req.tv_sec) * 1000000000.0);
            if (req.tv_nsec > 0) nanosleep(&req, NULL);
        }

        draw_test(frames, native.width, native.height);
        if (!eglSwapBuffers(display, surface)) {
            fprintf(stderr, "ERROR: eglSwapBuffers 0x%04x\n", eglGetError());
            break;
        }

        events += poll_pad(padfd);
        frames++;
        next += 1.0 / 60.0;

        n = now_s();
        if (n - last >= 1.0) {
            printf("native FPS  : %.2f (frames=%u)\n",
                   (double)frames / (n - start), frames);
            fflush(stdout);
            last = n;
        }
    }

    if (padfd >= 0) {
        ioctl(padfd, EVIOCGRAB, 0);
        close(padfd);
    }

    /* Clean EGL teardown is the main point of N1.7. */
    eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    if (context != EGL_NO_CONTEXT) eglDestroyContext(display, context);
    if (surface != EGL_NO_SURFACE) eglDestroySurface(display, surface);
    if (display != EGL_NO_DISPLAY) eglTerminate(display);

    printf("\nFINAL\n");
    printf("frames      : %u\n", frames);
    printf("input events: %u\n", events);
    printf("EGL         : liberado correctamente\n");
    printf("audio       : nunca fue abierto por Ik Core\n");
    fflush(stdout);

    return 0;
}
