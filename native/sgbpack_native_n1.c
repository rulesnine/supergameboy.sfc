/*
 * Ik Core Native / NES Mini frontend probe N1.4
 *
 * Diagnostic fullscreen ownership probe.
 * No RetroArch, no libretro.
 *
 * N1.4:
 * - scans /proc for processes that have /dev/fb0 or /dev/disp open
 * - prints comm/cmdline for those processes
 * - does NOT suspend anything automatically yet
 * - keeps second framebuffer page + Clovercon exclusive input
 * - 60 Hz presentation test
 */
#define _GNU_SOURCE
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#define FOOTER_SIZE 0x100u
#define MAGIC "SGBPACK1"
#define MAGIC_LEN 8u
#define SGB_W 256
#define SGB_H 224
#define SCALE 3
#define DRAW_W (SGB_W*SCALE)
#define DRAW_H (SGB_H*SCALE)

typedef struct {
    uint32_t sgb_off, sgb_size;
    uint32_t gb_off, gb_size;
    uint32_t boot_off, boot_size;
} PackInfo;

static uint32_t le32(const unsigned char *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1]<<8) |
           ((uint32_t)p[2]<<16) | ((uint32_t)p[3]<<24);
}

static int range_ok(uint64_t off, uint64_t size, uint64_t limit) {
    return off <= limit && size <= limit - off;
}

static int load_pack_info(const char *path, PackInfo *pi) {
    FILE *f;
    struct stat st;
    unsigned char footer[FOOTER_SIZE];
    uint64_t footer_off;

    if (stat(path,&st)!=0) return -1;
    if ((uint64_t)st.st_size<FOOTER_SIZE) return -1;

    f=fopen(path,"rb");
    if (!f) return -1;
    footer_off=(uint64_t)st.st_size-FOOTER_SIZE;
    if (fseeko(f,(off_t)footer_off,SEEK_SET)!=0 ||
        fread(footer,1,FOOTER_SIZE,f)!=FOOTER_SIZE) {
        fclose(f);
        return -1;
    }
    fclose(f);

    if (memcmp(footer,MAGIC,MAGIC_LEN)!=0) return -1;

    pi->sgb_off=le32(footer+0x10);
    pi->sgb_size=le32(footer+0x14);
    pi->gb_off=le32(footer+0x18);
    pi->gb_size=le32(footer+0x1c);
    pi->boot_off=le32(footer+0x20);
    pi->boot_size=le32(footer+0x24);

    if (!range_ok(pi->sgb_off,pi->sgb_size,footer_off) ||
        !range_ok(pi->gb_off,pi->gb_size,footer_off) ||
        !range_ok(pi->boot_off,pi->boot_size,footer_off))
        return -1;
    return 0;
}

static double now_s(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC,&ts);
    return (double)ts.tv_sec+(double)ts.tv_nsec/1e9;
}

static uint32_t scale_chan(uint8_t v,uint32_t bits) {
    if (!bits) return 0;
    if (bits>=8) return (uint32_t)v<<(bits-8);
    return (uint32_t)(v>>(8-bits));
}

static uint32_t pack_rgb(const struct fb_var_screeninfo *v,uint8_t r,uint8_t g,uint8_t b) {
    return (scale_chan(r,v->red.length)<<v->red.offset) |
           (scale_chan(g,v->green.length)<<v->green.offset) |
           (scale_chan(b,v->blue.length)<<v->blue.offset);
}

static void make_test_frame(uint32_t *frame,unsigned frame_no) {
    int x,y;
    for (y=0;y<SGB_H;y++) {
        for (x=0;x<SGB_W;x++) {
            uint8_t r=(uint8_t)((x+frame_no*2)&255);
            uint8_t g=(uint8_t)((y+frame_no)&255);
            uint8_t b=(uint8_t)(((x^y)+frame_no*3)&255);
            if (x>=48&&x<208&&y>=40&&y<184) {
                unsigned cell=(unsigned)((x/8+y/8+frame_no/4)&3);
                static const uint8_t shade[4]={232,176,104,32};
                r=shade[cell];
                g=(uint8_t)(shade[cell]+(cell==0?15:0));
                b=(uint8_t)(shade[cell]/2);
            }
            frame[y*SGB_W+x]=((uint32_t)r<<16)|((uint32_t)g<<8)|b;
        }
    }
}

static void clear_page(void *fb,const struct fb_fix_screeninfo *fix,
                       const struct fb_var_screeninfo *var,unsigned page_y) {
    unsigned y;
    for (y=0;y<var->yres;y++) {
        uint8_t *row=(uint8_t*)fb+(size_t)(page_y+y)*fix->line_length;
        memset(row,0,fix->line_length);
    }
}

