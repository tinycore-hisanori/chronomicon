/*
 * tinynes — an 8-bit home console emulator for NROM (mapper 0) cartridges only
 * No dependencies. Runs in the browser and in Node.
 *
 *   const nes = new NES({ sampleRate: 48000 });
 *   nes.load(uint8ArrayOfNesFile);
 *   nes.frame();                 // advance one frame
 *   nes.frameBuffer              // Uint32Array(256*240)  0xAABBGGRR (ready for a canvas ImageData)
 *   nes.setButton(0, NES.BTN.A, true)
 *   nes.audioOut = (samples: Float32Array) => {...}   // called once per frame
 *
 * Coverage: CPU 6502 (official opcodes + common unofficial ones), PPU (per-scanline rendering,
 *            loopy scroll registers, 8x8/8x16 sprites, sprite 0 hit, overflow flag),
 *            APU (2 pulse, triangle, noise, frame counter; DMC is silent), two controllers.
 *            Cartridges: NROM-128 / NROM-256 (PRG 16/32 KB, CHR-ROM 8 KB or CHR-RAM).
 *
 * MIT License. Copyright (c) 2026 Tiny Core Inc.
 * See the LICENSE file in the repository root for the full license text.
 */
(function (root) {
  "use strict";

  // ------------------------------------------------------------ 2C02 palette (RGB)
  const PALETTE_RGB = [
    0x545454, 0x001e74, 0x081090, 0x300088, 0x440064, 0x5c0030, 0x540400, 0x3c1800,
    0x202a00, 0x083a00, 0x004000, 0x003c00, 0x00323c, 0x000000, 0x000000, 0x000000,
    0x989698, 0x084cc4, 0x3032ec, 0x5c1ee4, 0x8814b0, 0xa01464, 0x982220, 0x783c00,
    0x545a00, 0x287200, 0x087c00, 0x007628, 0x006678, 0x000000, 0x000000, 0x000000,
    0xeceeec, 0x4c9aec, 0x787cec, 0xb062ec, 0xe454ec, 0xec58b4, 0xec6a64, 0xd48820,
    0xa0aa00, 0x74c400, 0x4cd020, 0x38cc6c, 0x38b4cc, 0x3c3c3c, 0x000000, 0x000000,
    0xeceeec, 0xa8ccec, 0xbcbcec, 0xd4b2ec, 0xecaeec, 0xecaed4, 0xecb4b0, 0xe4c490,
    0xccd278, 0xb4de78, 0xa8e290, 0x98e2b4, 0xa0d6e4, 0xa0a2a0, 0x000000, 0x000000,
  ];
  const PALETTE_ABGR = new Uint32Array(64);
  for (let i = 0; i < 64; i++) {
    const c = PALETTE_RGB[i];
    PALETTE_ABGR[i] = 0xff000000 | ((c & 0xff) << 16) | (c & 0xff00) | ((c >> 16) & 0xff);
  }

  // ------------------------------------------------------------ 6502 opcode table
  const OPS = (
    "BRK imp,ORA izx,KIL imp,SLO izx,NOP zp,ORA zp,ASL zp,SLO zp,PHP imp,ORA imm,ASL acc,ANC imm,NOP abs,ORA abs,ASL abs,SLO abs," +
    "BPL rel,ORA izy,KIL imp,SLO izy,NOP zpx,ORA zpx,ASL zpx,SLO zpx,CLC imp,ORA aby,NOP imp,SLO aby,NOP abx,ORA abx,ASL abx,SLO abx," +
    "JSR abs,AND izx,KIL imp,RLA izx,BIT zp,AND zp,ROL zp,RLA zp,PLP imp,AND imm,ROL acc,ANC imm,BIT abs,AND abs,ROL abs,RLA abs," +
    "BMI rel,AND izy,KIL imp,RLA izy,NOP zpx,AND zpx,ROL zpx,RLA zpx,SEC imp,AND aby,NOP imp,RLA aby,NOP abx,AND abx,ROL abx,RLA abx," +
    "RTI imp,EOR izx,KIL imp,SRE izx,NOP zp,EOR zp,LSR zp,SRE zp,PHA imp,EOR imm,LSR acc,ALR imm,JMP abs,EOR abs,LSR abs,SRE abs," +
    "BVC rel,EOR izy,KIL imp,SRE izy,NOP zpx,EOR zpx,LSR zpx,SRE zpx,CLI imp,EOR aby,NOP imp,SRE aby,NOP abx,EOR abx,LSR abx,SRE abx," +
    "RTS imp,ADC izx,KIL imp,RRA izx,NOP zp,ADC zp,ROR zp,RRA zp,PLA imp,ADC imm,ROR acc,ARR imm,JMP ind,ADC abs,ROR abs,RRA abs," +
    "BVS rel,ADC izy,KIL imp,RRA izy,NOP zpx,ADC zpx,ROR zpx,RRA zpx,SEI imp,ADC aby,NOP imp,RRA aby,NOP abx,ADC abx,ROR abx,RRA abx," +
    "NOP imm,STA izx,NOP imm,SAX izx,STY zp,STA zp,STX zp,SAX zp,DEY imp,NOP imm,TXA imp,XAA imm,STY abs,STA abs,STX abs,SAX abs," +
    "BCC rel,STA izy,KIL imp,AHX izy,STY zpx,STA zpx,STX zpy,SAX zpy,TYA imp,STA aby,TXS imp,TAS aby,SHY abx,STA abx,SHX aby,AHX aby," +
    "LDY imm,LDA izx,LDX imm,LAX izx,LDY zp,LDA zp,LDX zp,LAX zp,TAY imp,LDA imm,TAX imp,LAX imm,LDY abs,LDA abs,LDX abs,LAX abs," +
    "BCS rel,LDA izy,KIL imp,LAX izy,LDY zpx,LDA zpx,LDX zpy,LAX zpy,CLV imp,LDA aby,TSX imp,LAS aby,LDY abx,LDA abx,LDX aby,LAX aby," +
    "CPY imm,CMP izx,NOP imm,DCP izx,CPY zp,CMP zp,DEC zp,DCP zp,INY imp,CMP imm,DEX imp,AXS imm,CPY abs,CMP abs,DEC abs,DCP abs," +
    "BNE rel,CMP izy,KIL imp,DCP izy,NOP zpx,CMP zpx,DEC zpx,DCP zpx,CLD imp,CMP aby,NOP imp,DCP aby,NOP abx,CMP abx,DEC abx,DCP abx," +
    "CPX imm,SBC izx,NOP imm,ISB izx,CPX zp,SBC zp,INC zp,ISB zp,INX imp,SBC imm,NOP imp,SBC imm,CPX abs,SBC abs,INC abs,ISB abs," +
    "BEQ rel,SBC izy,KIL imp,ISB izy,NOP zpx,SBC zpx,INC zpx,ISB zpx,SED imp,SBC aby,NOP imp,ISB aby,NOP abx,SBC abx,INC abx,ISB abx"
  ).split(",").map((s) => s.split(" "));

  const CYCLES = [
    7, 6, 2, 8, 3, 3, 5, 5, 3, 2, 2, 2, 4, 4, 6, 6, 2, 5, 2, 8, 4, 4, 6, 6, 2, 4, 2, 7, 4, 4, 7, 7,
    6, 6, 2, 8, 3, 3, 5, 5, 4, 2, 2, 2, 4, 4, 6, 6, 2, 5, 2, 8, 4, 4, 6, 6, 2, 4, 2, 7, 4, 4, 7, 7,
    6, 6, 2, 8, 3, 3, 5, 5, 3, 2, 2, 2, 3, 4, 6, 6, 2, 5, 2, 8, 4, 4, 6, 6, 2, 4, 2, 7, 4, 4, 7, 7,
    6, 6, 2, 8, 3, 3, 5, 5, 4, 2, 2, 2, 5, 4, 6, 6, 2, 5, 2, 8, 4, 4, 6, 6, 2, 4, 2, 7, 4, 4, 7, 7,
    2, 6, 2, 6, 3, 3, 3, 3, 2, 2, 2, 2, 4, 4, 4, 4, 2, 6, 2, 6, 4, 4, 4, 4, 2, 5, 2, 5, 5, 5, 5, 5,
    2, 6, 2, 6, 3, 3, 3, 3, 2, 2, 2, 2, 4, 4, 4, 4, 2, 5, 2, 5, 4, 4, 4, 4, 2, 4, 2, 4, 4, 4, 4, 4,
    2, 6, 2, 8, 3, 3, 5, 5, 2, 2, 2, 2, 4, 4, 6, 6, 2, 5, 2, 8, 4, 4, 6, 6, 2, 4, 2, 7, 4, 4, 7, 7,
    2, 6, 2, 8, 3, 3, 5, 5, 2, 2, 2, 2, 4, 4, 6, 6, 2, 5, 2, 8, 4, 4, 6, 6, 2, 4, 2, 7, 4, 4, 7, 7,
  ];
  // read instructions that take +1 cycle on a page cross
  const PAGE_PENALTY = new Set(["LDA", "LDX", "LDY", "EOR", "AND", "ORA", "ADC", "SBC", "CMP", "LAX", "NOP", "LAS"]);

  const FLAG_C = 0x01, FLAG_Z = 0x02, FLAG_I = 0x04, FLAG_D = 0x08, FLAG_B = 0x10, FLAG_U = 0x20, FLAG_V = 0x40, FLAG_N = 0x80;

  // ------------------------------------------------------------ APU tables
  const LENGTH_TABLE = [10, 254, 20, 2, 40, 4, 80, 6, 160, 8, 60, 10, 14, 12, 26, 14,
    12, 16, 24, 18, 48, 20, 96, 22, 192, 24, 72, 26, 16, 28, 32, 30];
  const DUTY = [[0, 1, 0, 0, 0, 0, 0, 0], [0, 1, 1, 0, 0, 0, 0, 0], [0, 1, 1, 1, 1, 0, 0, 0], [1, 0, 0, 1, 1, 1, 1, 1]];
  const TRI_SEQ = [15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15];
  const NOISE_PERIOD = [4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068];

  class Pulse {
    constructor(isFirst) { this.first = isFirst; this.reset(); }
    reset() {
      this.enabled = false; this.duty = 0; this.seq = 0; this.timer = 0; this.period = 0;
      this.length = 0; this.halt = false; this.constVol = false; this.vol = 0;
      this.envStart = false; this.envDiv = 0; this.envDecay = 0;
      this.swEnabled = false; this.swPeriod = 0; this.swNeg = false; this.swShift = 0; this.swReload = false; this.swDiv = 0;
    }
    write(reg, v) {
      switch (reg) {
        case 0: this.duty = v >> 6; this.halt = !!(v & 0x20); this.constVol = !!(v & 0x10); this.vol = v & 15; break;
        case 1: this.swEnabled = !!(v & 0x80); this.swPeriod = (v >> 4) & 7; this.swNeg = !!(v & 8); this.swShift = v & 7; this.swReload = true; break;
        case 2: this.period = (this.period & 0x700) | v; break;
        case 3:
          this.period = (this.period & 0xff) | ((v & 7) << 8);
          if (this.enabled) this.length = LENGTH_TABLE[v >> 3];
          this.seq = 0; this.envStart = true; break;
      }
    }
    clockTimer() {
      if (this.timer === 0) { this.timer = this.period; this.seq = (this.seq + 1) & 7; } else this.timer--;
    }
    targetPeriod() {
      const ch = this.period >> this.swShift;
      return this.swNeg ? this.period - ch - (this.first ? 1 : 0) : this.period + ch;
    }
    clockEnvelope() {
      if (this.envStart) { this.envStart = false; this.envDecay = 15; this.envDiv = this.vol; }
      else if (this.envDiv === 0) { this.envDiv = this.vol; if (this.envDecay > 0) this.envDecay--; else if (this.halt) this.envDecay = 15; }
      else this.envDiv--;
    }
    clockHalf() {
      if (!this.halt && this.length > 0) this.length--;
      const t = this.targetPeriod();
      if (this.swDiv === 0 && this.swEnabled && this.swShift > 0 && this.period >= 8 && t <= 0x7ff) this.period = t;
      if (this.swDiv === 0 || this.swReload) { this.swDiv = this.swPeriod; this.swReload = false; } else this.swDiv--;
    }
    output() {
      if (!this.enabled || this.length === 0 || this.period < 8 || this.targetPeriod() > 0x7ff) return 0;
      if (!DUTY[this.duty][this.seq]) return 0;
      return this.constVol ? this.vol : this.envDecay;
    }
  }

  class Triangle {
    constructor() { this.reset(); }
    reset() { this.enabled = false; this.control = false; this.linReload = 0; this.lin = 0; this.linFlag = false; this.period = 0; this.timer = 0; this.seq = 0; this.length = 0; }
    write(reg, v) {
      switch (reg) {
        case 0: this.control = !!(v & 0x80); this.linReload = v & 0x7f; break;
        case 2: this.period = (this.period & 0x700) | v; break;
        case 3: this.period = (this.period & 0xff) | ((v & 7) << 8); if (this.enabled) this.length = LENGTH_TABLE[v >> 3]; this.linFlag = true; break;
      }
    }
    clockTimer() {
      if (this.timer === 0) { this.timer = this.period; if (this.length > 0 && this.lin > 0 && this.period >= 2) this.seq = (this.seq + 1) & 31; }
      else this.timer--;
    }
    clockQuarter() {
      if (this.linFlag) this.lin = this.linReload; else if (this.lin > 0) this.lin--;
      if (!this.control) this.linFlag = false;
    }
    clockHalf() { if (!this.control && this.length > 0) this.length--; }
    output() { return this.enabled ? TRI_SEQ[this.seq] : 0; }
  }

  class Noise {
    constructor() { this.reset(); }
    reset() { this.enabled = false; this.halt = false; this.constVol = false; this.vol = 0; this.mode = false; this.period = 4; this.timer = 0; this.shift = 1; this.length = 0; this.envStart = false; this.envDiv = 0; this.envDecay = 0; }
    write(reg, v) {
      switch (reg) {
        case 0: this.halt = !!(v & 0x20); this.constVol = !!(v & 0x10); this.vol = v & 15; break;
        case 2: this.mode = !!(v & 0x80); this.period = NOISE_PERIOD[v & 15]; break;
        case 3: if (this.enabled) this.length = LENGTH_TABLE[v >> 3]; this.envStart = true; break;
      }
    }
    clockTimer() {
      if (this.timer === 0) {
        this.timer = this.period;
        const fb = (this.shift & 1) ^ ((this.shift >> (this.mode ? 6 : 1)) & 1);
        this.shift = (this.shift >> 1) | (fb << 14);
      } else this.timer--;
    }
    clockEnvelope() { Pulse.prototype.clockEnvelope.call(this); }
    clockHalf() { if (!this.halt && this.length > 0) this.length--; }
    output() {
      if (!this.enabled || this.length === 0 || (this.shift & 1)) return 0;
      return this.constVol ? this.vol : this.envDecay;
    }
  }

  // ------------------------------------------------------------ core
  class NES {
    constructor(opts = {}) {
      this.sampleRate = opts.sampleRate || 48000;
      this.ram = new Uint8Array(0x800);
      this.prgRam = new Uint8Array(0x2000);
      this.vram = new Uint8Array(0x800);
      this.pal = new Uint8Array(32);
      this.oam = new Uint8Array(256);
      this.frameBuffer = new Uint32Array(256 * 240);
      this.indexBuffer = new Uint8Array(256 * 240);   // NES color index per pixel (for tests)
      this.pad = [0, 0];
      this.audioOut = null;
      this.p1 = new Pulse(true); this.p2 = new Pulse(false); this.tri = new Triangle(); this.noise = new Noise();
      this.cart = null;
    }

    // ---------------------------------------------------------- cartridge
    load(bytes) {
      bytes = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
      if (bytes[0] !== 0x4e || bytes[1] !== 0x45 || bytes[2] !== 0x53 || bytes[3] !== 0x1a) throw new Error("not an iNES file");
      const prgBanks = bytes[4], chrBanks = bytes[5], f6 = bytes[6], f7 = bytes[7];
      const mapper = (f6 >> 4) | (f7 & 0xf0);
      if (mapper !== 0) throw new Error(`mapper ${mapper} is not supported (NROM = 0 only)`);
      let off = 16 + ((f6 & 4) ? 512 : 0);
      const prg = bytes.slice(off, off + prgBanks * 0x4000); off += prgBanks * 0x4000;
      const chr = chrBanks ? bytes.slice(off, off + chrBanks * 0x2000) : new Uint8Array(0x2000);
      this.cart = { prg, chr, chrRam: chrBanks === 0, prgMask: prg.length - 1, vertical: !!(f6 & 1), fourScreen: !!(f6 & 8) };
      this.reset();
    }

    reset() {
      this.a = 0; this.x = 0; this.y = 0; this.sp = 0xfd; this.p = FLAG_I | FLAG_U;
      this.pc = this.read16(0xfffc);
      this.cycles = 7; this.stall = 0; this.nmiPending = false; this.irqLine = false;
      // PPU
      this.ctrl = 0; this.mask = 0; this.status = 0; this.oamAddr = 0;
      this.v = 0; this.t = 0; this.fx = 0; this.w = 0; this.readBuf = 0; this.openBus = 0;
      this.scanline = 0; this.dot = 21; this.frameCount = 0; this.oddFrame = false;
      // APU
      [this.p1, this.p2, this.tri, this.noise].forEach((c) => c.reset());
      this.fcMode = 0; this.fcIrqInhibit = true; this.fcCycle = 0; this.apuOdd = false;
      this.sampleAcc = 0; this.samples = []; this.hp = 0; this.hpPrev = 0; this.lp = 0;
      this.padShift = [0, 0]; this.strobe = 0;
    }

    // ---------------------------------------------------------- CPU bus
    read(addr) {
      addr &= 0xffff;
      if (addr < 0x2000) return this.ram[addr & 0x7ff];
      if (addr < 0x4000) return this.ppuRead(addr & 7);
      if (addr === 0x4015) {
        return (this.p1.length > 0 ? 1 : 0) | (this.p2.length > 0 ? 2 : 0) | (this.tri.length > 0 ? 4 : 0) | (this.noise.length > 0 ? 8 : 0);
      }
      if (addr === 0x4016 || addr === 0x4017) {
        const i = addr - 0x4016;
        if (this.strobe) return 0x40 | (this.pad[i] & 1);
        const bit = this.padShift[i] & 1;
        this.padShift[i] = (this.padShift[i] >> 1) | 0x80;
        return 0x40 | bit;
      }
      if (addr < 0x6000) return 0;
      if (addr < 0x8000) return this.prgRam[addr - 0x6000];
      return this.cart.prg[(addr - 0x8000) & this.cart.prgMask];
    }

    write(addr, v) {
      addr &= 0xffff; v &= 0xff;
      if (addr < 0x2000) { this.ram[addr & 0x7ff] = v; return; }
      if (addr < 0x4000) { this.ppuWrite(addr & 7, v); return; }
      if (addr === 0x4014) {           // OAM DMA
        const base = v << 8;
        for (let i = 0; i < 256; i++) this.oam[(this.oamAddr + i) & 0xff] = this.read(base + i);
        this.stall += 513 + (this.cycles & 1);
        return;
      }
      if (addr === 0x4016) {
        this.strobe = v & 1;
        if (this.strobe) { this.padShift[0] = this.pad[0]; this.padShift[1] = this.pad[1]; }
        return;
      }
      if (addr < 0x4014) {
        const ch = [this.p1, this.p2, this.tri, this.noise][(addr - 0x4000) >> 2];
        if (ch) ch.write(addr & 3, v);
        return;
      }
      if (addr === 0x4015) {
        this.p1.enabled = !!(v & 1); this.p2.enabled = !!(v & 2); this.tri.enabled = !!(v & 4); this.noise.enabled = !!(v & 8);
        [this.p1, this.p2, this.tri, this.noise].forEach((c) => { if (!c.enabled) c.length = 0; });
        return;
      }
      if (addr === 0x4017) {
        this.fcMode = v >> 7; this.fcIrqInhibit = !!(v & 0x40); this.fcCycle = 0;
        if (this.fcMode) { this.quarterFrame(); this.halfFrame(); }
        return;
      }
      if (addr >= 0x6000 && addr < 0x8000) this.prgRam[addr - 0x6000] = v;
    }

    read16(a) { return this.read(a) | (this.read((a + 1) & 0xffff) << 8); }
    read16bug(a) { return this.read(a) | (this.read((a & 0xff00) | ((a + 1) & 0xff)) << 8); }
    push(v) { this.write(0x100 | this.sp, v); this.sp = (this.sp - 1) & 0xff; }
    pull() { this.sp = (this.sp + 1) & 0xff; return this.read(0x100 | this.sp); }
    setZN(v) { this.p = (this.p & ~(FLAG_Z | FLAG_N)) | (v ? 0 : FLAG_Z) | (v & FLAG_N); }
    flag(f, on) { if (on) this.p |= f; else this.p &= ~f; }

    // ---------------------------------------------------------- CPU: one instruction
    step() {
      if (this.stall > 0) { this.stall--; return 1; }
      if (this.nmiPending) {
        this.nmiPending = false;
        this.push(this.pc >> 8); this.push(this.pc & 0xff); this.push((this.p | FLAG_U) & ~FLAG_B);
        this.p |= FLAG_I; this.pc = this.read16(0xfffa); this.cycles += 7; return 7;
      }
      const opcode = this.read(this.pc);
      const [mn, mode] = OPS[opcode];
      let cyc = CYCLES[opcode];
      let addr = 0, crossed = false;
      const pc1 = (this.pc + 1) & 0xffff;
      switch (mode) {
        case "imp": case "acc": this.pc = pc1; break;
        case "imm": addr = pc1; this.pc = (this.pc + 2) & 0xffff; break;
        case "zp": addr = this.read(pc1); this.pc = (this.pc + 2) & 0xffff; break;
        case "zpx": addr = (this.read(pc1) + this.x) & 0xff; this.pc = (this.pc + 2) & 0xffff; break;
        case "zpy": addr = (this.read(pc1) + this.y) & 0xff; this.pc = (this.pc + 2) & 0xffff; break;
        case "abs": addr = this.read16(pc1); this.pc = (this.pc + 3) & 0xffff; break;
        case "abx": { const b = this.read16(pc1); addr = (b + this.x) & 0xffff; crossed = (b & 0xff00) !== (addr & 0xff00); this.pc = (this.pc + 3) & 0xffff; break; }
        case "aby": { const b = this.read16(pc1); addr = (b + this.y) & 0xffff; crossed = (b & 0xff00) !== (addr & 0xff00); this.pc = (this.pc + 3) & 0xffff; break; }
        case "ind": addr = this.read16bug(this.read16(pc1)); this.pc = (this.pc + 3) & 0xffff; break;
        case "izx": { const z = (this.read(pc1) + this.x) & 0xff; addr = this.read(z) | (this.read((z + 1) & 0xff) << 8); this.pc = (this.pc + 2) & 0xffff; break; }
        case "izy": { const z = this.read(pc1); const b = this.read(z) | (this.read((z + 1) & 0xff) << 8); addr = (b + this.y) & 0xffff; crossed = (b & 0xff00) !== (addr & 0xff00); this.pc = (this.pc + 2) & 0xffff; break; }
        case "rel": { const off = this.read(pc1); this.pc = (this.pc + 2) & 0xffff; addr = (this.pc + (off < 0x80 ? off : off - 0x100)) & 0xffff; break; }
      }
      if (crossed && PAGE_PENALTY.has(mn)) cyc++;
      const branch = (cond) => {
        if (cond) { cyc += ((this.pc & 0xff00) !== (addr & 0xff00)) ? 2 : 1; this.pc = addr; }
      };
      const rmw = (fn) => {
        if (mode === "acc") { this.a = fn(this.a); this.setZN(this.a); return this.a; }
        const r = fn(this.read(addr)); this.write(addr, r); this.setZN(r); return r;
      };
      const adc = (m) => {
        const s = this.a + m + (this.p & FLAG_C);
        this.flag(FLAG_C, s > 0xff); this.flag(FLAG_V, (~(this.a ^ m) & (this.a ^ s) & 0x80) !== 0);
        this.a = s & 0xff; this.setZN(this.a);
      };
      const cmp = (r, m) => { this.flag(FLAG_C, r >= m); this.setZN((r - m) & 0xff); };
      const asl = (v) => { this.flag(FLAG_C, v & 0x80); return (v << 1) & 0xff; };
      const lsr = (v) => { this.flag(FLAG_C, v & 1); return v >> 1; };
      const rol = (v) => { const c = this.p & FLAG_C; this.flag(FLAG_C, v & 0x80); return ((v << 1) | c) & 0xff; };
      const ror = (v) => { const c = this.p & FLAG_C; this.flag(FLAG_C, v & 1); return (v >> 1) | (c << 7); };

      switch (mn) {
        case "LDA": this.a = this.read(addr); this.setZN(this.a); break;
        case "LDX": this.x = this.read(addr); this.setZN(this.x); break;
        case "LDY": this.y = this.read(addr); this.setZN(this.y); break;
        case "LAX": this.a = this.x = this.read(addr); this.setZN(this.a); break;
        case "STA": this.write(addr, this.a); break;
        case "STX": this.write(addr, this.x); break;
        case "STY": this.write(addr, this.y); break;
        case "SAX": this.write(addr, this.a & this.x); break;
        case "TAX": this.x = this.a; this.setZN(this.x); break;
        case "TAY": this.y = this.a; this.setZN(this.y); break;
        case "TXA": this.a = this.x; this.setZN(this.a); break;
        case "TYA": this.a = this.y; this.setZN(this.a); break;
        case "TSX": this.x = this.sp; this.setZN(this.x); break;
        case "TXS": this.sp = this.x; break;
        case "PHA": this.push(this.a); break;
        case "PHP": this.push(this.p | FLAG_B | FLAG_U); break;
        case "PLA": this.a = this.pull(); this.setZN(this.a); break;
        case "PLP": this.p = (this.pull() & ~FLAG_B) | FLAG_U; break;
        case "AND": this.a &= this.read(addr); this.setZN(this.a); break;
        case "ORA": this.a |= this.read(addr); this.setZN(this.a); break;
        case "EOR": this.a ^= this.read(addr); this.setZN(this.a); break;
        case "BIT": { const m = this.read(addr); this.flag(FLAG_Z, !(this.a & m)); this.p = (this.p & 0x3f) | (m & 0xc0); break; }
        case "ADC": adc(this.read(addr)); break;
        case "SBC": adc(this.read(addr) ^ 0xff); break;
        case "CMP": cmp(this.a, this.read(addr)); break;
        case "CPX": cmp(this.x, this.read(addr)); break;
        case "CPY": cmp(this.y, this.read(addr)); break;
        case "INC": rmw((v) => (v + 1) & 0xff); break;
        case "DEC": rmw((v) => (v - 1) & 0xff); break;
        case "INX": this.x = (this.x + 1) & 0xff; this.setZN(this.x); break;
        case "INY": this.y = (this.y + 1) & 0xff; this.setZN(this.y); break;
        case "DEX": this.x = (this.x - 1) & 0xff; this.setZN(this.x); break;
        case "DEY": this.y = (this.y - 1) & 0xff; this.setZN(this.y); break;
        case "ASL": rmw(asl); break;
        case "LSR": rmw(lsr); break;
        case "ROL": rmw(rol); break;
        case "ROR": rmw(ror); break;
        case "SLO": { const r = rmw(asl); this.a |= r; this.setZN(this.a); break; }
        case "RLA": { const r = rmw(rol); this.a &= r; this.setZN(this.a); break; }
        case "SRE": { const r = rmw(lsr); this.a ^= r; this.setZN(this.a); break; }
        case "RRA": { const r = rmw(ror); adc(r); break; }
        case "DCP": { const r = (this.read(addr) - 1) & 0xff; this.write(addr, r); cmp(this.a, r); break; }
        case "ISB": { const r = (this.read(addr) + 1) & 0xff; this.write(addr, r); adc(r ^ 0xff); break; }
        case "ANC": this.a &= this.read(addr); this.setZN(this.a); this.flag(FLAG_C, this.a & 0x80); break;
        case "ALR": this.a &= this.read(addr); this.a = lsr(this.a); this.setZN(this.a); break;
        case "ARR": { this.a &= this.read(addr); this.a = ((this.a >> 1) | ((this.p & FLAG_C) << 7)) & 0xff; this.setZN(this.a);
          this.flag(FLAG_C, this.a & 0x40); this.flag(FLAG_V, ((this.a >> 6) ^ (this.a >> 5)) & 1); break; }
        case "AXS": { const r = (this.a & this.x) - this.read(addr); this.flag(FLAG_C, r >= 0); this.x = r & 0xff; this.setZN(this.x); break; }
        case "LAS": this.a = this.x = this.sp = this.read(addr) & this.sp; this.setZN(this.a); break;
        case "XAA": this.a = this.x & this.read(addr); this.setZN(this.a); break;
        case "AHX": case "TAS": case "SHY": case "SHX": break;   // unstable opcodes (unused in practice)
        case "JMP": this.pc = addr; break;
        case "JSR": { const r = (this.pc - 1) & 0xffff; this.push(r >> 8); this.push(r & 0xff); this.pc = addr; break; }
        case "RTS": this.pc = ((this.pull() | (this.pull() << 8)) + 1) & 0xffff; break;
        case "RTI": this.p = (this.pull() & ~FLAG_B) | FLAG_U; this.pc = this.pull() | (this.pull() << 8); break;
        case "BRK": { const r = (this.pc + 1) & 0xffff; this.push(r >> 8); this.push(r & 0xff); this.push(this.p | FLAG_B | FLAG_U); this.p |= FLAG_I; this.pc = this.read16(0xfffe); break; }
        case "BPL": branch(!(this.p & FLAG_N)); break;
        case "BMI": branch(this.p & FLAG_N); break;
        case "BVC": branch(!(this.p & FLAG_V)); break;
        case "BVS": branch(this.p & FLAG_V); break;
        case "BCC": branch(!(this.p & FLAG_C)); break;
        case "BCS": branch(this.p & FLAG_C); break;
        case "BNE": branch(!(this.p & FLAG_Z)); break;
        case "BEQ": branch(this.p & FLAG_Z); break;
        case "CLC": this.p &= ~FLAG_C; break;
        case "SEC": this.p |= FLAG_C; break;
        case "CLI": this.p &= ~FLAG_I; break;
        case "SEI": this.p |= FLAG_I; break;
        case "CLD": this.p &= ~FLAG_D; break;
        case "SED": this.p |= FLAG_D; break;
        case "CLV": this.p &= ~FLAG_V; break;
        case "NOP": if (mode !== "imp" && mode !== "imm") this.read(addr); break;
        case "KIL": this.pc = (this.pc - 1) & 0xffff; break;   // halt
      }
      this.cycles += cyc;
      return cyc;
    }

    // ---------------------------------------------------------- PPU registers
    ppuRead(reg) {
      switch (reg) {
        case 2: {
          const r = (this.status & 0xe0) | (this.openBus & 0x1f);
          this.status &= ~0x80; this.w = 0; this.openBus = r; return r;
        }
        case 4: return this.oam[this.oamAddr];
        case 7: {
          let r;
          const a = this.v & 0x3fff;
          if (a >= 0x3f00) { r = this.pal[this.palIndex(a)] & ((this.mask & 1) ? 0x30 : 0x3f); this.readBuf = this.vramRead(a - 0x1000); }
          else { r = this.readBuf; this.readBuf = this.vramRead(a); }
          this.v = (this.v + ((this.ctrl & 4) ? 32 : 1)) & 0x7fff;
          this.openBus = r; return r;
        }
        default: return this.openBus;
      }
    }

    ppuWrite(reg, v) {
      this.openBus = v;
      switch (reg) {
        case 0: {
          const wasNmi = this.ctrl & 0x80;
          this.ctrl = v; this.t = (this.t & 0xf3ff) | ((v & 3) << 10);
          if (!wasNmi && (v & 0x80) && (this.status & 0x80)) this.nmiPending = true;
          break;
        }
        case 1: this.mask = v; break;
        case 3: this.oamAddr = v; break;
        case 4: this.oam[this.oamAddr] = v; this.oamAddr = (this.oamAddr + 1) & 0xff; break;
        case 5:
          if (!this.w) { this.t = (this.t & 0xffe0) | (v >> 3); this.fx = v & 7; }
          else { this.t = (this.t & 0x8c1f) | ((v & 7) << 12) | ((v & 0xf8) << 2); }
          this.w ^= 1; break;
        case 6:
          if (!this.w) { this.t = (this.t & 0x00ff) | ((v & 0x3f) << 8); }
          else { this.t = (this.t & 0xff00) | v; this.v = this.t; }
          this.w ^= 1; break;
        case 7: {
          const a = this.v & 0x3fff;
          this.vramWrite(a, v);
          this.v = (this.v + ((this.ctrl & 4) ? 32 : 1)) & 0x7fff;
          break;
        }
      }
    }

    palIndex(a) { let i = a & 0x1f; if ((i & 0x13) === 0x10) i &= 0x0f; return i; }
    ntIndex(a) {
      const n = (a >> 10) & 3, off = a & 0x3ff;
      if (this.cart.vertical) return ((n & 1) << 10) | off;
      return ((n >> 1) << 10) | off;
    }
    vramRead(a) {
      a &= 0x3fff;
      if (a < 0x2000) return this.cart.chr[a];
      if (a < 0x3f00) return this.vram[this.ntIndex(a)];
      return this.pal[this.palIndex(a)];
    }
    vramWrite(a, v) {
      a &= 0x3fff;
      if (a < 0x2000) { if (this.cart.chrRam) this.cart.chr[a] = v; return; }
      if (a < 0x3f00) { this.vram[this.ntIndex(a)] = v; return; }
      this.pal[this.palIndex(a)] = v & 0x3f;
    }

    // ---------------------------------------------------------- PPU timing (one dot)
    ppuTick() {
      const rendering = (this.mask & 0x18) !== 0;
      if (this.scanline < 240) {
        if (this.dot === 256) { if (rendering) this.renderLine(this.scanline); else this.blankLine(this.scanline); }
        if (rendering && this.dot === 256) this.incY();
        if (rendering && this.dot === 257) this.v = (this.v & ~0x041f) | (this.t & 0x041f);
      } else if (this.scanline === 241 && this.dot === 1) {
        this.status |= 0x80;
        if (this.ctrl & 0x80) this.nmiPending = true;
      } else if (this.scanline === 261) {
        if (this.dot === 1) this.status &= ~0xe0;
        if (rendering && this.dot === 257) this.v = (this.v & ~0x041f) | (this.t & 0x041f);
        if (rendering && this.dot >= 280 && this.dot <= 304) this.v = (this.v & ~0x7be0) | (this.t & 0x7be0);
      }
      this.dot++;
      if (this.scanline === 261 && this.dot === 340 && this.oddFrame && rendering) this.dot = 341;   // odd frames are one dot shorter
      if (this.dot > 340) {
        this.dot = 0; this.scanline++;
        if (this.scanline > 261) { this.scanline = 0; this.frameCount++; this.oddFrame = !this.oddFrame; this.frameDone = true; }
      }
    }

    incY() {
      if ((this.v & 0x7000) !== 0x7000) { this.v += 0x1000; return; }
      this.v &= ~0x7000;
      let y = (this.v & 0x03e0) >> 5;
      if (y === 29) { y = 0; this.v ^= 0x0800; } else if (y === 31) y = 0; else y++;
      this.v = (this.v & ~0x03e0) | (y << 5);
    }

    blankLine(y) {
      const bg = this.pal[0] & 0x3f;
      for (let x = 0; x < 256; x++) { this.indexBuffer[y * 256 + x] = bg; this.frameBuffer[y * 256 + x] = PALETTE_ABGR[bg]; }
    }

    renderLine(y) {
      const showBg = this.mask & 0x08, showSpr = this.mask & 0x10, bgLeft = this.mask & 0x02, sprLeft = this.mask & 0x04;
      const bgPix = new Uint8Array(256);           // 0..15 (0 = transparent)
      // ---- background
      if (showBg) {
        let v = this.v, fx = this.fx;
        const fineY = (v >> 12) & 7, bgTable = (this.ctrl & 0x10) ? 0x1000 : 0;
        let x = 0;
        for (let tile = 0; tile < 33 && x < 256 + fx; tile++) {
          const ntAddr = 0x2000 | (v & 0x0fff);
          const tileIdx = this.vramRead(ntAddr);
          const atAddr = 0x23c0 | (v & 0x0c00) | ((v >> 4) & 0x38) | ((v >> 2) & 0x07);
          const at = this.vramRead(atAddr);
          const shift = ((v >> 4) & 4) | (v & 2);
          const palHi = ((at >> shift) & 3) << 2;
          const lo = this.vramRead(bgTable + tileIdx * 16 + fineY), hi = this.vramRead(bgTable + tileIdx * 16 + fineY + 8);
          for (let b = 7; b >= 0; b--, x++) {
            const sx = x - fx;
            if (sx < 0 || sx >= 256) continue;
            const c = ((lo >> b) & 1) | (((hi >> b) & 1) << 1);
            bgPix[sx] = c ? (palHi | c) : 0;
          }
          // coarse X++
          if ((v & 0x1f) === 31) { v &= ~0x1f; v ^= 0x0400; } else v++;
        }
        if (!bgLeft) for (let i = 0; i < 8; i++) bgPix[i] = 0;
      }
      // ---- sprites
      const sprPix = new Uint8Array(256), sprPri = new Uint8Array(256), sprZero = new Uint8Array(256);
      if (showSpr) {
        const h = (this.ctrl & 0x20) ? 16 : 8;
        let count = 0;
        for (let i = 0; i < 64; i++) {
          const sy = this.oam[i * 4] + 1;
          const row = y - sy;
          if (row < 0 || row >= h) continue;
          if (count === 8) { this.status |= 0x20; break; }
          count++;
          const tile = this.oam[i * 4 + 1], attr = this.oam[i * 4 + 2], sx = this.oam[i * 4 + 3];
          let r = (attr & 0x80) ? h - 1 - row : row;
          let addr;
          if (h === 16) {
            const table = (tile & 1) ? 0x1000 : 0;
            let t = tile & 0xfe;
            if (r >= 8) { t++; r -= 8; }
            addr = table + t * 16 + r;
          } else {
            addr = ((this.ctrl & 0x08) ? 0x1000 : 0) + tile * 16 + r;
          }
          const lo = this.vramRead(addr), hi = this.vramRead(addr + 8);
          for (let b = 0; b < 8; b++) {
            const px = sx + b;
            if (px > 255) break;
            const bit = (attr & 0x40) ? b : 7 - b;
            const c = ((lo >> bit) & 1) | (((hi >> bit) & 1) << 1);
            if (!c || sprPix[px]) continue;           // earlier sprites win
            if (!sprLeft && px < 8) continue;
            sprPix[px] = 16 | ((attr & 3) << 2) | c;
            sprPri[px] = attr & 0x20;
            if (i === 0) sprZero[px] = 1;
          }
        }
      }
      // ---- composite
      const base = y * 256;
      for (let x = 0; x < 256; x++) {
        const b = bgPix[x], s = sprPix[x];
        if (sprZero[x] && b && s && x !== 255) this.status |= 0x40;
        let idx;
        if (s && (!b || !sprPri[x])) idx = s; else if (b) idx = b; else idx = 0;
        const c = this.pal[this.palIndex(0x3f00 | idx)] & ((this.mask & 1) ? 0x30 : 0x3f);
        this.indexBuffer[base + x] = c;
        this.frameBuffer[base + x] = PALETTE_ABGR[c];
      }
    }

    // ---------------------------------------------------------- APU
    quarterFrame() { this.p1.clockEnvelope(); this.p2.clockEnvelope(); this.noise.clockEnvelope(); this.tri.clockQuarter(); }
    halfFrame() { this.p1.clockHalf(); this.p2.clockHalf(); this.tri.clockHalf(); this.noise.clockHalf(); }

    apuTick() {
      this.tri.clockTimer();
      this.apuOdd = !this.apuOdd;
      if (this.apuOdd) { this.p1.clockTimer(); this.p2.clockTimer(); this.noise.clockTimer(); }
      this.fcCycle++;
      const c = this.fcCycle;
      if (this.fcMode === 0) {
        if (c === 7457 || c === 22371) this.quarterFrame();
        else if (c === 14913) { this.quarterFrame(); this.halfFrame(); }
        else if (c === 29829) { this.quarterFrame(); this.halfFrame(); this.fcCycle = 0; }
      } else {
        if (c === 7457 || c === 22371) this.quarterFrame();
        else if (c === 14913) { this.quarterFrame(); this.halfFrame(); }
        else if (c === 37281) { this.quarterFrame(); this.halfFrame(); this.fcCycle = 0; }
      }
      // resampling (1.789773 MHz -> sampleRate)
      this.sampleAcc += this.sampleRate;
      if (this.sampleAcc >= 1789773) {
        this.sampleAcc -= 1789773;
        const pul = this.p1.output() + this.p2.output();
        const pOut = pul ? 95.88 / (8128 / pul + 100) : 0;
        const tnd = this.tri.output() / 8227 + this.noise.output() / 12241;
        const tOut = tnd ? 159.79 / (1 / tnd + 100) : 0;
        let s = pOut + tOut;
        // simple high/low-pass filter (DC removal)
        const hp = s - this.hpPrev + 0.996 * this.hp; this.hpPrev = s; this.hp = hp;
        this.samples.push(hp);
      }
    }

    // ---------------------------------------------------------- 実行
    frame() {
      if (!this.cart) return;
      this.frameDone = false;
      let guard = 0;
      while (!this.frameDone && guard++ < 200000) {
        const c = this.step();
        for (let i = 0; i < c * 3; i++) this.ppuTick();
        for (let i = 0; i < c; i++) this.apuTick();
      }
      if (this.audioOut && this.samples.length) { this.audioOut(Float32Array.from(this.samples)); }
      this.samples.length = 0;
    }

    setButton(player, btn, down) {
      if (down) this.pad[player] |= btn; else this.pad[player] &= ~btn;
    }
  }

  NES.BTN = { A: 1, B: 2, SELECT: 4, START: 8, UP: 16, DOWN: 32, LEFT: 64, RIGHT: 128 };
  NES.PALETTE_RGB = PALETTE_RGB;
  NES.OPS = OPS;

  if (typeof module !== "undefined" && module.exports) module.exports = NES;
  else root.NES = NES;
})(typeof self !== "undefined" ? self : this);
