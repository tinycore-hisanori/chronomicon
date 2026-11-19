; crt0.s - RESET sequence, IRQ stub and vectors (see rom-builder design, "RESET sequence").

        .export __STARTUP__ : absolute = 1
        .export reset, irq
        .export reset_handler, nmi_handler, irq_handler

        .import _main, _oam, _palette_bg, _palette_sprite
        .import zerobss, copydata, screen_upload
        .import nmi
        .import __STACK_START__, __STACK_SIZE__
        .importzp c_sp
        .importzp _ppuctrl_shadow, _ppumask_shadow

PPUCTRL   = $2000
PPUMASK   = $2001
PPUSTATUS = $2002
PPUSCROLL = $2005
PPUADDR   = $2006
PPUDATA   = $2007
APUDMC    = $4010
APUSTATUS = $4015
APUFRAME  = $4017

        .segment "STARTUP"

.proc reset
        sei
        cld
        ldx #$40
        stx APUFRAME            ; APU frame IRQ off
        ldx #$00
        stx APUDMC              ; DMC IRQ off
        ldx #$FF
        txs                     ; hardware stack pointer
        inx                     ; X = 0
        stx PPUCTRL             ; NMI off
        stx PPUMASK             ; rendering off

vb1:    bit PPUSTATUS
        bpl vb1                 ; vblank 1
vb2:    bit PPUSTATUS
        bpl vb2                 ; vblank 2

        ; clear $0000-$07FF (no JSR, no stack use); X = 0
        lda #$00
clr:    sta $0000,x
        sta $0100,x
        sta $0200,x
        sta $0300,x
        sta $0400,x
        sta $0500,x
        sta $0600,x
        sta $0700,x
        inx
        bne clr

        ; cc65 C stack pointer
        lda #<(__STACK_START__ + __STACK_SIZE__)
        sta c_sp
        lda #>(__STACK_START__ + __STACK_SIZE__)
        sta c_sp+1

        jsr zerobss
        jsr copydata

        ; hide all 64 sprites (Y = $FF)
        lda #$FF
        ldx #$00
hide:   sta _oam,x
        inx
        inx
        inx
        inx
        bne hide

        lda #%00001011          ; pulse 1, pulse 2, noise
        sta APUSTATUS

        ; palette upload: 16 bytes BG then 16 bytes sprite at $3F00
        bit PPUSTATUS
        lda #$3F
        sta PPUADDR
        lda #$00
        sta PPUADDR
        ldx #$00
pal_bg: lda _palette_bg,x
        sta PPUDATA
        inx
        cpx #16
        bne pal_bg
        ldx #$00
pal_sp: lda _palette_sprite,x
        sta PPUDATA
        inx
        cpx #16
        bne pal_sp

        lda #$00
        jsr screen_upload       ; screen 0 into nametable $2000

        bit PPUSTATUS
        lda #$00
        sta PPUSCROLL
        sta PPUSCROLL

        lda #$A0
        sta _ppuctrl_shadow
        sta PPUCTRL             ; NMI on, 8x16 sprites
        lda #$1E
        sta _ppumask_shadow
        sta PPUMASK             ; BG + sprites on

        jsr _main
halt:   jmp halt
.endproc

reset_handler = reset
nmi_handler   = nmi
irq_handler   = irq

.proc irq
        rti
.endproc

        .segment "VECTORS"
        .word nmi
        .word reset
        .word irq
