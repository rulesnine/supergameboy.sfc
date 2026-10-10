/*
 * Ik Core Native N2.11 — real-audio A/B diagnostic + Clover EGL frontend
 *
 * Hardware target: NES Classic / NES Mini (ARMv7 Cortex-A7, Mali-400 MP)
 *
 * N2.11 goals:
 * - keep the validated N1.7 Clover EGL lifecycle
 * - dlopen the Ik Core / SuperSnes9x SGBPACK libretro core directly
 * - load the SGBPACK1 test image without RetroArch
 * - render the core's real video through GLES2
 * - enable libretro audio and deliver real stereo S16_LE samples through ALSA
 * - keep the N2.10 engine unchanged so this is an audio-only A/B
 * - map the Nintendo Clovercon NES pad to libretro joypad input
 *
 * - keep full 256x224 SGB composite output and test real gameplay\n * - allow a clean return with SELECT+START held for 1.5 seconds\n *\n * - open/close ALSA cleanly without stopping or pausing Clover services\n *\n * Audio is intentionally enabled in N2.11 to measure its real cost.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <dlfcn.h>

#include "libretro.h"

#define IKCORE_CORE_PATH "/usr/lib/ikcore/ikcore_sgbpack_libretro.so"
#define IKCORE_STATE_DIR "/var/lib/hakchi/sgb-native-test"
#define IKCORE_DEFAULT_PACK IKCORE_STATE_DIR "/KOF96_SGBPACK_v1_REUPLOAD.sfc"
#define IKCORE_LOG_PATH IKCORE_STATE_DIR "/ikcore-n2_11.log"
#define IKCORE_TEST_SECONDS 120.0
#define IKCORE_EXIT_HOLD_SECONDS 1.5

/* Minimal EGL declarations, loaded dynamically just like N1.7. */
typedef void *EGLDisplay;
typedef void *EGLSurface;
typedef void *EGLContext;
typedef void *EGLConfig;
typedef void *EGLNativeDisplayType;
typedef void *EGLNativeWindowType;
typedef int EGLint;
typedef unsigned int EGLBoolean;

#define EGL_FALSE 0
#define EGL_TRUE 1
#define EGL_DEFAULT_DISPLAY ((EGLNativeDisplayType)0)
#define EGL_NO_DISPLAY ((EGLDisplay)0)
#define EGL_NO_SURFACE ((EGLSurface)0)
#define EGL_NO_CONTEXT ((EGLContext)0)
#define EGL_RENDERABLE_TYPE 0x3040
#define EGL_OPENGL_ES2_BIT 0x0004
#define EGL_SURFACE_TYPE 0x3033
#define EGL_WINDOW_BIT 0x0004
#define EGL_RED_SIZE 0x3024
#define EGL_GREEN_SIZE 0x3023
#define EGL_BLUE_SIZE 0x3022
#define EGL_ALPHA_SIZE 0x3021
#define EGL_NONE 0x3038
#define EGL_CONTEXT_CLIENT_VERSION 0x3098

/* Minimal GLES2 declarations/constants. */
typedef unsigned int GLenum;
typedef unsigned char GLboolean;
typedef unsigned int GLbitfield;
typedef void GLvoid;
typedef signed char GLbyte;
typedef short GLshort;
typedef int GLint;
typedef int GLsizei;
typedef unsigned char GLubyte;
typedef unsigned short GLushort;
typedef unsigned int GLuint;
typedef float GLfloat;
typedef char GLchar;
typedef ptrdiff_t GLsizeiptr;

#define GL_FALSE 0
#define GL_TRUE 1
#define GL_COLOR_BUFFER_BIT 0x00004000
#define GL_DITHER 0x0BD0
#define GL_TEXTURE_2D 0x0DE1
#define GL_TEXTURE0 0x84C0
#define GL_RGB 0x1907
#define GL_RGBA 0x1908
#define GL_UNSIGNED_BYTE 0x1401
#define GL_UNSIGNED_SHORT_5_6_5 0x8363
#define GL_FLOAT 0x1406
#define GL_TRIANGLE_STRIP 0x0005
#define GL_VERTEX_SHADER 0x8B31
#define GL_FRAGMENT_SHADER 0x8B30
#define GL_COMPILE_STATUS 0x8B81
#define GL_LINK_STATUS 0x8B82
#define GL_INFO_LOG_LENGTH 0x8B84
#define GL_TEXTURE_MIN_FILTER 0x2801
#define GL_TEXTURE_MAG_FILTER 0x2800
#define GL_TEXTURE_WRAP_S 0x2802
#define GL_TEXTURE_WRAP_T 0x2803
#define GL_NEAREST 0x2600
#define GL_CLAMP_TO_EDGE 0x812F
#define GL_VENDOR 0x1F00
#define GL_RENDERER 0x1F01

static void *g_libegl = NULL;
static void *g_libgles = NULL;
static void *g_libcore = NULL;
static void *g_libasound = NULL;
static FILE *g_log = NULL;

/* Minimal ALSA ABI loaded dynamically; no build-time libasound dependency. */
typedef struct _snd_pcm snd_pcm_t;
typedef long snd_pcm_sframes_t;
#define SND_PCM_STREAM_PLAYBACK 0
#define SND_PCM_NONBLOCK 0x00000001
#define SND_PCM_ACCESS_RW_INTERLEAVED 3
#define SND_PCM_FORMAT_S16_LE 2
static int (*p_snd_pcm_open)(snd_pcm_t **, const char *, int, int);
static int (*p_snd_pcm_close)(snd_pcm_t *);
static int (*p_snd_pcm_set_params)(snd_pcm_t *, int, int, unsigned, unsigned, int, unsigned);
static snd_pcm_sframes_t (*p_snd_pcm_writei)(snd_pcm_t *, const void *, unsigned long);
static int (*p_snd_pcm_recover)(snd_pcm_t *, int, int);
static int (*p_snd_pcm_prepare)(snd_pcm_t *);
static const char *(*p_snd_strerror)(int);
static snd_pcm_t *g_pcm = NULL;
static int g_alsa_ready = 0;
static unsigned g_audio_rate = 32040;
static unsigned long g_audio_frames_generated = 0;
static unsigned long g_audio_frames_written = 0;
static unsigned long g_audio_frames_dropped = 0;
static unsigned long g_audio_recoveries = 0;

