; screen.s - full-screen nametable upload and load_screen().
;
; screen_upload: A = screen index (caller guarantees it is in range and that
; rendering is off). Writes 960 nametable bytes and 64 attribute bytes to
; $2000. Not reachable from the NMI handler, so it may use ptr1/ptr2.
;
; void __fastcall__ load_screen(unsigned char n): n arrives in A.

.setcpu "6502"

.import _wait_frame
.import _screen_count
.import screen_nt_lo, screen_nt_hi, screen_at_lo, screen_at_hi
.importzp ptr1, ptr2
.importzp _vram_ready, _vq_head, _vq_tail, _ppuctrl_shadow, _ppumask_shadow

.export screen_upload
.export _load_screen

PPUCTRL   = $2000
PPUMASK   = $2001
PPUSTATUS = $2002
PPUSCROLL = $2005
PPUADDR   = $2006
PPUDATA   = $2007

.segment "BSS"

load_screen_n: .res 1

.segment "CODE"

.proc screen_upload
    tax
    lda screen_nt_lo,x
    sta ptr1
    lda screen_nt_hi,x
    sta ptr1+1
    lda screen_at_lo,x
    sta ptr2
    lda screen_at_hi,x
    sta ptr2+1

    bit PPUSTATUS
    lda #$20
    sta PPUADDR
    lda #$00
    sta PPUADDR

    ; 960 nametable bytes = 3 full pages + 192 bytes
    ldx #3
page_loop:
    ldy #0
page_byte:
    lda (ptr1),y
    sta PPUDATA
    iny
    bne page_byte
    inc ptr1+1
    dex
    bne page_loop

    ldy #0
tail_byte:
    lda (ptr1),y
    sta PPUDATA
    iny
    cpy #192
    bne tail_byte

    ; 64 attribute bytes
    ldy #0
attr_byte:
    lda (ptr2),y
    sta PPUDATA
    iny
    cpy #64
    bne attr_byte
    rts
.endproc

.proc _load_screen
    cmp _screen_count
    bcc in_range
    rts                     ; out of range: no changes

in_range:
    sta load_screen_n
    jsr _wait_frame

    lda _ppuctrl_shadow
    and #$7F                ; NMI off while the large write runs
    sta PPUCTRL
    lda #0
    sta PPUMASK             ; rendering off

    lda load_screen_n
    jsr screen_upload

    lda #0
    sta _vq_head
    sta _vq_tail
    sta _vram_ready

wait_vblank:
    bit PPUSTATUS
    bpl wait_vblank

    bit PPUSTATUS
    lda #0
    sta PPUSCROLL
    sta PPUSCROLL

    lda _ppuctrl_shadow
    sta PPUCTRL
    lda _ppumask_shadow
    sta PPUMASK
    rts
.endproc
