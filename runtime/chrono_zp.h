/* chrono_zp.h - zero-page variables shared between C and assembly (defined in zp.s).
 *
 * Naming: cc65 prefixes every C identifier with '_' in assembly. The C name
 * `frame_flag` is therefore the asm symbol `_frame_flag`, so zp.s exports the
 * underscored names and the assembly files (nmi.s, crt0.s, screen.s) use them too.
 * `#pragma zpsym` makes cc65 emit `.importzp _name` and use zero-page addressing.
 */
#ifndef CHRONO_ZP_H
#define CHRONO_ZP_H

extern volatile unsigned char frame_flag;
extern volatile unsigned char vram_ready;
extern unsigned char vq_head;
extern unsigned char vq_tail;
extern unsigned char ppuctrl_shadow;
extern unsigned char ppumask_shadow;
#pragma zpsym ("frame_flag")
#pragma zpsym ("vram_ready")
#pragma zpsym ("vq_head")
#pragma zpsym ("vq_tail")
#pragma zpsym ("ppuctrl_shadow")
#pragma zpsym ("ppumask_shadow")

#endif