static EGLDisplay (*p_eglGetDisplay)(EGLNativeDisplayType);
static EGLBoolean (*p_eglInitialize)(EGLDisplay,EGLint*,EGLint*);
static EGLBoolean (*p_eglChooseConfig)(EGLDisplay,const EGLint*,EGLConfig*,EGLint,EGLint*);
static EGLSurface (*p_eglCreateWindowSurface)(EGLDisplay,EGLConfig,EGLNativeWindowType,const EGLint*);
static EGLContext (*p_eglCreateContext)(EGLDisplay,EGLConfig,EGLContext,const EGLint*);
static EGLBoolean (*p_eglMakeCurrent)(EGLDisplay,EGLSurface,EGLSurface,EGLContext);
static EGLBoolean (*p_eglSwapBuffers)(EGLDisplay,EGLSurface);
static EGLBoolean (*p_eglSwapInterval)(EGLDisplay,EGLint);
static EGLBoolean (*p_eglDestroyContext)(EGLDisplay,EGLContext);
static EGLBoolean (*p_eglDestroySurface)(EGLDisplay,EGLSurface);
static EGLBoolean (*p_eglTerminate)(EGLDisplay);
static EGLint (*p_eglGetError)(void);

static void (*p_glActiveTexture)(GLenum);
static void (*p_glAttachShader)(GLuint,GLuint);
static void (*p_glBindTexture)(GLenum,GLuint);
static void (*p_glClear)(GLbitfield);
static void (*p_glClearColor)(GLfloat,GLfloat,GLfloat,GLfloat);
static void (*p_glCompileShader)(GLuint);
static GLuint (*p_glCreateProgram)(void);
static GLuint (*p_glCreateShader)(GLenum);
static void (*p_glDeleteProgram)(GLuint);
static void (*p_glDeleteShader)(GLuint);
static void (*p_glDeleteTextures)(GLsizei,const GLuint*);
static void (*p_glDisable)(GLenum);
static void (*p_glDrawArrays)(GLenum,GLint,GLsizei);
static void (*p_glEnableVertexAttribArray)(GLuint);
static void (*p_glGenTextures)(GLsizei,GLuint*);
static GLint (*p_glGetAttribLocation)(GLuint,const GLchar*);
static void (*p_glGetProgramInfoLog)(GLuint,GLsizei,GLsizei*,GLchar*);
static void (*p_glGetProgramiv)(GLuint,GLenum,GLint*);
static void (*p_glGetShaderInfoLog)(GLuint,GLsizei,GLsizei*,GLchar*);
static void (*p_glGetShaderiv)(GLuint,GLenum,GLint*);
static const GLubyte *(*p_glGetString)(GLenum);
static GLint (*p_glGetUniformLocation)(GLuint,const GLchar*);
static void (*p_glLinkProgram)(GLuint);
static void (*p_glShaderSource)(GLuint,GLsizei,const GLchar* const*,const GLint*);
static void (*p_glTexImage2D)(GLenum,GLint,GLint,GLsizei,GLsizei,GLint,GLenum,GLenum,const GLvoid*);
static void (*p_glTexSubImage2D)(GLenum,GLint,GLint,GLint,GLsizei,GLsizei,GLenum,GLenum,const GLvoid*);
static void (*p_glTexParameteri)(GLenum,GLenum,GLint);
static void (*p_glUniform1i)(GLint,GLint);
static void (*p_glUseProgram)(GLuint);
static void (*p_glVertexAttribPointer)(GLuint,GLint,GLenum,GLboolean,GLsizei,const GLvoid*);
static void (*p_glViewport)(GLint,GLint,GLsizei,GLsizei);

#define eglGetDisplay p_eglGetDisplay
#define eglInitialize p_eglInitialize
#define eglChooseConfig p_eglChooseConfig
#define eglCreateWindowSurface p_eglCreateWindowSurface
#define eglCreateContext p_eglCreateContext
#define eglMakeCurrent p_eglMakeCurrent
#define eglSwapBuffers p_eglSwapBuffers
#define eglSwapInterval p_eglSwapInterval
#define eglDestroyContext p_eglDestroyContext
#define eglDestroySurface p_eglDestroySurface
#define eglTerminate p_eglTerminate
#define eglGetError p_eglGetError

#define glActiveTexture p_glActiveTexture
#define glAttachShader p_glAttachShader
#define glBindTexture p_glBindTexture
#define glClear p_glClear
#define glClearColor p_glClearColor
#define glCompileShader p_glCompileShader
#define glCreateProgram p_glCreateProgram
#define glCreateShader p_glCreateShader
#define glDeleteProgram p_glDeleteProgram
#define glDeleteShader p_glDeleteShader
#define glDeleteTextures p_glDeleteTextures
#define glDisable p_glDisable
#define glDrawArrays p_glDrawArrays
#define glEnableVertexAttribArray p_glEnableVertexAttribArray
#define glGenTextures p_glGenTextures
#define glGetAttribLocation p_glGetAttribLocation
#define glGetProgramInfoLog p_glGetProgramInfoLog
#define glGetProgramiv p_glGetProgramiv
#define glGetShaderInfoLog p_glGetShaderInfoLog
#define glGetShaderiv p_glGetShaderiv
#define glGetString p_glGetString
#define glGetUniformLocation p_glGetUniformLocation
#define glLinkProgram p_glLinkProgram
#define glShaderSource p_glShaderSource
#define glTexImage2D p_glTexImage2D
#define glTexSubImage2D p_glTexSubImage2D
#define glTexParameteri p_glTexParameteri
#define glUniform1i p_glUniform1i
#define glUseProgram p_glUseProgram
#define glVertexAttribPointer p_glVertexAttribPointer
#define glViewport p_glViewport

typedef struct {
    unsigned short width;
    unsigned short height;
} NativeFBWindow;

static NativeFBWindow g_native;
static EGLDisplay g_display = EGL_NO_DISPLAY;
static EGLSurface g_surface = EGL_NO_SURFACE;
static EGLContext g_context = EGL_NO_CONTEXT;
static GLuint g_program = 0;
static GLuint g_texture = 0;
static GLint g_attr_pos = -1;
static GLint g_attr_uv = -1;
static GLint g_uniform_tex = -1;
static uint8_t *g_rgba = NULL;
static size_t g_rgba_cap = 0;
static uint8_t *g_rgb565_pack = NULL;
static size_t g_rgb565_pack_cap = 0;
static enum retro_pixel_format g_pixel_format = RETRO_PIXEL_FORMAT_0RGB1555;
static unsigned g_frame_w = 0;
static unsigned g_frame_h = 0;
static unsigned g_tex_w = 0;
static unsigned g_tex_h = 0;
static int g_tex_rgb565 = 0;
static float g_core_aspect = 4.0f / 3.0f;
static unsigned long g_video_frames = 0;
static unsigned long g_audio_frames_discarded = 0;
static unsigned long g_input_events = 0;
static unsigned long g_late_frames = 0;
static double g_video_seconds = 0.0;
static double g_work_seconds = 0.0;
static size_t g_first_pitch = 0;
static int g_swap_failed = 0;
static int g_user_exit = 0;
static int g_shutdown_requested = 0;
static int g_padfd = -1;
static uint16_t g_pad_mask = 0;

