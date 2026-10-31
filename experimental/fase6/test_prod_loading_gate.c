#include "ik_prod_loading_gate.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    IkProdLoadingGate g;
    unsigned i;
    ik_prod_gate_init(&g,1);
    for(i=0;i<100;i++)assert(!ik_prod_gate_frame(&g,0,1));
    /* PCT transfer in SGB game: keep splash while mGBA copies CHR/PCT. */
    assert(!ik_prod_gate_frame(&g,1,1));
    for(i=0;i<29;i++)assert(!ik_prod_gate_frame(&g,1,1));
    assert(ik_prod_gate_frame(&g,1,1));
    for(i=0;i<100;i++)assert(ik_prod_gate_frame(&g,1,1));
    ik_prod_gate_init(&g,0);
    for(i=0;i<1;i++)assert(!ik_prod_gate_frame(&g,0,1));
    assert(ik_prod_gate_frame(&g,0,1));
    ik_prod_gate_init(&g,1);
    for(i=0;i<119;i++)assert(!ik_prod_gate_frame(&g,0,1));
    assert(ik_prod_gate_frame(&g,0,1));
    ik_prod_gate_init(&g,1);
    for(i=0;i<7;i++)assert(!ik_prod_gate_frame(&g,0,0));
    assert(ik_prod_gate_frame(&g,0,0));
    ik_prod_gate_init(&g,1);
    assert(!ik_prod_gate_frame(&g,1,1));
    for(i=0;i<10;i++)assert(!ik_prod_gate_frame(&g,1,1));
    assert(!ik_prod_gate_frame(&g,2,1));
    for(i=0;i<30;i++)assert(ik_prod_gate_frame(&g,2,1)==(i==29));
    /* PCT just before the short guard: preserve the original 30 quiet frames. */
    ik_prod_gate_init(&g,1);
    for(i=0;i<90;i++)assert(!ik_prod_gate_frame(&g,0,1));
    assert(!ik_prod_gate_frame(&g,1,1));
    for(i=0;i<29;i++)assert(!ik_prod_gate_frame(&g,1,1));
    assert(ik_prod_gate_frame(&g,1,1));
    /* Late custom border after fallback remains visible normally. */
    ik_prod_gate_init(&g,1);
    for(i=0;i<119;i++)assert(!ik_prod_gate_frame(&g,0,1));
    assert(ik_prod_gate_frame(&g,0,1));
    assert(ik_prod_gate_frame(&g,1,1));
    puts("PASS: shortened loading handoff and 30-frame PCT safety retained");
    return 0;
}
