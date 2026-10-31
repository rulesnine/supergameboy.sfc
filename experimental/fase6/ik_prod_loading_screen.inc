/* Ik Core SGB production: deliberate pixel-art Game Boy loading screen.
 * Never depends on a commercial Game Boy/SGB graphic or a font file.
 * Rendered on the existing Mali RGB565 texture; no extra EGL context.
 */
#include "ik_prod_loading_gate.h"
static uint16_t ik_prod_load_pixels[256u*224u];
static IkProdLoadingGate ik_prod_gate;
static int ik_prod_load_built=0, ik_prod_load_phase=0;
static void ik_prod_px(int x,int y,uint16_t p) {
    if((unsigned)x<256u&&(unsigned)y<224u)
        ik_prod_load_pixels[(unsigned)y*256u+(unsigned)x]=p;
}
static void ik_prod_rect(int x,int y,int w,int h,uint16_t c) {
    int xx,yy;
    for(yy=y;yy<y+h;yy++)for(xx=x;xx<x+w;xx++)ik_prod_px(xx,yy,c);
}
static void ik_prod_rounded(int x,int y,int w,int h,int r,uint16_t c) {
    int xx,yy;
    for(yy=0;yy<h;yy++)for(xx=0;xx<w;xx++) {
        int dx=xx<r?r-xx-1:(xx>=w-r?xx-(w-r):0);
        int dy=yy<r?r-yy-1:(yy>=h-r?yy-(h-r):0);
        if(dx*dx+dy*dy<=r*r)ik_prod_px(x+xx,y+yy,c);
    }
}
/* Exact pixels for the only glyphs required by this UI: CARGANDO / GAME BOY.
 * Stylized 5x7 block font. This does not affect in-game font or SGB colors. */
static const uint8_t *ik_prod_glyph(char c) {
    static const uint8_t A[7]={14,17,17,31,17,17,17};
    static const uint8_t B[7]={30,17,17,30,17,17,30};
    static const uint8_t C[7]={14,17,16,16,16,17,14};
    static const uint8_t D[7]={30,17,17,17,17,17,30};
    static const uint8_t E[7]={31,16,16,30,16,16,31};
    static const uint8_t G[7]={14,17,16,23,17,17,14};
    static const uint8_t M[7]={17,27,21,21,17,17,17};
    static const uint8_t N[7]={17,25,21,19,17,17,17};
    static const uint8_t O[7]={14,17,17,17,17,17,14};
    static const uint8_t R[7]={30,17,17,30,20,18,17};
    static const uint8_t Y[7]={17,17,10,4,4,4,4};
    switch(c) {
      case 'A':return A;case 'B':return B;case 'C':return C;
      case 'D':return D;case 'E':return E;case 'G':return G;
      case 'M':return M;case 'N':return N;case 'O':return O;
      case 'R':return R;case 'Y':return Y;default:return NULL;
    }
}
static void ik_prod_print(int x,int y,const char *str,int scale,uint16_t color) {
    for(;*str;str++,x+=6*scale) {
        const uint8_t *rows=ik_prod_glyph(*str);
        int ry,cx,dx,dy;
        if(!rows)continue;
        for(ry=0;ry<7;ry++)for(cx=0;cx<5;cx++)
            if(rows[ry]&(1u<<(4-cx)))
                for(dy=0;dy<scale;dy++)for(dx=0;dx<scale;dx++)
                    ik_prod_px(x+cx*scale+dx,y+ry*scale+dy,color);
    }
}
static void ik_prod_build_loading(void) {
    static const uint16_t bg=0x0842u, shell=0xD6B9u, shell_shade=0xB596u;
    static const uint16_t bezel=0x2945u,lcd=0xB62Au, ink=0x2946u;
    int i;
    /* 256x224 NES native presentation, subtle shadow and original DMG shell. */
    ik_prod_rect(0,0,256,224,bg);
    ik_prod_rounded(32,7,192,211,12,0x2104u);
    ik_prod_rounded(29,4,192,211,12,shell);
    ik_prod_rect(39,14,171,2,0xE71Cu);
    ik_prod_rect(33,201,182,3,shell_shade);
    ik_prod_rounded(43,25,164,117,8,bezel);
    ik_prod_rounded(54,36,142,88,4,0x7BCAu);
    ik_prod_rect(60,42,130,76,lcd);
    ik_prod_rect(63,45,124,70,0xA5A7u);
    ik_prod_rect(65,47,120,66,0xBDE9u);
    /* Only the word the user requested is centered in the LCD. */
    ik_prod_print(82,72,"CARGANDO",2,ink);
    ik_prod_rect(113,95,5,5,ink);
    ik_prod_rect(124,95,5,5,ink);
    ik_prod_rect(135,95,5,5,ink);
    ik_prod_print(100,147,"GAME BOY",1,0x395Au);
    /* Raised D-pad; two burgundy A/B buttons and two dark menu buttons. */
    ik_prod_rect(67,166,47,15,0x18C3u);
    ik_prod_rect(83,150,15,47,0x18C3u);
    ik_prod_rect(71,169,39,9,0x2945u);
    ik_prod_rect(86,154,9,39,0x2945u);
    ik_prod_rounded(147,170,23,23,11,0x500Eu);
    ik_prod_rounded(176,158,23,23,11,0x500Eu);
    ik_prod_rounded(151,171,17,17,8,0xA018u);
    ik_prod_rounded(180,159,17,17,8,0xA018u);
    ik_prod_rounded(117,200,15,5,2,0x5289u);
    ik_prod_rounded(138,200,15,5,2,0x5289u);
    for(i=0;i<5;i++)
        ik_prod_rect(172+i*7,198-i*2,3,14,0x7BCEu);
    ik_prod_load_built=1;
}
static void ik_prod_show_loading(void) {
    if(!ik_prod_load_built)ik_prod_build_loading();
    g_border_fade=1.0f;
    upload_rgb565_direct(ik_prod_load_pixels,256u,224u);
    draw_texture_frame(256u,224u);
    if(!eglSwapBuffers(g_display,g_surface)) {
        log_printf("IKSGB LOADING: error in EGL swap 0x%04x\n",eglGetError());
        g_swap_failed=1;
    }
    if(!ik_prod_load_phase)log_printf("IKSGB LOADING: GAME_BOY_FRAME CARGANDO visible\n");
    ik_prod_load_phase=1;
}

/* Animated dots driven by actual firmware progress or by emulated GB frames. */
static void ik_prod_loading_animate(unsigned ticks) {
    unsigned step=(ticks/24u)%4u, i;
    if(!ik_prod_load_built)return;
    ik_prod_rect(112,95,37,5,0xBDE9u);
    for(i=0;i<3;i++)
        if(i<step)ik_prod_rect(113+(int)i*11,95,5,5,0x2946u);
    ik_prod_show_loading();
}