/* Libretro entry points loaded from the core. */
static unsigned (*core_retro_api_version)(void);
static void (*core_retro_set_environment)(retro_environment_t);
static void (*core_retro_set_video_refresh)(retro_video_refresh_t);
static void (*core_retro_set_audio_sample)(retro_audio_sample_t);
static void (*core_retro_set_audio_sample_batch)(retro_audio_sample_batch_t);
static void (*core_retro_set_input_poll)(retro_input_poll_t);
static void (*core_retro_set_input_state)(retro_input_state_t);
static void (*core_retro_init)(void);
static void (*core_retro_deinit)(void);
static void (*core_retro_get_system_info)(struct retro_system_info *);
static void (*core_retro_get_system_av_info)(struct retro_system_av_info *);
static bool (*core_retro_load_game)(const struct retro_game_info *);
static void (*core_retro_unload_game)(void);
static void (*core_retro_run)(void);
static void (*core_retro_set_controller_port_device)(unsigned,unsigned);

static double now_s(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1000000000.0;
}

static void sleep_s(double seconds)
{
    struct timespec req, rem;
    if (seconds <= 0.0) return;

    req.tv_sec = (time_t)seconds;
    req.tv_nsec = (long)((seconds - (double)req.tv_sec) * 1000000000.0);
    if (req.tv_nsec < 0) req.tv_nsec = 0;
    if (req.tv_nsec > 999999999L) req.tv_nsec = 999999999L;

    while (nanosleep(&req, &rem) < 0 && errno == EINTR)
        req = rem;
}

static void log_open(void)
{
    mkdir(IKCORE_STATE_DIR, 0755);
    g_log = fopen(IKCORE_LOG_PATH, "w");
}

static void log_printf(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    vfprintf(stdout, fmt, ap);
    va_end(ap);
    fflush(stdout);

    if (g_log) {
        va_start(ap, fmt);
        vfprintf(g_log, fmt, ap);
        va_end(ap);
        fflush(g_log);
    }
}

static void core_log(enum retro_log_level level, const char *fmt, ...)
{
    const char *tag = "INFO";
    va_list ap;
    switch (level) {
        case RETRO_LOG_DEBUG: tag = "DEBUG"; break;
        case RETRO_LOG_INFO:  tag = "INFO"; break;
        case RETRO_LOG_WARN:  tag = "WARN"; break;
        case RETRO_LOG_ERROR: tag = "ERROR"; break;
        default: break;
    }
    fprintf(stdout, "core[%s]   : ", tag);
    va_start(ap, fmt);
    vfprintf(stdout, fmt, ap);
    va_end(ap);
    fflush(stdout);

    if (g_log) {
        fprintf(g_log, "core[%s]   : ", tag);
        va_start(ap, fmt);
        vfprintf(g_log, fmt, ap);
        va_end(ap);
        fflush(g_log);
    }
}

