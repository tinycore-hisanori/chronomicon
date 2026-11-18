---
inclusion: fileMatch
fileMatchPattern: "web/**"
---
# Browser player (tinynes)

- Single dependency-free file `nes.js` (works in browser and Node), MIT licence, NROM only.
- API: `new NES({sampleRate})`, `load(Uint8Array)`, `frame()`, `frameBuffer` (Uint32Array 256x240,
  0xAABBGGRR for ImageData), `indexBuffer` (palette indices for tests), `pad[0]` bitmask
  (A=1,B=2,SELECT=4,START=8,UP=16,DOWN=32,LEFT=64,RIGHT=128), `audioOut(Float32Array)` per frame.
- Verified: nestest CPU log 8,991/8,991 lines match (registers, flags, cycles); frames match nes-py
  pixel-for-pixel on the sample game.
- Limits: scanline-granular rendering (no mid-line raster effects), no DMC audio, mapper 0 only.
- UI rules: drag & drop a .nes, `?rom=` query to autoload, keyboard (arrows, Z=B, X/Space=A,
  Enter=START, Shift=SELECT) + standard gamepad. ROMs never leave the browser.
- Never label it with console trademarks; call it "8-bit player" / "NES-format ROM player".