static void blit_3x_32(void *fb,const struct fb_fix_screeninfo *fix,
                       const struct fb_var_screeninfo *var,unsigned page_y,
                       const uint32_t *src,uint32_t *line) {
    const unsigned ox=(var->xres-DRAW_W)/2;
    const unsigned oy=(var->yres-DRAW_H)/2;
    unsigned sy,sx,k;

    for (sy=0;sy<SGB_H;sy++) {
        uint32_t *d=line;
        const uint32_t *s=src+sy*SGB_W;
        for (sx=0;sx<SGB_W;sx++) {
            uint32_t c=s[sx];
            uint32_t p=pack_rgb(var,(uint8_t)(c>>16),(uint8_t)(c>>8),(uint8_t)c);
            *d++=p; *d++=p; *d++=p;
        }
        for (k=0;k<SCALE;k++) {
            uint8_t *row=(uint8_t*)fb+
                (size_t)(page_y+oy+sy*SCALE+k)*fix->line_length+
                (size_t)ox*4u;
            memcpy(row,line,DRAW_W*sizeof(uint32_t));
        }
    }
}

static int read_proc_text(pid_t pid,const char *leaf,char *buf,size_t cap) {
    char path[64];
    int fd;
    ssize_t n;
    snprintf(path,sizeof(path),"/proc/%ld/%s",(long)pid,leaf);
    fd=open(path,O_RDONLY);
    if (fd<0) return -1;
    n=read(fd,buf,cap-1);
    close(fd);
    if (n<=0) return -1;
    buf[n]=0;
    for (ssize_t i=0;i<n;i++) if (buf[i]=='\0') buf[i]=' ';
    return 0;
}

static int process_has_target_fd(pid_t pid,const char *needle) {
    char dirpath[64];
    DIR *d;
    struct dirent *de;
    int found=0;

    snprintf(dirpath,sizeof(dirpath),"/proc/%ld/fd",(long)pid);
    d=opendir(dirpath);
    if (!d) return 0;

    while ((de=readdir(d))!=NULL) {
        char fdpath[PATH_MAX],target[PATH_MAX];
        ssize_t n;
        if (de->d_name[0]=='.') continue;
        snprintf(fdpath,sizeof(fdpath),"%s/%s",dirpath,de->d_name);
        n=readlink(fdpath,target,sizeof(target)-1);
        if (n<=0) continue;
        target[n]=0;
        if (strstr(target,needle)) {
            found=1;
            break;
        }
    }

    closedir(d);
    return found;
}

static void print_display_owners(void) {
    DIR *d=opendir("/proc");
    struct dirent *de;
    pid_t self=getpid();
    int count=0;

    printf("\nDISPLAY OWNERS / CANDIDATES\n");
    if (!d) {
        printf("proc scan   : no se pudo abrir /proc\n");
        return;
    }

    while ((de=readdir(d))!=NULL) {
        char *p=de->d_name;
        int numeric=1;
        pid_t pid;
        char comm[256]={0},cmd[1024]={0};

        if (!*p) continue;
        for (;*p;p++) if (!isdigit((unsigned char)*p)) { numeric=0; break; }
        if (!numeric) continue;

        pid=(pid_t)strtol(de->d_name,NULL,10);
        if (pid<=1 || pid==self) continue;

        if (process_has_target_fd(pid,"/dev/fb0") ||
            process_has_target_fd(pid,"/dev/disp")) {
            read_proc_text(pid,"comm",comm,sizeof(comm));
            read_proc_text(pid,"cmdline",cmd,sizeof(cmd));
            printf("display proc: pid=%ld comm=[%s] cmd=[%s]\n",
                   (long)pid,comm,cmd);
            count++;
        }
    }

    closedir(d);
    printf("display proc count: %d\n\n",count);
}

static int open_clovercon(void) {
    int i;
    for (i=0;i<32;i++) {
        char path[64],name[128]={0};
        int fd;
        snprintf(path,sizeof(path),"/dev/input/event%d",i);
        fd=open(path,O_RDONLY|O_NONBLOCK);
        if (fd<0) continue;
        ioctl(fd,EVIOCGNAME(sizeof(name)),name);
        if (strstr(name,"Nintendo Clovercon")) {
            printf("controller  : %s [%s]\n",path,name);
            if (ioctl(fd,EVIOCGRAB,1)==0)
                printf("controller  : EVIOCGRAB OK\n");
            else
                printf("controller  : EVIOCGRAB fallo: %s\n",strerror(errno));
            return fd;
        }
        close(fd);
    }
    return -1;
}

static unsigned poll_pad(int fd) {
    unsigned n=0;
    struct input_event ev[32];
    ssize_t got;
    if (fd<0) return 0;
    while ((got=read(fd,ev,sizeof(ev)))>0) {
        size_t i,count=(size_t)got/sizeof(ev[0]);
        for (i=0;i<count;i++) {
            if (ev[i].type==EV_KEY || ev[i].type==EV_ABS) {
                printf("pad event   : type=%u code=%u value=%d\n",
                       (unsigned)ev[i].type,(unsigned)ev[i].code,ev[i].value);
                n++;
            }
        }
    }
    return n;
}