static int get_fb_size(NativeFBWindow *w)
{
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

static int load_gl(void)
{
#define LOAD_EGL(name) do { *(void **)(&p_##name) = dlsym(g_libegl, #name); if (!p_##name) { log_printf("ERROR EGL  : falta %s\n", #name); return -1; } } while (0)
#define LOAD_GL(name) do { *(void **)(&p_##name) = dlsym(g_libgles, #name); if (!p_##name) { log_printf("ERROR GLES : falta %s\n", #name); return -1; } } while (0)
    g_libegl = dlopen("libEGL.so", RTLD_NOW | RTLD_LOCAL);
    if (!g_libegl) g_libegl = dlopen("libEGL.so.1", RTLD_NOW | RTLD_LOCAL);
    g_libgles = dlopen("libGLESv2.so", RTLD_NOW | RTLD_LOCAL);
    if (!g_libgles) g_libgles = dlopen("libGLESv2.so.2", RTLD_NOW | RTLD_LOCAL);
    if (!g_libegl || !g_libgles) {
        log_printf("ERROR GL   : %s\n", dlerror());
        return -1;
    }

    LOAD_EGL(eglGetDisplay);
    LOAD_EGL(eglInitialize);
    LOAD_EGL(eglChooseConfig);
    LOAD_EGL(eglCreateWindowSurface);
    LOAD_EGL(eglCreateContext);
    LOAD_EGL(eglMakeCurrent);
    LOAD_EGL(eglSwapBuffers);
    LOAD_EGL(eglSwapInterval);
    LOAD_EGL(eglDestroyContext);
    LOAD_EGL(eglDestroySurface);
    LOAD_EGL(eglTerminate);
    LOAD_EGL(eglGetError);

    LOAD_GL(glActiveTexture);
    LOAD_GL(glAttachShader);
    LOAD_GL(glBindTexture);
    LOAD_GL(glClear);
    LOAD_GL(glClearColor);
    LOAD_GL(glCompileShader);
    LOAD_GL(glCreateProgram);
    LOAD_GL(glCreateShader);
    LOAD_GL(glDeleteProgram);
    LOAD_GL(glDeleteShader);
    LOAD_GL(glDeleteTextures);
    LOAD_GL(glDisable);
    LOAD_GL(glDrawArrays);
    LOAD_GL(glEnableVertexAttribArray);
    LOAD_GL(glGenTextures);
    LOAD_GL(glGetAttribLocation);
    LOAD_GL(glGetProgramInfoLog);
    LOAD_GL(glGetProgramiv);
    LOAD_GL(glGetShaderInfoLog);
    LOAD_GL(glGetShaderiv);
    LOAD_GL(glGetString);
    LOAD_GL(glGetUniformLocation);
    LOAD_GL(glLinkProgram);
    LOAD_GL(glShaderSource);
    LOAD_GL(glTexImage2D);
    LOAD_GL(glTexSubImage2D);
    LOAD_GL(glTexParameteri);
    LOAD_GL(glUniform1i);
    LOAD_GL(glUseProgram);
    LOAD_GL(glVertexAttribPointer);
    LOAD_GL(glViewport);
    return 0;
}

static GLuint compile_shader(GLenum type, const char *src)
{
    GLuint sh = glCreateShader(type);
    GLint ok = 0;
    if (!sh) return 0;
    glShaderSource(sh, 1, &src, NULL);
    glCompileShader(sh);
    glGetShaderiv(sh, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char buf[1024];
        GLsizei n = 0;
        buf[0] = '\0';
        glGetShaderInfoLog(sh, sizeof(buf) - 1, &n, buf);
        buf[(n >= 0 && n < (GLsizei)sizeof(buf)) ? n : (GLsizei)sizeof(buf)-1] = '\0';
        log_printf("ERROR shader: %s\n", buf);
        glDeleteShader(sh);
        return 0;
    }
    return sh;
}

static int init_video_pipeline(void)
{
    static const char *vs_src =
        "attribute vec2 aPos;\n"
        "attribute vec2 aUV;\n"
        "varying vec2 vUV;\n"
        "void main(){ gl_Position=vec4(aPos,0.0,1.0); vUV=aUV; }\n";
    static const char *fs_src =
        "precision mediump float;\n"
        "varying vec2 vUV;\n"
        "uniform sampler2D uTex;\n"
        "void main(){ gl_FragColor=texture2D(uTex,vUV); }\n";
    GLuint vs = 0, fs = 0;
    GLint ok = 0;

    vs = compile_shader(GL_VERTEX_SHADER, vs_src);
    fs = compile_shader(GL_FRAGMENT_SHADER, fs_src);
    if (!vs || !fs) goto fail;

    g_program = glCreateProgram();
    if (!g_program) goto fail;
    glAttachShader(g_program, vs);
    glAttachShader(g_program, fs);
    glLinkProgram(g_program);
    glGetProgramiv(g_program, GL_LINK_STATUS, &ok);
    if (!ok) {
        char buf[1024];
        GLsizei n = 0;
        buf[0] = '\0';
        glGetProgramInfoLog(g_program, sizeof(buf) - 1, &n, buf);
        buf[(n >= 0 && n < (GLsizei)sizeof(buf)) ? n : (GLsizei)sizeof(buf)-1] = '\0';
        log_printf("ERROR link  : %s\n", buf);
        goto fail;
    }

    g_attr_pos = glGetAttribLocation(g_program, "aPos");
    g_attr_uv = glGetAttribLocation(g_program, "aUV");
    g_uniform_tex = glGetUniformLocation(g_program, "uTex");
    if (g_attr_pos < 0 || g_attr_uv < 0 || g_uniform_tex < 0) goto fail;

    glGenTextures(1, &g_texture);
    if (!g_texture) goto fail;
    glBindTexture(GL_TEXTURE_2D, g_texture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);

    glDeleteShader(vs);
    glDeleteShader(fs);
    return 0;

fail:
    if (vs) glDeleteShader(vs);
    if (fs) glDeleteShader(fs);
    return -1;
}

static int init_egl(void)
{
    EGLConfig config;
    EGLint count = 0;
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

    if (load_gl() != 0) return -1;
    if (get_fb_size(&g_native) != 0) {
        log_printf("ERROR      : no se pudo leer /dev/fb0\n");
        return -1;
    }

    g_display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    if (g_display == EGL_NO_DISPLAY) return -1;
    if (!eglInitialize(g_display, NULL, NULL)) {
        log_printf("ERROR EGL  : eglInitialize 0x%04x\n", eglGetError());
        return -1;
    }
    if (!eglChooseConfig(g_display, cfg_attrs, &config, 1, &count) || count < 1) {
        log_printf("ERROR EGL  : eglChooseConfig 0x%04x\n", eglGetError());
        return -1;
    }
    g_surface = eglCreateWindowSurface(g_display, config, (EGLNativeWindowType)&g_native, NULL);
    if (g_surface == EGL_NO_SURFACE) {
        log_printf("ERROR EGL  : eglCreateWindowSurface 0x%04x\n", eglGetError());
        return -1;
    }
    g_context = eglCreateContext(g_display, config, EGL_NO_CONTEXT, ctx_attrs);
    if (g_context == EGL_NO_CONTEXT) {
        log_printf("ERROR EGL  : eglCreateContext 0x%04x\n", eglGetError());
        return -1;
    }
    if (!eglMakeCurrent(g_display, g_surface, g_surface, g_context)) {
        log_printf("ERROR EGL  : eglMakeCurrent 0x%04x\n", eglGetError());
        return -1;
    }

    eglSwapInterval(g_display, 0); /* unpaced: N2 measures full-engine throughput */
    glDisable(GL_DITHER);
    glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);
    eglSwapBuffers(g_display, g_surface);

    if (init_video_pipeline() != 0) return -1;

    log_printf("display     : %ux%u\n", g_native.width, g_native.height);
    log_printf("EGL         : OK\n");
    log_printf("GL vendor   : %s\n", (const char *)glGetString(GL_VENDOR));
    log_printf("GL renderer : %s\n", (const char *)glGetString(GL_RENDERER));
    return 0;
}

static void destroy_egl(void)
{
    if (g_texture && glDeleteTextures) glDeleteTextures(1, &g_texture);
    g_texture = 0;
    if (g_program && glDeleteProgram) glDeleteProgram(g_program);
    g_program = 0;
    free(g_rgba);
    g_rgba = NULL;
    g_rgba_cap = 0;
    free(g_rgb565_pack);
    g_rgb565_pack = NULL;
    g_rgb565_pack_cap = 0;

    if (g_display != EGL_NO_DISPLAY && eglMakeCurrent)
        eglMakeCurrent(g_display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    if (g_context != EGL_NO_CONTEXT && eglDestroyContext)
        eglDestroyContext(g_display, g_context);
    if (g_surface != EGL_NO_SURFACE && eglDestroySurface)
        eglDestroySurface(g_display, g_surface);
    if (g_display != EGL_NO_DISPLAY && eglTerminate)
        eglTerminate(g_display);
    g_context = EGL_NO_CONTEXT;
    g_surface = EGL_NO_SURFACE;
    g_display = EGL_NO_DISPLAY;

    if (g_libgles) dlclose(g_libgles);
    if (g_libegl) dlclose(g_libegl);
    g_libgles = NULL;
    g_libegl = NULL;
}

static int open_clovercon(void)
{
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
            log_printf("controller  : %s [%s]\n", path, name);
            if (ioctl(fd, EVIOCGRAB, 1) == 0)
                log_printf("controller  : EVIOCGRAB OK\n");
            else
                log_printf("controller  : EVIOCGRAB fallo: %s\n", strerror(errno));
            return fd;
        }
        close(fd);
    }
    log_printf("controller  : no encontrado\n");
    return -1;
}

static void set_retro_button(unsigned id, int pressed)
{
    uint16_t bit;
    if (id > 15) return;
    bit = (uint16_t)(1u << id);
    if (pressed) g_pad_mask |= bit;
    else g_pad_mask &= (uint16_t)~bit;
}

