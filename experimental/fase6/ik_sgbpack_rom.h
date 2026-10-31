#ifndef IK_F6_SGBPACK_ROM_H
#define IK_F6_SGBPACK_ROM_H
#include <stddef.h>
#include <stdint.h>
/* Load the embedded original GB ROM from an existing SGBPACK1 container.
 * Validates magic, v1, all three segment CRC32s and payload CRC32 before
 * allocating output; on error output pointers are left empty.
 * Never modifies, repacks, or distributes any firmware or ROM. */
int ik_f6_sgbpack_extract_gb(const char *pack_path,uint8_t **rom,size_t *size,
                            char *why,size_t why_size);
#endif
