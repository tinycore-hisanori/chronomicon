; zp.s - zero-page variables shared between C and assembly.
; Declared in C by chrono_zp.h. cc65 prefixes C names with '_', so the exported
; symbols carry the underscore (C `frame_flag` == asm `_frame_flag`).
; NMI-only temporaries (nmi_budget, nmi_len) live in nmi.s and are not exported.

        .segment "ZEROPAGE"

        .exportzp _frame_flag, _vram_ready, _vq_head, _vq_tail
        .exportzp _ppuctrl_shadow, _ppumask_shadow

_frame_flag:      .res 1    ; NMI sets 1, wait_frame sets 0
_vram_ready:      .res 1    ; wait_frame sets 1, NMI and load_screen clear
_vq_head:         .res 1    ; VRAM queue read index (NMI consumer)
_vq_tail:         .res 1    ; VRAM queue write index (vramq_push producer)
_ppuctrl_shadow:  .res 1    ; last value written to PPUCTRL
_ppumask_shadow:  .res 1    ; last value written to PPUMASK