static void poll_clover_events(void)
{
    struct input_event ev[32];
    ssize_t got;
    if (g_padfd < 0) return;

    while ((got = read(g_padfd, ev, sizeof(ev))) > 0) {
        size_t i;
        size_t count = (size_t)got / sizeof(ev[0]);
        for (i = 0; i < count; i++) {
            int down;
            if (ev[i].type != EV_KEY) continue;
            down = ev[i].value != 0;
            switch (ev[i].code) {
                case BTN_A: set_retro_button(RETRO_DEVICE_ID_JOYPAD_A, down); break;
                case BTN_B: set_retro_button(RETRO_DEVICE_ID_JOYPAD_B, down); break;
                case BTN_SELECT: set_retro_button(RETRO_DEVICE_ID_JOYPAD_SELECT, down); break;
                case BTN_START: set_retro_button(RETRO_DEVICE_ID_JOYPAD_START, down); break;
                case BTN_TRIGGER_HAPPY1: set_retro_button(RETRO_DEVICE_ID_JOYPAD_LEFT, down); break;
                case BTN_TRIGGER_HAPPY2: set_retro_button(RETRO_DEVICE_ID_JOYPAD_RIGHT, down); break;
                case BTN_TRIGGER_HAPPY3: set_retro_button(RETRO_DEVICE_ID_JOYPAD_UP, down); break;
                case BTN_TRIGGER_HAPPY4: set_retro_button(RETRO_DEVICE_ID_JOYPAD_DOWN, down); break;
                default: break;
            }
            g_input_events++;
        }
    }
}

static void input_poll_cb(void)
{
    poll_clover_events();
}

static int16_t input_state_cb(unsigned port, unsigned device, unsigned index, unsigned id)
{
    (void)index;
    if (port != 0 || device != RETRO_DEVICE_JOYPAD || id > 15) return 0;
    return (g_pad_mask & (uint16_t)(1u << id)) ? 1 : 0;
}

static int load_alsa(void)
{
#define LOAD_ALSA(name) do { *(void **)(&p_##name) = dlsym(g_libasound, #name); if (!p_##name) { log_printf("ERROR ALSA  : falta %s\n", #name); return -1; } } while (0)
    g_libasound = dlopen("libasound.so.2", RTLD_NOW | RTLD_LOCAL);
    if (!g_libasound) g_libasound = dlopen("libasound.so", RTLD_NOW | RTLD_LOCAL);
    if (!g_libasound) {
        log_printf("ERROR ALSA  : dlopen %s\n", dlerror());
        return -1;
    }
    LOAD_ALSA(snd_pcm_open);
    LOAD_ALSA(snd_pcm_close);
    LOAD_ALSA(snd_pcm_set_params);
    LOAD_ALSA(snd_pcm_writei);
    LOAD_ALSA(snd_pcm_recover);
    LOAD_ALSA(snd_pcm_prepare);
    LOAD_ALSA(snd_strerror);
    return 0;
#undef LOAD_ALSA
}

static int init_alsa(unsigned rate)
{
    int rc;
    const char *device = "default";
    if (load_alsa() != 0) return -1;

    rc = p_snd_pcm_open(&g_pcm, device, SND_PCM_STREAM_PLAYBACK, SND_PCM_NONBLOCK);
    if (rc < 0) {
        device = "hw:0,0";
        rc = p_snd_pcm_open(&g_pcm, device, SND_PCM_STREAM_PLAYBACK, SND_PCM_NONBLOCK);
    }
    if (rc < 0 || !g_pcm) {
        log_printf("ERROR ALSA  : snd_pcm_open fallo: %s\n",
                   p_snd_strerror ? p_snd_strerror(rc) : "?");
        g_pcm = NULL;
        return -1;
    }

    rc = p_snd_pcm_set_params(g_pcm,
                              SND_PCM_FORMAT_S16_LE,
                              SND_PCM_ACCESS_RW_INTERLEAVED,
                              2, rate, 1, 100000);
    if (rc < 0) {
        log_printf("ERROR ALSA  : set_params %u Hz fallo: %s\n",
                   rate, p_snd_strerror ? p_snd_strerror(rc) : "?");
        p_snd_pcm_close(g_pcm);
        g_pcm = NULL;
        return -1;
    }

    p_snd_pcm_prepare(g_pcm);
    g_audio_rate = rate;
    g_alsa_ready = 1;
    log_printf("ALSA        : OK, %s, stereo S16_LE, %u Hz, nonblocking\n",
               device, rate);
    return 0;
}

static void close_alsa(void)
{
    if (g_pcm) {
        p_snd_pcm_close(g_pcm);
        g_pcm = NULL;
    }
    g_alsa_ready = 0;
    if (g_libasound) {
        dlclose(g_libasound);
        g_libasound = NULL;
    }
}

static size_t audio_batch_cb(const int16_t *data, size_t frames)
{
    snd_pcm_sframes_t wrote;
    g_audio_frames_generated += (unsigned long)frames;

    if (!g_alsa_ready || !g_pcm || !data || frames == 0) {
        g_audio_frames_dropped += (unsigned long)frames;
        return frames;
    }

    wrote = p_snd_pcm_writei(g_pcm, data, (unsigned long)frames);
    if (wrote < 0) {
        if (wrote == -EAGAIN) {
            g_audio_frames_dropped += (unsigned long)frames;
            return frames;
        }
        if (p_snd_pcm_recover(g_pcm, (int)wrote, 1) >= 0) {
            g_audio_recoveries++;
            wrote = p_snd_pcm_writei(g_pcm, data, (unsigned long)frames);
        }
    }

    if (wrote > 0) {
        size_t n = (size_t)wrote > frames ? frames : (size_t)wrote;
        g_audio_frames_written += (unsigned long)n;
        if (n < frames) g_audio_frames_dropped += (unsigned long)(frames - n);
    } else {
        g_audio_frames_dropped += (unsigned long)frames;
    }

    /* Libretro callback contract: samples were accepted by the frontend.
       We never block the emulation thread waiting for the ALSA device. */
    return frames;
}

static void audio_sample_cb(int16_t left, int16_t right)
{
    int16_t pair[2];
    pair[0] = left;
    pair[1] = right;
    (void)audio_batch_cb(pair, 1);
}

