/*
 * Ik Core native-only Clover suspendpoint v1.
 *
 * Save/load is lossless for the Game Boy SGB state exposed by the pinned
 * libretro core. SNES-side SPC DSP state is not part of the core's SGB
 * serialization. This is an explicitly provisional suspendpoint feature,
 * NOT a guarantee of seamless SNES audio continuation.
 *
 * No background autosnapshot, no mutation of validated internal SRAM logic.
 * Writes only to paths Clover supplies in command-line flags, atomic rename.
 */
#define IK_SUSPEND_MAX_BYTES (24u * 1024u * 1024u)
#define IK_SUSPEND_HEADER_BYTES 40u

static char ik_suspend_output[4096] = {0};
static char ik_suspend_input[4096] = {0};
static char ik_suspend_png[4096] = {0};
static char ik_suspend_clv[16] = {0};
static uint64_t ik_suspend_rom_hash = 0;
static int ik_suspend_ready = 0;

static const void *ik_suspend_last_frame = NULL;
static unsigned ik_suspend_frame_width = 0, ik_suspend_frame_height = 0;
static size_t ik_suspend_frame_pitch = 0;

static void ik_susp_le32(uint8_t *p, uint32_t v)
{
    p[0]=(uint8_t)v; p[1]=(uint8_t)(v >> 8);
    p[2]=(uint8_t)(v >> 16); p[3]=(uint8_t)(v >> 24);
}
static uint32_t ik_susp_get32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static void ik_susp_le64(uint8_t *p, uint64_t v)
{
    unsigned k;
    for(k=0;k<8;++k) p[k]=(uint8_t)(v >> (8*k));
}
static uint64_t ik_susp_get64(const uint8_t *p)
{
    uint64_t v=0;
    int k;
    for(k=7;k>=0;--k) v=(v << 8) | p[k];
    return v;
}
static uint32_t ik_susp_crc_update(uint32_t crc, const uint8_t *p, size_t n)
{
    size_t i;
    for(i=0;i<n;i++) {
        unsigned j;
        crc ^= p[i];
        for(j=0;j<8;j++)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return crc;
}
static uint32_t ik_susp_crc(const uint8_t *p, size_t n)
{
    return ~ik_susp_crc_update(0xffffffffu, p, n);
}
static uint64_t ik_susp_hash_pack(const char *path)
{
    FILE *f;
    uint8_t buf[8192];
    size_t n;
    uint64_t hash=UINT64_C(14695981039346656037);
    size_t total=0;
    f=fopen(path,"rb");
    if(!f) return 0;
    while((n=fread(buf,1,sizeof buf,f))>0) {
        size_t i;
        total+=n;
        if(total>64u*1024u*1024u) { fclose(f);return 0; }
        for(i=0;i<n;i++) { hash^=buf[i];hash*=UINT64_C(1099511628211); }
    }
    if(ferror(f)) { fclose(f);return 0; }
    fclose(f);
    return total>256 ? hash : 0;
}
/* We do not trust a possibly partial .state. The header binds the snapshot
 * to the actual SGBPACK bytes and selected Hakchi game, not the 7z tmp path.
 * Keep file layout byte-defined (no padding/endian ambiguity).
 */
static int ik_susp_read_file(const char *path, uint8_t **buf_out,
                             size_t *size_out)
{
    FILE *f=NULL;
    struct stat st;
    uint8_t h[IK_SUSPEND_HEADER_BYTES];
    uint8_t *data=NULL;
    size_t n;
    if(stat(path,&st)!=0 || !S_ISREG(st.st_mode) ||
       st.st_size<(off_t)IK_SUSPEND_HEADER_BYTES ||
       st.st_size>(off_t)(IK_SUSPEND_MAX_BYTES+IK_SUSPEND_HEADER_BYTES))
        return 0;
    f=fopen(path,"rb");
    if(!f) return 0;
    if(fread(h,1,sizeof h,f)!=sizeof h) goto bad;
    if(memcmp(h,"IKCSUSP1",8) || ik_susp_get32(h+12)!=1 ||
       memcmp(h+20,ik_suspend_clv,12) ||
       ik_susp_get64(h+32)!=ik_suspend_rom_hash) {
        log_printf("SUSP LOAD    : archivo incompatible (ROM/ID/version), conservado.\n");
        goto bad;
    }
    n=(size_t)ik_susp_get32(h+8);
    if(n<12 || n>IK_SUSPEND_MAX_BYTES ||
       st.st_size!=(off_t)(n+sizeof h)) goto bad;
    data=(uint8_t *)malloc(n);
    if(!data) goto bad;
    if(fread(data,1,n,f)!=n ||
       ik_susp_crc(data,n)!=ik_susp_get32(h+16)) {
        log_printf("SUSP LOAD    : CRC/truncado incompatible; ignorado.\n");
        goto bad;
    }
    fclose(f);
    *buf_out=data;
    *size_out=n;
    return 1;
bad:
    if(f) fclose(f);
    free(data);
    return 0;
}
static int ik_susp_parent_dir(const char *path)
{
    char dir[4096];
    size_t i,n=strlen(path);
    if(n==0 || n>=sizeof dir || path[0]!='/') return 0;
    memcpy(dir,path,n+1);
    for(i=1;i<n;i++) {
        if(dir[i]!='/') continue;
        dir[i]=0;
        if(mkdir(dir,0755)!=0 && errno!=EEXIST) return 0;
        dir[i]='/';
    }
    return 1;
}
static int ik_susp_save_file(const char *path, const uint8_t *data,
                             size_t size)
{
    /* Create one header+body write in .tmp PID, then fsync+rename.
     * Existing suspendpoints are preserved on all write failures.
     */
    uint8_t *blob=NULL;
    uint8_t h[IK_SUSPEND_HEADER_BYTES];
    char temp[4096];
    int fd=-1,rc=0;
    size_t total,pos=0;
    if(size<12 || size>IK_SUSPEND_MAX_BYTES || !ik_susp_parent_dir(path))return 0;
    if(snprintf(temp,sizeof temp,"%s.tmp.%ld",path,(long)getpid())>=
       (int)sizeof temp)return 0;
    total=size+sizeof h;
    blob=(uint8_t *)malloc(total);
    if(!blob)return 0;
    memset(h,0,sizeof h);
    memcpy(h,"IKCSUSP1",8);
    ik_susp_le32(h+8,(uint32_t)size);
    ik_susp_le32(h+12,1);
    ik_susp_le32(h+16,ik_susp_crc(data,size));
    memcpy(h+20,ik_suspend_clv,12);
    ik_susp_le64(h+32,ik_suspend_rom_hash);
    memcpy(blob,h,sizeof h);
    memcpy(blob+sizeof h,data,size);
    fd=open(temp,O_WRONLY|O_CREAT|O_EXCL,0600);
    if(fd<0)goto done;
    while(pos<total) {
        ssize_t w=write(fd,blob+pos,total-pos);
        if(w<0 && errno==EINTR)continue;
        if(w<=0)goto done;
        pos+=(size_t)w;
    }
    if(fsync(fd)!=0)goto done;
    if(close(fd)!=0) { fd=-1;goto done; }
    fd=-1;
    if(rename(temp,path)!=0)goto done;
    rc=1;
done:
    if(fd>=0)close(fd);
    if(!rc)unlink(temp);
    free(blob);
    return rc;
}

static void ik_susp_be32(uint8_t *p, uint32_t x)
{
    p[0]=(uint8_t)(x>>24);p[1]=(uint8_t)(x>>16);
    p[2]=(uint8_t)(x>>8);p[3]=(uint8_t)x;
}
static uint32_t ik_susp_adler(const uint8_t *p,size_t n)
{
    uint32_t a=1,b=0;
    size_t i;
    for(i=0;i<n;i++) {
        a=(a+p[i])%65521u;
        b=(b+a)%65521u;
    }
    return (b<<16)|a;
}
static int ik_susp_png_piece(FILE *f,uint32_t *crc,
                             const void *p,size_t n)
{
    if(fwrite(p,1,n,f)!=n)return 0;
    if(crc)*crc=ik_susp_crc_update(*crc,(const uint8_t *)p,n);
    return 1;
}
static int ik_susp_png_chunk(FILE *f,const char *type,
                             const uint8_t *bytes,size_t n)
{
    uint8_t be[4];
    uint32_t crc=0xffffffffu;
    ik_susp_be32(be,(uint32_t)n);
    if(!ik_susp_png_piece(f,NULL,be,4) ||
       !ik_susp_png_piece(f,&crc,type,4) ||
       (n && !ik_susp_png_piece(f,&crc,bytes,n)))return 0;
    ik_susp_be32(be,~crc);
    return ik_susp_png_piece(f,NULL,be,4);
}
/* One PNG IDAT chunk containing a valid zlib stream of uncompressed DEFLATE
 * blocks. Use only once on exit; preserve zero pixel-conversion overhead in
 * the approved 60 FPS render loop. No dependency on extra PNG libraries.
 */
static int ik_susp_png_write(const char *path)
{
    uint8_t *raw=NULL;
    size_t rowsz,rawlen;
    unsigned w=ik_suspend_frame_width,h=ik_suspend_frame_height,y,x;
    const uint8_t *source=(const uint8_t *)ik_suspend_last_frame;
    uint8_t be[4],ihdr[13],zhead[2]={0x78,0x01};
    uint32_t crc,adler;
    FILE *f=NULL;
    char tmp[4096];
    size_t blocks,remaining,pos;
    int ok=0;
    if(!source || !w || !h || w>512 || h>512 ||
       ik_suspend_frame_pitch < (size_t)w*2 ||
       ik_suspend_frame_pitch>8192 || !ik_susp_parent_dir(path))return 0;
    rowsz=(size_t)w*3u+1u;
    rawlen=rowsz*(size_t)h;
    raw=(uint8_t *)malloc(rawlen);
    if(!raw)return 0;
    for(y=0;y<h;y++) {
        uint8_t *dst=raw+(size_t)y*rowsz;
        const uint8_t *src=source+(size_t)y*ik_suspend_frame_pitch;
        dst[0]=0; /* PNG filter: none */
        for(x=0;x<w;x++) {
            unsigned r,g,b;
            if(g_pixel_format==RETRO_PIXEL_FORMAT_XRGB8888) {
                uint32_t pix;
                memcpy(&pix,src+(size_t)x*4,4);
                r=(pix>>16)&255u;g=(pix>>8)&255u;b=pix&255u;
            } else {
                uint16_t pix;
                memcpy(&pix,src+(size_t)x*2,2);
                if(g_pixel_format==RETRO_PIXEL_FORMAT_RGB565) {
                    r=(pix>>11)&31u;g=(pix>>5)&63u;b=pix&31u;
                    r=(r<<3)|(r>>2);g=(g<<2)|(g>>4);b=(b<<3)|(b>>2);
                } else {
                    r=(pix>>10)&31u;g=(pix>>5)&31u;b=pix&31u;
                    r=(r<<3)|(r>>2);g=(g<<3)|(g>>2);b=(b<<3)|(b>>2);
                }
            }
            dst[1+3*x]=(uint8_t)r;
            dst[2+3*x]=(uint8_t)g;
            dst[3+3*x]=(uint8_t)b;
        }
    }
    if(snprintf(tmp,sizeof tmp,"%s.tmp.%ld",path,(long)getpid())>=
       (int)sizeof tmp)goto done;
    f=fopen(tmp,"wb");
    if(!f)goto done;
    if(fwrite("\211PNG\r\n\032\n",1,8,f)!=8)goto done;
    memset(ihdr,0,sizeof ihdr);
    ik_susp_be32(ihdr,w);ik_susp_be32(ihdr+4,h);
    ihdr[8]=8;ihdr[9]=2; /* 8 bit RGB */
    if(!ik_susp_png_chunk(f,"IHDR",ihdr,sizeof ihdr))goto done;

    blocks=(rawlen+65534u)/65535u;
    ik_susp_be32(be,(uint32_t)(2u+5u*blocks+rawlen+4u));
    crc=0xffffffffu;
    if(!ik_susp_png_piece(f,NULL,be,4) ||
       !ik_susp_png_piece(f,&crc,"IDAT",4) ||
       !ik_susp_png_piece(f,&crc,zhead,2))goto done;
    remaining=rawlen;pos=0;
    while(remaining>0) {
        uint8_t blk[5];
        unsigned chunk=(unsigned)(remaining>65535u?65535u:remaining);
        unsigned inv=65535u-chunk;
        blk[0]=(remaining==chunk)?1u:0u; /* final uncompressed block */
        blk[1]=(uint8_t)chunk;blk[2]=(uint8_t)(chunk>>8);
        blk[3]=(uint8_t)inv;blk[4]=(uint8_t)(inv>>8);
        if(!ik_susp_png_piece(f,&crc,blk,5) ||
           !ik_susp_png_piece(f,&crc,raw+pos,chunk))goto done;
        pos+=chunk;remaining-=chunk;
    }
    adler=ik_susp_adler(raw,rawlen);
    ik_susp_be32(be,adler);
    if(!ik_susp_png_piece(f,&crc,be,4))goto done;
    ik_susp_be32(be,~crc);
    if(!ik_susp_png_piece(f,NULL,be,4) ||
       !ik_susp_png_chunk(f,"IEND",NULL,0))goto done;
    if(fflush(f)!=0 || fsync(fileno(f))!=0 || fclose(f)!=0) {
        f=NULL;goto done;
    }
    f=NULL;
    if(rename(tmp,path)!=0)goto done;
    ok=1;
done:
    if(f)fclose(f);
    if(!ok)unlink(tmp);
    free(raw);
    return ok;
}

static const char *ik_susp_arg(int argc,char **argv,const char *key)
{
    int i;
    size_t len=strlen(key);
    for(i=1;i<argc;i++) {
        const char *arg=argv[i];
        if(!arg)continue;
        if(!strcmp(arg,key) && i+1<argc) return argv[i+1];
        if(!strncmp(arg,key,len) && arg[len]=='=')return arg+len+1;
    }
    return NULL;
}
static void ik_susp_copy_path(char dest[4096], const char *value)
{
    if(value && value[0]=='/' && strlen(value)<4096)
        memcpy(dest,value,strlen(value)+1);
}
static void ik_suspend_initialize(int argc,char **argv,const char *pack_path)
{
    const char *value;
    uint8_t *snapshot=NULL;
    size_t size=0;
    int i;
    char next[16]={0};
    value=ik_susp_arg(argc,argv,"--save-on-quit");
    ik_susp_copy_path(ik_suspend_output,value);
    value=ik_susp_arg(argc,argv,"--load-state-file");
    ik_susp_copy_path(ik_suspend_input,value);
    value=ik_susp_arg(argc,argv,"--save-screenshot-on-quit");
    ik_susp_copy_path(ik_suspend_png,value);

    for(i=1;i<argc;i++) {
        if(!ikcore_extract_clv_id(argv[i],next))continue;
        if(ik_suspend_clv[0] && strcmp(ik_suspend_clv,next)) {
            log_printf("SUSP ERROR   : CLV ambiguo, se bloquean estados.\n");
            return;
        }
        strcpy(ik_suspend_clv,next);
    }
    if(!ik_suspend_clv[0]) {
        char cwd[4096];
        if(getcwd(cwd,sizeof cwd)) (void)ikcore_extract_clv_id(cwd,ik_suspend_clv);
    }
    if(!ik_suspend_clv[0] || !core_retro_serialize_size ||
       !core_retro_serialize || !core_retro_unserialize) {
        log_printf("SUSP ERROR   : ID estable o API de estados no disponible.\n");
        return;
    }
    ik_suspend_rom_hash=ik_susp_hash_pack(pack_path);
    if(!ik_suspend_rom_hash) {
        log_printf("SUSP ERROR   : no se pudo identificar ROM, guardado deshabilitado.\n");
        return;
    }
    ik_suspend_ready=1;
    log_printf("SUSP         : juego=%s, guardado=%s, carga=%s\n",
               ik_suspend_clv,
               ik_suspend_output[0]?ik_suspend_output:"NO",
               ik_suspend_input[0]?ik_suspend_input:"NO");

    if(!ik_suspend_input[0])return;
    if(!ik_susp_read_file(ik_suspend_input,&snapshot,&size)) {
        log_printf("SUSP LOAD    : no hay punto válido, inicia juego normalmente.\n");
        return;
    }
    if(core_retro_unserialize(snapshot,size)) {
        /* A suspendpoint can contain older cart SRAM than the permanent
         * .srm. Reset the comparison baseline to the restored RAM so the
         * 5-second autosaver will NOT silently overwrite an existing, newer
         * cartridge save merely because a suspendpoint was loaded.
         * A subsequent real in-game save changes SRAM and persists normally.
         */
        if(ik_sram_shadow && !ik_sram_disabled) {
            size_t ram_size=core_retro_get_memory_size(RETRO_MEMORY_SAVE_RAM);
            void *ram=core_retro_get_memory_data(RETRO_MEMORY_SAVE_RAM);
            if(ram && ram_size==ik_sram_size) {
                memcpy(ik_sram_shadow,ram,ram_size);
                log_printf("SUSP SRAM    : cartucho protegido hasta nuevo guardado interno.\n");
            }
        }
        log_printf("SUSP LOAD OK : %zu bytes restaurados desde %s\n",
                   size,ik_suspend_input);
    } else
        log_printf("SUSP LOAD    : el núcleo rechazó el estado, inicia normalmente.\n");
    free(snapshot);
}
static void ik_suspend_save(void)
{
    uint8_t *data=NULL;
    size_t n;
    if(!ik_suspend_ready || !ik_suspend_output[0])return;
    if(g_video_frames==0) {
        log_printf("SUSP SAVE    : sin fotogramas; no crear estado.\n");
        return;
    }
    n=core_retro_serialize_size();
    if(n<12 || n>IK_SUSPEND_MAX_BYTES) {
        log_printf("SUSP ERROR   : tamaño no válido %zu.\n",n);
        return;
    }
    data=(uint8_t *)malloc(n);
    if(!data) { log_printf("SUSP ERROR   : memoria insuficiente.\n");return; }
    if(!core_retro_serialize(data,n)) {
        log_printf("SUSP ERROR   : retro_serialize devolvió error.\n");
        free(data);
        return;
    }
    if(ik_susp_save_file(ik_suspend_output,data,n)) {
        log_printf("SUSP SAVE OK : %zu bytes en %s\n",n,ik_suspend_output);
        if(ik_suspend_png[0]) {
            if(ik_susp_png_write(ik_suspend_png))
                log_printf("SUSP PNG OK  : %s\n",ik_suspend_png);
            else
                log_printf("SUSP PNG FAIL: no se creó vista previa.\n");
        }
    } else {
        log_printf("SUSP ERROR   : no se pudo escribir %s: %s\n",
                   ik_suspend_output,strerror(errno));
    }
    free(data);
}
