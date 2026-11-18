---
inclusion: manual
---
# Real-hardware path (for the demo video finale)

## Cartridge board: TINYLABO NROM-FLASH Rev0.2 (60-pin, ordered from PCBWay)
- 2-layer, 90x46.1mm, 1.2mm thick, ENIG gold fingers with 45° bevel
- U1 PRG: SST39SF010A (PLCC-32 socket). A0–A14 = CPU A0–A14, A15+ = GND, /CE=/ROMSEL, /OE=GND, /WE=5V
- U2 CHR: SST39SF010A (PLCC-32 socket). A0–A12 = PPU A0–A12, A13+ = GND, /CE=PPU A13, /OE=PPU /RD, /WE=5V
- JP1 mirroring: V (iNES vertical) = PPU A10, H = PPU A11
- Hard-wired: pins 30↔31 (5V; some RF board revisions need pin 31 for video), 45↔46 (audio pass-through),
  48↔49 (CIRAM /CE = PPU /A13)
- Burn: PRG = .nes bytes [16 .. 16+32768), CHR = next 8192 bytes, both at chip offset 0
- First power-up: insert **without chips**, measure +5V between socket pin 32 and pin 16 before inserting chips

## Writer: Arduino Mega 2560 flash shield (DIP-32 ZIF, via PLCC32→DIP32 adapter)
- DQ0–7 = D22–D29 (PORTA), A0–A7 = D37–D30 (PORTC), A8–A15 = D49–D42 (PORTL),
  A16–A18 = D50–D52, CE#=D38, OE#=D39, WE#=D40