static bool environ_cb(unsigned cmd, void *data)
{
    switch (cmd) {
        case RETRO_ENVIRONMENT_GET_CAN_DUPE:
            *(bool *)data = true;
            return true;
        case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
        case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
            *(const char **)data = IKCORE_STATE_DIR;
            return true;
        case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT: {
            enum retro_pixel_format fmt = *(const enum retro_pixel_format *)data;
            if (fmt == RETRO_PIXEL_FORMAT_0RGB1555 ||
                fmt == RETRO_PIXEL_FORMAT_RGB565 ||
                fmt == RETRO_PIXEL_FORMAT_XRGB8888) {
                g_pixel_format = fmt;
                log_printf("pixel fmt   : %d\n", (int)fmt);
                return true;
            }
            return false;
        }
        case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
            *(bool *)data = false;
            return true;
        case RETRO_ENVIRONMENT_GET_VARIABLE:
            return false; /* core falls back to its safe defaults */
        case RETRO_ENVIRONMENT_GET_LOG_INTERFACE:
            ((struct retro_log_callback *)data)->log = core_log;
            return true;
        case RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE:
            *(int *)data = 3; /* video + audio enabled */
            return true;
        case RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION:
            *(unsigned *)data = 0; /* ask core to use legacy SET_VARIABLES */
            return true;
        case RETRO_ENVIRONMENT_GET_LANGUAGE:
            *(unsigned *)data = RETRO_LANGUAGE_ENGLISH;
            return true;
        case RETRO_ENVIRONMENT_SET_GEOMETRY: {
            const struct retro_game_geometry *geo = (const struct retro_game_geometry *)data;
            if (geo && geo->aspect_ratio > 0.1f) g_core_aspect = geo->aspect_ratio;
            return true;
        }
        case RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO: {
            const struct retro_system_av_info *av = (const struct retro_system_av_info *)data;
            if (av && av->geometry.aspect_ratio > 0.1f) g_core_aspect = av->geometry.aspect_ratio;
            return true;
        }
        case RETRO_ENVIRONMENT_SHUTDOWN:
            g_shutdown_requested = 1;
            return true;
        case RETRO_ENVIRONMENT_GET_RUMBLE_INTERFACE:
        case RETRO_ENVIRONMENT_GET_VFS_INTERFACE:
            return false;
        case RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME:
        case RETRO_ENVIRONMENT_SET_SUBSYSTEM_INFO:
        case RETRO_ENVIRONMENT_SET_CONTROLLER_INFO:
        case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
        case RETRO_ENVIRONMENT_SET_VARIABLES:
        case RETRO_ENVIRONMENT_SET_SUPPORT_ACHIEVEMENTS:
        case RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL:
            return true;
        default:
            return false;
    }
}

static void convert_frame_rgba(const void *data, unsigned w, unsigned h, size_t pitch)
{
    size_t need = (size_t)w * (size_t)h * 4u;
    unsigned y, x;
    if (need > g_rgba_cap) {
        uint8_t *p = (uint8_t *)realloc(g_rgba, need);
        if (!p) return;
        g_rgba = p;
        g_rgba_cap = need;
    }

    if (g_pixel_format == RETRO_PIXEL_FORMAT_XRGB8888) {
        for (y = 0; y < h; y++) {
            const uint32_t *src = (const uint32_t *)((const uint8_t *)data + (size_t)y * pitch);
            uint8_t *dst = g_rgba + (size_t)y * w * 4u;
            for (x = 0; x < w; x++) {
                uint32_t p = src[x];
                dst[x*4+0] = (uint8_t)((p >> 16) & 0xff);
                dst[x*4+1] = (uint8_t)((p >> 8) & 0xff);
                dst[x*4+2] = (uint8_t)(p & 0xff);
                dst[x*4+3] = 0xff;
            }
        }
    } else {
        for (y = 0; y < h; y++) {
            const uint16_t *src = (const uint16_t *)((const uint8_t *)data + (size_t)y * pitch);
            uint8_t *dst = g_rgba + (size_t)y * w * 4u;
            for (x = 0; x < w; x++) {
                uint16_t p = src[x];
                if (g_pixel_format == RETRO_PIXEL_FORMAT_RGB565) {
                    unsigned r = (p >> 11) & 31u;
                    unsigned g = (p >> 5) & 63u;
                    unsigned b = p & 31u;
                    dst[x*4+0] = (uint8_t)((r << 3) | (r >> 2));
                    dst[x*4+1] = (uint8_t)((g << 2) | (g >> 4));
                    dst[x*4+2] = (uint8_t)((b << 3) | (b >> 2));
                } else {
                    unsigned r = (p >> 10) & 31u;
                    unsigned g = (p >> 5) & 31u;
                    unsigned b = p & 31u;
                    dst[x*4+0] = (uint8_t)((r << 3) | (r >> 2));
                    dst[x*4+1] = (uint8_t)((g << 3) | (g >> 2));
                    dst[x*4+2] = (uint8_t)((b << 3) | (b >> 2));
                }
                dst[x*4+3] = 0xff;
            }
        }
    }
}

static void draw_texture_frame(unsigned w, unsigned h)
{
    /* Triangle strip, vertically flipped so top row remains top on screen. */
    static const GLfloat pos[] = {
        -1.0f, -1.0f,
         1.0f, -1.0f,
        -1.0f,  1.0f,
         1.0f,  1.0f
    };
    static const GLfloat uv[] = {
         0.0f, 1.0f,
         1.0f, 1.0f,
         0.0f, 0.0f,
         1.0f, 0.0f
    };
    float aspect = g_core_aspect > 0.1f ? g_core_aspect : ((float)w / (float)h);
    float screen_aspect = (float)g_native.width / (float)g_native.height;
    int vx = 0, vy = 0, vw = g_native.width, vh = g_native.height;

    if (screen_aspect > aspect) {
        vw = (int)((float)g_native.height * aspect + 0.5f);
        vx = ((int)g_native.width - vw) / 2;
    } else {
        vh = (int)((float)g_native.width / aspect + 0.5f);
        vy = ((int)g_native.height - vh) / 2;
    }

    glViewport(0, 0, g_native.width, g_native.height);
    glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);
    glViewport(vx, vy, vw, vh);

    glUseProgram(g_program);
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, g_texture);
    glUniform1i(g_uniform_tex, 0);
    glEnableVertexAttribArray((GLuint)g_attr_pos);
    glEnableVertexAttribArray((GLuint)g_attr_uv);
    glVertexAttribPointer((GLuint)g_attr_pos, 2, GL_FLOAT, GL_FALSE, 0, pos);
    glVertexAttribPointer((GLuint)g_attr_uv, 2, GL_FLOAT, GL_FALSE, 0, uv);
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
}

static const void *pack_rgb565_rows(const void *data, unsigned w, unsigned h, size_t pitch)
{
    size_t tight_pitch = (size_t)w * 2u;
    size_t need = tight_pitch * (size_t)h;
    unsigned y;

    if (pitch == tight_pitch)
        return data;

    if (need > g_rgb565_pack_cap) {
        uint8_t *p = (uint8_t *)realloc(g_rgb565_pack, need);
        if (!p) return NULL;
        g_rgb565_pack = p;
        g_rgb565_pack_cap = need;
    }

    for (y = 0; y < h; y++) {
        memcpy(g_rgb565_pack + (size_t)y * tight_pitch,
               (const uint8_t *)data + (size_t)y * pitch,
               tight_pitch);
    }

    return g_rgb565_pack;
}

static void upload_rgb565_direct(const void *data, unsigned w, unsigned h)
{
    glBindTexture(GL_TEXTURE_2D, g_texture);
    if (g_tex_w != w || g_tex_h != h || !g_tex_rgb565) {
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, (GLsizei)w, (GLsizei)h, 0,
                     GL_RGB, GL_UNSIGNED_SHORT_5_6_5, data);
        g_tex_w = w;
        g_tex_h = h;
        g_tex_rgb565 = 1;
    } else {
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, (GLsizei)w, (GLsizei)h,
                        GL_RGB, GL_UNSIGNED_SHORT_5_6_5, data);
    }
}

