#ifndef IK_PROD_LOADING_GATE_H
#define IK_PROD_LOADING_GATE_H
#include <stdint.h>
/* Presentation only. Never stops emulation, PCM mixing, or SGB packet input.
 * A SGB-enhanced game has time to upload CHR_TRN/PCT_TRN before visibility.
 * A plain DMG game reveals the stock SGB border immediately.
 * The finite fallback prevents games with no PCT from staying covered forever.
 */
typedef struct {
    uint32_t frames, pct_last, pct_quiet;
    uint8_t enhanced, visible;
} IkProdLoadingGate;
static inline void ik_prod_gate_init(IkProdLoadingGate *g, int enhanced) {
    g->frames=0;g->pct_last=0;g->pct_quiet=0;
    g->enhanced=(uint8_t)(!!enhanced);g->visible=0;
}
static inline int ik_prod_gate_frame(IkProdLoadingGate *g, uint32_t pct, int full_sgb_frame) {
    if(g->visible)return 1;
    ++g->frames;
    if(pct != g->pct_last) {g->pct_last=pct;g->pct_quiet=0;}
    else if(g->pct_quiet<65535u)++g->pct_quiet;
    /* Transfers need 5 frames; allow 30 for two halves and packet bursts. */
    if(full_sgb_frame && pct && g->pct_quiet>=30u)g->visible=1;
    else if(!g->enhanced && g->frames>=4u)g->visible=1;
    else if(g->enhanced && g->frames>=480u)g->visible=1;
    else if(!full_sgb_frame && g->frames>=16u)g->visible=1;
    return g->visible;
}
#endif
