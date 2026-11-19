"use strict";
// Persistent tinynes driver for the ROM tests.
// Protocol: one JSON object per line on stdin, one JSON object per line on stdout.
// See .kiro/specs/rom-builder/design.md ("Test harness"). Binary data is base64.
const path = require("path");
const readline = require("readline");
const NES = require(path.resolve(__dirname, "..", "..", "web", "nes.js"));

let rom = null; // Buffer of the cached ROM

function b64(arr) {
  return Buffer.from(arr.buffer, arr.byteOffset, arr.byteLength).toString("base64");
}

function checkInt(v, what, lo, hi) {
  if (!Number.isInteger(v) || v < lo || v > hi) throw new Error(`${what} must be an integer in ${lo}..${hi}, got ${JSON.stringify(v)}`);
  return v;
}

function applyHold(nes, mask) {
  for (let bit = 0; bit < 8; bit++) {
    const b = 1 << bit;
    nes.setButton(0, b, (mask & b) !== 0);
  }
}

function doLoad(req) {
  if (typeof req.rom !== "string") throw new Error("load: 'rom' must be a base64 string");
  const buf = Buffer.from(req.rom, "base64");
  // Validate now so that a bad ROM fails at load, not at the first run.
  new NES().load(new Uint8Array(buf));
  rom = buf;
  return {};
}

function doRun(req) {
  if (!rom) throw new Error("run: no ROM loaded");
  if (!Array.isArray(req.steps)) throw new Error("run: 'steps' must be an array");
  const trace = req.trace || {};
  const nes = new NES();
  nes.load(new Uint8Array(rom));

  let frameIdx = 0;
  let ppuCounts = null;
  let ioLog = null;
  let apuLog = null;
  if (trace.ppu_data || trace.io || trace.apu) {
    const origWrite = nes.write.bind(nes);
    nes.write = function (addr, v) {
      const a = addr & 0xffff;
      const val = v & 0xff;
      if (a >= 0x2000 && a < 0x4000) {
        const reg = a & 7;
        if (reg === 7 && ppuCounts) ppuCounts[frameIdx] = (ppuCounts[frameIdx] || 0) + 1;
        if (ioLog) ioLog.push([frameIdx, 0x2000 + reg, val]);
      } else if (a >= 0x4000 && a <= 0x4017) {
        if (ioLog) ioLog.push([frameIdx, a, val]);
        if (apuLog) apuLog.push([frameIdx, a, val]);
      }
      return origWrite(addr, v);
    };
  }

  const results = [];
  for (const step of req.steps) {
    if (step === null || typeof step !== "object") throw new Error("each step must be an object");
    const frames = step.frames === undefined ? 0 : checkInt(step.frames, "frames", 0, 100000);

    for (const w of step.writes || []) {
      const data = Buffer.from(String(w.data), "base64");
      const addr = checkInt(w.addr, "write addr", 0, 0x7ff);
      if (addr + data.length > 0x800) throw new Error(`write at ${addr} of ${data.length} bytes exceeds CPU RAM`);
      nes.ram.set(data, addr);
    }

    const hold = step.hold === undefined ? 0 : step.hold;
    if (!Number.isInteger(hold) && !Array.isArray(hold)) throw new Error("hold must be an integer or a list");

    ppuCounts = trace.ppu_data ? new Array(frames).fill(0) : null;
    ioLog = trace.io ? [] : null;
    apuLog = trace.apu ? [] : null;

    for (let f = 0; f < frames; f++) {
      frameIdx = f;
      const mask = Array.isArray(hold) ? (hold[f] === undefined ? 0 : checkInt(hold[f], "hold mask", 0, 255)) : checkInt(hold, "hold mask", 0, 255);
      applyHold(nes, mask);
      nes.frame();
    }

    const out = {};
    const reads = {};
    for (const r of step.reads || []) {
      const addr = checkInt(r.addr, "read addr", 0, 0x7ff);
      const len = checkInt(r.len, "read len", 0, 0x800 - addr);
      reads[String(r.name)] = b64(nes.ram.subarray(addr, addr + len));
    }
    out.reads = reads;

    const snap = {};
    for (const s of step.snap || []) {
      switch (s) {
        case "index_buffer": snap.index_buffer = b64(nes.indexBuffer); break;
        case "oam": snap.oam = b64(nes.oam); break;
        case "vram": snap.vram = b64(nes.vram); break;
        case "pal": snap.pal = b64(nes.pal); break;
        default: throw new Error(`unknown snapshot '${s}'`);
      }
    }
    out.snap = snap;
    if (ppuCounts) out.ppu_data_per_frame = ppuCounts;
    if (ioLog) out.io = ioLog;
    if (apuLog) out.apu = apuLog;
    results.push(out);
  }
  return { steps: results };
}

function handle(line) {
  let id = null;
  try {
    const req = JSON.parse(line);
    if (req === null || typeof req !== "object" || Array.isArray(req)) throw new Error("request must be a JSON object");
    if (req.id !== undefined) id = req.id;
    let body;
    if (req.op === "load") body = doLoad(req);
    else if (req.op === "run") body = doRun(req);
    else throw new Error(`unknown op ${JSON.stringify(req.op)}`);
    return JSON.stringify({ id, ok: true, ...body });
  } catch (e) {
    return JSON.stringify({ id, ok: false, error: String(e && e.message ? e.message : e) });
  }
}

const rl = readline.createInterface({ input: process.stdin, terminal: false });
rl.on("line", (line) => {
  if (line.trim() === "") return;
  process.stdout.write(handle(line) + "\n");
});