static void upload_rgba_fallback(unsigned w, unsigned h)
{
    glBindTexture(GL_TEXTURE_2D, g_texture);
    if (g_tex_w != w || g_tex_h != h || g_tex_rgb565) {
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, (GLsizei)w, (GLsizei)h, 0,
                     GL_RGBA, GL_UNSIGNED_BYTE, g_rgba);
        g_tex_w = w;
        g_tex_h = h;
        g_tex_rgb565 = 0;
    } else {
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, (GLsizei)w, (GLsizei)h,
                        GL_RGBA, GL_UNSIGNED_BYTE, g_rgba);
    }
}

static void video_cb(const void *data, unsigned width, unsigned height, size_t pitch)
{
    double t0 = now_s();

    if (!data || width == 0 || height == 0) {
        /* libretro duplicate frame: redraw the already uploaded texture. */
        if (g_frame_w && g_frame_h)
            draw_texture_frame(g_frame_w, g_frame_h);
        if (!eglSwapBuffers(g_display, g_surface)) g_swap_failed = 1;
        g_video_frames++;
        g_video_seconds += now_s() - t0;
        return;
    }

    g_frame_w = width;
    g_frame_h = height;
    if (!g_first_pitch) g_first_pitch = pitch;

    /*
     * N2.2 RGB565 path:
     * SuperSnes9x already renders in the exact 16-bit format Mali accepts.
     * If the core pitch is wider than the visible 256 pixels, only compact the
     * rows with memcpy; never expand every pixel to 32-bit RGBA on Cortex-A7.
     */
    if (g_pixel_format == RETRO_PIXEL_FORMAT_RGB565) {
        const void *packed = pack_rgb565_rows(data, width, height, pitch);
        if (!packed) {
            g_video_seconds += now_s() - t0;
            return;
        }
        upload_rgb565_direct(packed, width, height);
    } else {
        convert_frame_rgba(data, width, height, pitch);
        if (!g_rgba) {
            g_video_seconds += now_s() - t0;
            return;
        }
        upload_rgba_fallback(width, height);
    }

    draw_texture_frame(width, height);
    if (!eglSwapBuffers(g_display, g_surface)) {
        log_printf("ERROR EGL  : eglSwapBuffers 0x%04x\n", eglGetError());
        g_swap_failed = 1;
    }
    g_video_frames++;
    g_video_seconds += now_s() - t0;
}

static int load_core(void)
{
#define LOAD_CORE(name) do { *(void **)(&core_##name) = dlsym(g_libcore, #name); if (!core_##name) { log_printf("ERROR core : falta %s\n", #name); return -1; } } while (0)
    g_libcore = dlopen(IKCORE_CORE_PATH, RTLD_NOW | RTLD_LOCAL);
    if (!g_libcore) {
        log_printf("ERROR core : dlopen %s\n", dlerror());
        return -1;
    }
    LOAD_CORE(retro_api_version);
    LOAD_CORE(retro_set_environment);
    LOAD_CORE(retro_set_video_refresh);
    LOAD_CORE(retro_set_audio_sample);
    LOAD_CORE(retro_set_audio_sample_batch);
    LOAD_CORE(retro_set_input_poll);
    LOAD_CORE(retro_set_input_state);
    LOAD_CORE(retro_init);
    LOAD_CORE(retro_deinit);
    LOAD_CORE(retro_get_system_info);
    LOAD_CORE(retro_get_system_av_info);
    LOAD_CORE(retro_load_game);
    LOAD_CORE(retro_unload_game);
    LOAD_CORE(retro_run);
    LOAD_CORE(retro_set_controller_port_device);

    if (core_retro_api_version() != RETRO_API_VERSION) {
        log_printf("ERROR core : libretro API %u, esperado %u\n",
                   core_retro_api_version(), (unsigned)RETRO_API_VERSION);
        return -1;
    }
    return 0;
}

static void close_core(void)
{
    if (g_libcore) dlclose(g_libcore);
    g_libcore = NULL;
}

static int has_rom_extension(const char *path)
{
    const char *dot;
    if (!path) return 0;
    dot = strrchr(path, '.');
    if (!dot) return 0;
    return strcasecmp(dot, ".sfc") == 0 ||
           strcasecmp(dot, ".smc") == 0;
}

static const char *select_pack_path(int argc, char **argv)
{
    int i;

    /*
     * Clover/Hakchi appends launcher flags such as --save-on-quit to Exec.
     * Those are frontend options, not ROM paths. N2 previously treated argv[1]
     * as the SGBPACK unconditionally, so Clover launch tried to open the literal
     * filename "--save-on-quit" and immediately returned to the menu.
     *
     * Only accept an explicit ROM-looking positional argument. With no such
     * argument, use the installed/default SGBPACK test image.
     */
    for (i = 1; i < argc; i++) {
        if (!argv[i] || !argv[i][0]) continue;
        if (argv[i][0] == '-') {
            log_printf("launcher arg: ignorado %s\n", argv[i]);
            continue;
        }
        if (has_rom_extension(argv[i])) return argv[i];
    }

    return IKCORE_DEFAULT_PACK;
}

