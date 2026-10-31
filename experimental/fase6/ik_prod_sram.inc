/* Ik Core QuickStart RC5: mGBA battery SRAM persistence.
 * This is NOT a libretro savestate or an Snes9x firmware cache.
 * Key by actual Game Boy ROM bytes; never by temporary .7z extraction path.
 */
#define IK_PROD_SAVE_DIR "/var/lib/hakchi/ikcore-quick-saves"
static void *(*core_retro_get_memory_data)(unsigned);
static size_t (*core_retro_get_memory_size)(unsigned);
static uint8_t *ik_prod_sram_shadow=NULL;
static size_t ik_prod_sram_size=0;
static char ik_prod_sram_path[512]={0};
static double ik_prod_sram_next_check=0.0;
static int ik_prod_sram_blocked=0;
static unsigned ik_prod_sram_writes=0;

static int ikcore_extract_clv_id(const char *text,char id[16]) {
    const char *p;
    if(!text)return 0;
    for(p=text;(p=strstr(p,"CLV-"))!=NULL;++p) {
        if(strlen(p)<11u)break;
        int i,ok=(p[4]>='A'&&p[4]<='Z'&&p[5]=='-');
        if(!ok)continue;
        for(i=6;i<11;++i) {
            const char c=p[i];
            if(!((c>='A'&&c<='Z')||(c>='0'&&c<='9'))){ok=0;break;}
        }
        if(ok) {
            const char c=p[11];
            if((c>='A'&&c<='Z')||(c>='0'&&c<='9'))continue;
            memcpy(id,p,11);id[11]=0;
            return 1;
        }
    }
    return 0;
}
static uint64_t ik_prod_hash_gb(const uint8_t *bytes,size_t sz,const char *path) {
    uint64_t hash=UINT64_C(14695981039346656037);
    size_t i;
    if(bytes && sz) {
        for(i=0;i<sz;++i){hash^=bytes[i];hash*=UINT64_C(1099511628211);}
        return hash;
    }
    if(path) {
        FILE *f=fopen(path,"rb");
        unsigned char b[8192];
        size_t n,total=0;
        if(!f)return 0;
        while((n=fread(b,1,sizeof b,f))>0) {
            total+=n;
            if(total>64u*1024u*1024u){fclose(f);return 0;}
            for(i=0;i<n;++i){hash^=b[i];hash*=UINT64_C(1099511628211);}
        }
        if(ferror(f)||!total){fclose(f);return 0;}
        fclose(f);return hash;
    }
    return 0;
}
static int ik_prod_atomic_write(const char *path,const uint8_t *data,size_t n) {
    char tmp[560];
    int fd;
    size_t off=0;
    if(snprintf(tmp,sizeof tmp,"%s.tmp-%ld",path,(long)getpid())>=(int)sizeof tmp)
        return 0;
    fd=open(tmp,O_WRONLY|O_CREAT|O_EXCL,0600);
    if(fd<0)return 0;
    while(off<n) {
        ssize_t w=write(fd,data+off,n-off);
        if(w<0&&errno==EINTR)continue;
        if(w<=0){close(fd);unlink(tmp);return 0;}
        off+=(size_t)w;
    }
    if(fsync(fd)!=0){close(fd);unlink(tmp);return 0;}
    if(close(fd)!=0){unlink(tmp);return 0;}
    if(rename(tmp,path)!=0){unlink(tmp);return 0;}
    return 1;
}
static void ik_prod_sram_initialize(int argc,char **argv,const char *game_path,
                                     const uint8_t *gb,size_t gb_size) {
    uint64_t hash;
    size_t size;
    uint8_t *ram,*saved;
    struct stat st;
    FILE *f=NULL;
    char clv[16]={0},other[16]={0},legacy[512];
    int i;
    if(!core_retro_get_memory_data||!core_retro_get_memory_size)return;
    ram=(uint8_t*)core_retro_get_memory_data(RETRO_MEMORY_SAVE_RAM);
    size=core_retro_get_memory_size(RETRO_MEMORY_SAVE_RAM);
    if(!ram||!size){log_printf("IKSAVE SRAM: cartucho sin bateria o RAM externa\n");return;}
    if(size>1024u*1024u){log_printf("IKSAVE SRAM: tamano excesivo %zu, bloqueado\n",size);return;}
    hash=ik_prod_hash_gb(gb,gb_size,game_path);
    if(!hash){log_printf("IKSAVE SRAM: hash ROM no disponible, bloqueado\n");return;}
    if(mkdir(IK_PROD_SAVE_DIR,0755)!=0 && errno!=EEXIST){
        log_printf("IKSAVE SRAM: no pudo crear carpeta\n");return;
    }
    snprintf(ik_prod_sram_path,sizeof ik_prod_sram_path,
             IK_PROD_SAVE_DIR "/gb-%016llx.srm",(unsigned long long)hash);
    ik_prod_sram_shadow=(uint8_t*)malloc(size);
    if(!ik_prod_sram_shadow)return;
    ik_prod_sram_size=size;
    memcpy(ik_prod_sram_shadow,ram,size);
    for(i=1;i<argc;i++) {
        other[0]=0;
        if(ikcore_extract_clv_id(argv[i],other)){
            if(clv[0] && strcmp(clv,other)){clv[0]=0;break;}
            memcpy(clv,other,sizeof clv);
        }
    }
    if(!clv[0]) {
        const char *a=getenv("IKF6_ORIGINAL_ARCHIVE");
        if(a)(void)ikcore_extract_clv_id(a,clv);
    }
    if(stat(ik_prod_sram_path,&st)!=0 && errno==ENOENT && clv[0]) {
        /* Read-only import of #25 battery save into the new isolated SRAM
         * namespace. NEVER rewrite or delete the old .srm. */
        snprintf(legacy,sizeof legacy,"/var/lib/hakchi/ikcore-saves/%s.srm",clv);
        if(stat(legacy,&st)==0 && S_ISREG(st.st_mode) &&
           st.st_size==(off_t)size) {
            saved=(uint8_t*)malloc(size);
            if(saved) {
                f=fopen(legacy,"rb");
                if(f && fread(saved,1,size,f)==size &&
                   ik_prod_atomic_write(ik_prod_sram_path,saved,size)) {
                    memcpy(ram,saved,size);
                    memcpy(ik_prod_sram_shadow,saved,size);
                    log_printf("IKSAVE SRAM: importado desde #25 (origen intacto)\n");
                }
                if(f)fclose(f);
                f=NULL;
                free(saved);
            }
        }
    }
    if(stat(ik_prod_sram_path,&st)==0) {
        if(!S_ISREG(st.st_mode)||st.st_size!=(off_t)size) {
            log_printf("IKSAVE SRAM: tamano existente incompatible; BLOQUEADO\n");
            ik_prod_sram_blocked=1;return;
        }
        saved=(uint8_t*)malloc(size);
        if(!saved){ik_prod_sram_blocked=1;return;}
        f=fopen(ik_prod_sram_path,"rb");
        if(!f||fread(saved,1,size,f)!=size){
            if(f)fclose(f);free(saved);ik_prod_sram_blocked=1;return;
        }
        fclose(f);
        memcpy(ram,saved,size);
        memcpy(ik_prod_sram_shadow,saved,size);
        free(saved);
        log_printf("IKSAVE SRAM LOAD: %zu bytes %s\n",size,ik_prod_sram_path);
    }else if(errno==ENOENT) {
        log_printf("IKSAVE SRAM NEW: %zu bytes %s\n",size,ik_prod_sram_path);
    }else ik_prod_sram_blocked=1;
    ik_prod_sram_next_check=now_s()+5.0;
}
static void ik_prod_sram_rebase(void) {
    void *p;
    if(!ik_prod_sram_shadow||ik_prod_sram_blocked)return;
    p=core_retro_get_memory_data(RETRO_MEMORY_SAVE_RAM);
    if(p&&core_retro_get_memory_size(RETRO_MEMORY_SAVE_RAM)==ik_prod_sram_size)
        memcpy(ik_prod_sram_shadow,p,ik_prod_sram_size);
}
static void ik_prod_sram_flush(int force) {
    const uint8_t *ram;
    size_t n;
    if(!ik_prod_sram_shadow||ik_prod_sram_blocked||!ik_prod_sram_path[0])return;
    if(!force && now_s()<ik_prod_sram_next_check)return;
    ik_prod_sram_next_check=now_s()+5.0;
    ram=(const uint8_t*)core_retro_get_memory_data(RETRO_MEMORY_SAVE_RAM);
    n=core_retro_get_memory_size(RETRO_MEMORY_SAVE_RAM);
    if(!ram||n!=ik_prod_sram_size){ik_prod_sram_blocked=1;return;}
    if(!memcmp(ram,ik_prod_sram_shadow,n))return;
    if(!ik_prod_atomic_write(ik_prod_sram_path,ram,n)){
        log_printf("IKSAVE SRAM ERROR: escritura fallo %s\n",ik_prod_sram_path);
        ik_prod_sram_blocked=1;return;
    }
    memcpy(ik_prod_sram_shadow,ram,n);
    ++ik_prod_sram_writes;
    log_printf("IKSAVE SRAM SAVE: %zu bytes #%u %s\n",
               n,ik_prod_sram_writes,force?"exit":"autosave");
}
static void ik_prod_sram_finish(void) {
    free(ik_prod_sram_shadow);ik_prod_sram_shadow=NULL;
    ik_prod_sram_size=0;
}
