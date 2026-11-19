; nmi.s - NMI handler and VRAM queue consumer (vram_apply).
;
; Imports come before the ZEROPAGE segment switch: ca65 gives an import the
; address size of the current segment, so _vq_buf would otherwise be assumed
; to be zero page (link-time range error).
.importzp _frame_flag, _vram_ready, _vq_head, _vq_tail, _ppuctrl_shadow
.import   _vq_buf: absolute

.export nmi

; NMI-only zero-page temporaries. Not exported: no other file and no C code
; refers to them. No cc65 shared zero-page symbol is used here (Requirement 10.7).
.segment "ZEROPAGE"
nmi_budget: .res 1
nmi_len:    .res 1

PPUCTRL   = $2000
PPUSTATUS = $2002
OAMADDR   = $2003
PPUSCROLL = $2005
PPUADDR   = $2006
PPUDATA   = $2007
OAMDMA    = $4014

.segment "CODE"

.proc nmi
    pha                         ; save A, X, Y
    txa
    pha
    tya
    pha

    lda #0
    sta OAMADDR                 ; first PPU write
    lda #$02
    sta OAMDMA                  ; OAM DMA from $0200

    lda _vram_ready
    beq scroll                  ; nothing is written while the flag is clear
    jsr vram_apply              ; at most 64 payload bytes
    lda #0
    sta _vram_ready

scroll:
    bit PPUSTATUS               ; reset the address latch (read only)
    lda #0
    sta PPUSCROLL               ; scroll writes are the last PPU writes ...
    sta PPUSCROLL
    lda _ppuctrl_shadow
    sta PPUCTRL                 ; ... followed by the nametable bits of PPUCTRL
    lda #1
    sta _frame_flag

    pla                         ; restore Y, X, A
    tay
    pla
    tax
    pla
    rti
.endproc

; Applies whole queue entries [len][addr_hi][addr_lo][payload...] in order.
; X = read position, Y = payload counter.
.proc vram_apply
    ldx _vq_head
    lda #64
    sta nmi_budget
next:
    cpx _vq_tail
    beq done                    ; queue empty
    lda _vq_buf,x               ; entry length
    ; ZEROLEN-GUARD: a zero length is never written, the queue is discarded
    beq corrupt
    sta nmi_len
    lda nmi_budget
    sec
    sbc nmi_len
    bcc done                    ; len > budget: entry stays queued, X at its start
    sta nmi_budget
    inx
    lda _vq_buf,x
    sta PPUADDR                 ; addr_hi
    inx
    lda _vq_buf,x
    sta PPUADDR                 ; addr_lo
    inx
    ldy nmi_len
copy:
    lda _vq_buf,x
    sta PPUDATA
    inx
    dey
    bne copy
    stx _vq_head                ; whole entry consumed
    jmp next
done:
    cpx _vq_tail
    bne ret                     ; entries left for a later NMI
corrupt:
    lda #0                      ; drained, or corrupt: reset the queue
    sta _vq_head
    sta _vq_tail
ret:
    rts
.endproc