int main(int argc, char **argv)
{
    const char *pack_path;
    struct retro_system_info sysinfo;
    struct retro_system_av_info avinfo;
    struct retro_game_info game;
    double start = 0.0, last = 0.0, end = 0.0, test_elapsed = 0.0;
    double target_fps = 60.0988, frame_period = 1.0 / 60.0988;
    double deadline = 0.0, exit_combo_since = 0.0;
    unsigned long run_frames = 0, last_run_frames = 0;
    int core_inited = 0;
    int game_loaded = 0;
    int success = 0;

    log_open();
    pack_path = select_pack_path(argc, argv);
    log_printf("Ik Core Native N2.11 - real audio A/B\n");
    log_printf("audio       : ACTIVADO; salida ALSA real\n");
    log_printf("core        : %s\n", IKCORE_CORE_PATH);
    log_printf("core mode   : N2.10 sin cambios + audio real\n");
    log_printf("SGBPACK     : %s\n", pack_path);

    if (access(pack_path, R_OK) != 0) {
        log_printf("ERROR      : SGBPACK no accesible: %s\n", strerror(errno));
        goto cleanup;
    }

    if (init_egl() != 0) {
        log_printf("ERROR      : fallo inicializando EGL/GLES\n");
        goto cleanup;
    }

    g_padfd = open_clovercon();

    if (load_core() != 0) goto cleanup;

    memset(&sysinfo, 0, sizeof(sysinfo));
    core_retro_get_system_info(&sysinfo);
    log_printf("core name   : %s\n", sysinfo.library_name ? sysinfo.library_name : "?");
    log_printf("core ver    : %s\n", sysinfo.library_version ? sysinfo.library_version : "?");

    core_retro_set_environment(environ_cb);
    core_retro_set_video_refresh(video_cb);
    core_retro_set_audio_sample(audio_sample_cb);
    core_retro_set_audio_sample_batch(audio_batch_cb);
    core_retro_set_input_poll(input_poll_cb);
    core_retro_set_input_state(input_state_cb);
    core_retro_init();
    core_inited = 1;
    core_retro_set_controller_port_device(0, RETRO_DEVICE_JOYPAD);

    memset(&game, 0, sizeof(game));
    game.path = pack_path;
    game.data = NULL;
    game.size = 0;
    game.meta = NULL;
    if (!core_retro_load_game(&game)) {
        log_printf("ERROR core : retro_load_game fallo\n");
        goto cleanup;
    }
    game_loaded = 1;

    memset(&avinfo, 0, sizeof(avinfo));
    core_retro_get_system_av_info(&avinfo);
    if (avinfo.geometry.aspect_ratio > 0.1f) g_core_aspect = avinfo.geometry.aspect_ratio;
    log_printf("geometry    : %ux%u max=%ux%u aspect=%.4f\n",
               avinfo.geometry.base_width, avinfo.geometry.base_height,
               avinfo.geometry.max_width, avinfo.geometry.max_height,
               (double)g_core_aspect);
    log_printf("timing      : %.3f fps / %.0f Hz audio\n",
               avinfo.timing.fps, avinfo.timing.sample_rate);

    if (avinfo.timing.fps > 30.0 && avinfo.timing.fps < 120.0)
        target_fps = avinfo.timing.fps;
    frame_period = 1.0 / target_fps;

    {
        unsigned arate = (avinfo.timing.sample_rate >= 8000.0 &&
                          avinfo.timing.sample_rate <= 192000.0)
                         ? (unsigned)(avinfo.timing.sample_rate + 0.5)
                         : 32040u;
        if (init_alsa(arate) != 0)
            log_printf("ALSA        : NO DISPONIBLE; el core sigue generando audio para medirlo\n");
    }

    log_printf("video path  : RGB565 16-bit a Mali; compacta filas solo si pitch > visible\n");
    log_printf("play test   : %.0f s a %.3f FPS objetivo\n", IKCORE_TEST_SECONDS, target_fps);
    log_printf("salir       : mantener SELECT+START %.1f s\n", IKCORE_EXIT_HOLD_SECONDS);

    start = last = now_s();
    deadline = start;
    end = start + IKCORE_TEST_SECONDS;

    while (!g_shutdown_requested && !g_swap_failed && now_s() < end) {
        double work_start, work_end, n;
        uint16_t exit_mask = (uint16_t)((1u << RETRO_DEVICE_ID_JOYPAD_SELECT) |
                                        (1u << RETRO_DEVICE_ID_JOYPAD_START));

        work_start = now_s();
        core_retro_run();
        work_end = now_s();
        g_work_seconds += work_end - work_start;
        run_frames++;

        n = work_end;
        if ((g_pad_mask & exit_mask) == exit_mask) {
            if (exit_combo_since <= 0.0)
                exit_combo_since = n;
            else if (n - exit_combo_since >= IKCORE_EXIT_HOLD_SECONDS) {
                g_user_exit = 1;
                break;
            }
        } else {
            exit_combo_since = 0.0;
        }

        deadline += frame_period;
        n = now_s();
        if (n < deadline) {
            sleep_s(deadline - n);
        } else {
            g_late_frames++;
            if (n - deadline > frame_period * 3.0)
                deadline = n;
        }

        n = now_s();
        if (n - last >= 1.0) {
            unsigned long delta_frames = run_frames - last_run_frames;
            double interval = n - last;
            double capacity = g_work_seconds > 0.0 ?
                              (double)run_frames / g_work_seconds : 0.0;
            log_printf("play FPS    : %.2f | capacidad trabajo: %.2f FPS | runs=%lu video=%lu\n",
                       interval > 0.0 ? (double)delta_frames / interval : 0.0,
                       capacity, run_frames, g_video_frames);
            last = n;
            last_run_frames = run_frames;
        }
    }

    test_elapsed = now_s() - start;
    success = (run_frames > 0 && g_video_frames > 0 && !g_swap_failed);

cleanup:
    if (game_loaded && core_retro_unload_game) core_retro_unload_game();
    if (core_inited && core_retro_deinit) core_retro_deinit();
    close_alsa();
    close_core();

    if (g_padfd >= 0) {
        ioctl(g_padfd, EVIOCGRAB, 0);
        close(g_padfd);
        g_padfd = -1;
    }

    destroy_egl();

    log_printf("\nFINAL N2.11\n");
    log_printf("runs        : %lu\n", run_frames);
    log_printf("video frames: %lu\n", g_video_frames);
    log_printf("runtime     : %.2f s\n", test_elapsed);
    if (test_elapsed > 0.0)
        log_printf("play avg    : %.2f FPS\n", (double)run_frames / test_elapsed);
    if (g_work_seconds > 0.0) {
        log_printf("work cap    : %.2f FPS\n", (double)run_frames / g_work_seconds);
        log_printf("work cost   : %.3f ms/frame\n",
                   (g_work_seconds * 1000.0) / (double)run_frames);
    }
    if (g_video_frames > 0)
        log_printf("video cost  : %.3f ms/frame\n",
                   (g_video_seconds * 1000.0) / (double)g_video_frames);
    log_printf("late frames : %lu\n", g_late_frames);
    log_printf("first pitch : %lu bytes\n", (unsigned long)g_first_pitch);
    log_printf("exit reason : %s\n",
               g_user_exit ? "SELECT+START" :
               (g_shutdown_requested ? "core shutdown" :
               (g_swap_failed ? "EGL swap failure" : "timeout 120 s")));
    log_printf("last frame  : %ux%u\n", g_frame_w, g_frame_h);
    log_printf("input events: %lu\n", g_input_events);
    log_printf("audio gen   : %lu frames\n", g_audio_frames_generated);
    log_printf("audio write : %lu frames\n", g_audio_frames_written);
    log_printf("audio drop  : %lu frames\n", g_audio_frames_dropped);
    log_printf("ALSA recover: %lu\n", g_audio_recoveries);
    log_printf("ALSA close  : cerrado limpiamente\n");
    log_printf("EGL         : liberado correctamente\n");
    log_printf("resultado   : %s\n", success ? "VIDEO SGB OK" : "FALLO; revisar ikcore-n2_11.log");
    log_printf("log         : %s\n", IKCORE_LOG_PATH);

    if (g_log) {
        fclose(g_log);
        g_log = NULL;
    }

    /* Always return cleanly to Clover for controlled N2.11 exits/errors. */
    return 0;
}