int main(int argc,char **argv) {
    PackInfo pi;
    int fbfd=-1,padfd=-1;
    struct fb_fix_screeninfo fix;
    struct fb_var_screeninfo var,original_var,pan;
    void *fb=MAP_FAILED;
    uint32_t *frame=NULL,*line=NULL;
    unsigned private_y=0,input_events=0,frames=0;
    double t0,end,next,last,fps;

    if (argc!=2) {
        fprintf(stderr,"uso: %s archivo_SGBPACK.sfc\n",argv[0]);
        return 2;
    }
    if (load_pack_info(argv[1],&pi)!=0) {
        fprintf(stderr,"ERROR: SGBPACK1 invalido\n");
        return 3;
    }

    printf("Ik Core Native N1.4 - diagnostico propietario de pantalla\n");
    printf("SGBPACK1   : OK\n");
    print_display_owners();

    fbfd=open("/dev/fb0",O_RDWR);
    if (fbfd<0) {
        fprintf(stderr,"ERROR /dev/fb0: %s\n",strerror(errno));
        return 4;
    }

    if (ioctl(fbfd,FBIOGET_FSCREENINFO,&fix)<0 ||
        ioctl(fbfd,FBIOGET_VSCREENINFO,&var)<0) {
        fprintf(stderr,"ERROR framebuffer ioctl\n");
        close(fbfd);
        return 5;
    }

    original_var=var;
    printf("framebuffer: %ux%u virt=%ux%u, %u bpp, yoffset=%u\n",
           var.xres,var.yres,var.xres_virtual,var.yres_virtual,
           var.bits_per_pixel,var.yoffset);

    if (var.bits_per_pixel!=32 || var.xres<DRAW_W || var.yres<DRAW_H) {
        fprintf(stderr,"ERROR: framebuffer no compatible\n");
        close(fbfd);
        return 6;
    }

    private_y=(var.yres_virtual>=var.yres*2)
        ? ((var.yoffset<var.yres)?var.yres:0)
        : var.yoffset;

    fb=mmap(NULL,fix.smem_len,PROT_READ|PROT_WRITE,MAP_SHARED,fbfd,0);
    if (fb==MAP_FAILED) {
        fprintf(stderr,"ERROR mmap: %s\n",strerror(errno));
        close(fbfd);
        return 7;
    }

    frame=(uint32_t*)malloc(SGB_W*SGB_H*sizeof(uint32_t));
    line=(uint32_t*)malloc(DRAW_W*sizeof(uint32_t));
    if (!frame || !line) {
        fprintf(stderr,"ERROR memoria\n");
        free(frame); free(line);
        munmap(fb,fix.smem_len); close(fbfd);
        return 8;
    }

    clear_page(fb,&fix,&var,private_y);

    pan=var;
    pan.yoffset=private_y;
    pan.activate=FB_ACTIVATE_VBL;
    if (ioctl(fbfd,FBIOPAN_DISPLAY,&pan)==0)
        printf("pan display : OK -> yoffset=%u\n",private_y);
    else {
        printf("pan display : FALLO (%s)\n",strerror(errno));
        private_y=var.yoffset;
        clear_page(fb,&fix,&var,private_y);
    }

    padfd=open_clovercon();

    printf("benchmark   : 10 s @ 60 Hz; pulsa botones\n");
    fflush(stdout);

    t0=last=now_s();
    end=t0+10.0;
    next=t0;

    while (now_s()<end) {
        double n=now_s();
        if (n<next) {
            struct timespec req;
            double rem=next-n;
            req.tv_sec=(time_t)rem;
            req.tv_nsec=(long)((rem-(double)req.tv_sec)*1e9);
            if (req.tv_nsec>0) nanosleep(&req,NULL);
        }

        make_test_frame(frame,frames);
        blit_3x_32(fb,&fix,&var,private_y,frame,line);
        input_events+=poll_pad(padfd);
        frames++;
        next+=1.0/60.0;

        n=now_s();
        if (n-last>=1.0) {
            printf("native FPS  : %.2f (frames=%u)\n",(double)frames/(n-t0),frames);
            fflush(stdout);
            last=n;
        }
    }

    fps=(double)frames/(now_s()-t0);

    if (padfd>=0) {
        ioctl(padfd,EVIOCGRAB,0);
        close(padfd);
    }

    if (ioctl(fbfd,FBIOPAN_DISPLAY,&original_var)==0)
        printf("restore pan : OK -> yoffset=%u\n",original_var.yoffset);
    else
        printf("restore pan : FALLO: %s\n",strerror(errno));

    printf("\nFINAL\n");
    printf("NATIVE FPS  : %.2f\n",fps);
    printf("input events: %u\n",input_events);
    printf("display     : restaurado\n");

    free(line); free(frame);
    munmap(fb,fix.smem_len);
    close(fbfd);
    return 0;
}
