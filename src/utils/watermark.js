const sharp = require('sharp');
const axios = require('axios');
const fs    = require('fs');
const path  = require('path');
const { AttachmentBuilder } = require('discord.js');

const FONT_PATHS = [
  path.join(__dirname, 'fonts', 'DejaVuSans-Bold.ttf'),
  path.join(__dirname, 'DejaVuSans-Bold.ttf'),
  '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
  '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
];
let _fontFaceDecl = '';
for (const fp of FONT_PATHS) {
  try {
    const b64 = fs.readFileSync(fp).toString('base64');
    _fontFaceDecl = `<defs><style>@font-face{font-family:'BrawlFont';src:url('data:font/ttf;base64,${b64}') format('truetype');font-weight:bold;}</style></defs>`;
    break;
  } catch { /* try next */ }
}
/**
 * Fetch an image from a URL, watermark it, and return a Discord AttachmentBuilder.
 * @param {string} url
 * @param {boolean} blur
 * @returns {Promise<AttachmentBuilder|null>}
 */
async function fetchAndWatermark(url, blur = false) {
  const response = await axios.get(url, {
  responseType: 'arraybuffer',
  timeout: 10000,
  headers: { 'User-Agent': 'Mozilla/5.0 (compatible; BrawlCarryBot/1.0)' },
});
  const rawBuffer = Buffer.from(response.data);
  const marked = await watermarkImage(rawBuffer, 'Brawl Carry Vouches', blur);
  return new AttachmentBuilder(marked, { name: 'proof.jpg' });
}
/**
 * Apply a tiled diagonal watermark to an image buffer.
 * @param {Buffer} imageBuffer
 * @param {string} text
 * @param {boolean} blur
 * @returns {Promise<Buffer>}
 */
async function watermarkImage(imageBuffer, text = 'BrawlCarry™', blur = false) {
  let pipeline = sharp(imageBuffer);
  const meta   = await pipeline.metadata();
  const w      = meta.width  ?? 800;
  const h      = meta.height ?? 600;

  if (blur) pipeline = pipeline.blur(6);

  // 2-line watermark: "BrawlCarry™" + "discord.gg/brawlcarry"
  // fontSize ~1.5× larger than old design (w/18 → w/14)
  const fontSize = Math.max(14, Math.floor(w / 31));
  const lineGap = Math.floor(fontSize * 0.30);
  const opacity    = 0.45;
  const subSize = Math.floor(fontSize * 0.68);

  // Render line 1
const svgW = Math.ceil(fontSize * 14);
const svgH = fontSize + lineGap + subSize + Math.ceil(fontSize * 0.2);
const fontFamily = _fontFaceDecl ? 'BrawlFont' : 'DejaVu Sans, Liberation Sans, FreeSans, sans-serif';
const diagColor = _fontFaceDecl ? 'rgba(0,220,0,0.6)' : 'rgba(255,0,0,0.6)';
const svgBuf = Buffer.from(
  `<svg xmlns="http://www.w3.org/2000/svg" width="${svgW}" height="${svgH}">
    ${_fontFaceDecl}
    <rect width="${svgW}" height="${svgH}" fill="${diagColor}"/>
    <text x="${svgW / 2}" y="${fontSize}" font-size="${fontSize}" font-weight="bold"
      font-family="${fontFamily}"
      fill="white" text-anchor="middle">BrawlCarry</text>
    <text x="${svgW / 2}" y="${fontSize + lineGap + subSize}" font-size="${subSize}" font-weight="bold"
      font-family="${fontFamily}"
      fill="white" text-anchor="middle">discord.gg/brawlcarry</text>
  </svg>`
);
const stampSvg = await sharp(svgBuf).png().toBuffer();
const m1 = await sharp(stampSvg).metadata();

const stampRaw = stampSvg;
const stampW = m1.width;
const stampH = m1.height;

// Apply 45% opacity directly on raw alpha bytes
const { data, info } = await sharp(stampRaw).ensureAlpha().raw()
  .toBuffer({ resolveWithObject: true });
for (let i = 3; i < data.length; i += 4) data[i] = Math.round(data[i] * 0.45);
const stamp = await sharp(data, {
  raw: { width: info.width, height: info.height, channels: 4 },
}).png().toBuffer();

// Rotate stamp −30°
const rotated = await sharp(stamp)
  .rotate(-30, { background: { r: 0, g: 0, b: 0, alpha: 0 } })
  .png().toBuffer();

const rMeta = await sharp(rotated).metadata();
const rW    = rMeta.width;
const rH    = rMeta.height;

  const composites = [];
const stepX = Math.ceil(rW * 0.85);
const stepY = Math.ceil(rH * 0.85);

// Canvas esteso con padding = rW/rH su ogni lato, poi si ritaglia
const padX = rW;
const padY = rH;
const canvasW = w + padX * 2;
const canvasH = h + padY * 2;

for (let row = -2; row * stepY < canvasH + rH; row++) {
  for (let col = -2; col * stepX < canvasW + rW; col++) {
    const offsetX = (row % 2 !== 0) ? Math.floor(stepX / 2) : 0;
    const top  = Math.round(row * stepY);
    const left = Math.round(col * stepX + offsetX);
    if (left + rW < 0 || left > canvasW || top + rH < 0 || top > canvasH) continue;
    composites.push({ input: rotated, top, left });
  }
}

const overlayPng = await sharp({
  create: { width: canvasW, height: canvasH, channels: 4,
            background: { r: 0, g: 0, b: 0, alpha: 0 } },
})
.composite(composites)
.png().toBuffer();

// Ritaglia al canvas originale w×h
const overlayPngCropped = await sharp(overlayPng)
  .extract({ left: padX, top: padY, width: w, height: h })
  .png().toBuffer();

return pipeline
  .composite([{ input: overlayPngCropped, blend: 'over' }])
  .jpeg({ quality: 92 })
  .toBuffer();
}


/**
 * DEBUG: returns a Discord AttachmentBuilder with a diagnostic image.
 * Call it with: const dbg = await require('./watermark').debugWatermarkDiag(); 
 * then send it in any channel.
 */
async function debugWatermarkDiag() {
  // ── 1. Check every font path ──────────────────────────────────────────────
  const checks = FONT_PATHS.map(fp => {
    let status = 'MISSING';
    let bytes  = 0;
    try { bytes = fs.statSync(fp).size; status = 'OK'; } catch {}
    return { fp, status, bytes };
  });

  const fontLoaded  = _fontFaceDecl !== '';
  const fontFamily  = fontLoaded ? 'BrawlFont (embedded)' : 'system fallback (DejaVu/Liberation)';
  const b64Len      = _fontFaceDecl.length;

  // ── 2. Try rendering the exact same SVG the watermark uses ────────────────
  const fontSize = 28;
  const lineGap  = Math.floor(fontSize * 0.30);
  const subSize  = Math.floor(fontSize * 0.68);
  const svgW     = 560;
  const svgH     = 400;
  const ff       = fontLoaded ? 'BrawlFont' : 'DejaVu Sans, Liberation Sans, FreeSans, sans-serif';

  let renderOK = true;
  let renderBuf;
  try {
    renderBuf = await sharp(Buffer.from(
      `<svg xmlns="http://www.w3.org/2000/svg" width="${svgW}" height="${svgH}">
        ${_fontFaceDecl}
        <rect width="${svgW}" height="${svgH}" fill="#1a1a2e"/>
        <!-- ── section 1: font path results ── -->
        ${checks.map((c, i) => {
          const colour = c.status === 'OK' ? '#00ff88' : '#ff4444';
          const label  = `${c.status === 'OK' ? '✓' : '✗'} ${c.fp.split('/').pop()} (${c.status}${c.bytes ? ' '+c.bytes+'B' : ''})`;
          return `<text x="10" y="${30 + i * 22}" font-size="12" font-family="DejaVu Sans,Liberation Sans,sans-serif" fill="${colour}">${label}</text>`;
        }).join('\n')}
        <!-- ── section 2: _fontFaceDecl state ── -->
        <text x="10" y="${30 + checks.length * 22 + 20}" font-size="13" font-family="DejaVu Sans,Liberation Sans,sans-serif" fill="${fontLoaded ? '#00ff88' : '#ff4444'}">_fontFaceDecl: ${fontLoaded ? 'POPULATED ('+b64Len+' chars)' : 'EMPTY — no font file found'}</text>
        <text x="10" y="${30 + checks.length * 22 + 42}" font-size="13" font-family="DejaVu Sans,Liberation Sans,sans-serif" fill="#ffffff">fontFamily used: ${fontFamily}</text>
        <!-- ── section 3: actual watermark text rendered with the real font ── -->
        <text x="10" y="${30 + checks.length * 22 + 80}" font-size="11" font-family="DejaVu Sans,Liberation Sans,sans-serif" fill="#aaaaaa">--- render test (font: ${ff}) ---</text>
        <text x="${svgW/2}" y="${30 + checks.length * 22 + 110}" font-size="${fontSize}" font-weight="bold" font-family="${ff}" fill="white" text-anchor="middle">BrawlCarry</text>
        <text x="${svgW/2}" y="${30 + checks.length * 22 + 110 + lineGap + subSize}" font-size="${subSize}" font-weight="bold" font-family="${ff}" fill="white" text-anchor="middle">discord.gg/brawlcarry</text>
        <!-- ── section 4: sharp/librsvg version ── -->
        <text x="10" y="${svgH - 20}" font-size="11" font-family="DejaVu Sans,Liberation Sans,sans-serif" fill="#888888">sharp ${require('sharp').versions.sharp}  |  librsvg ${require('sharp').versions.rsvg}  |  node ${process.version}</text>
      </svg>`
    )).png().toBuffer();
  } catch (e) {
    renderOK = false;
    // fallback: plain colour block
    renderBuf = await sharp({
      create: { width: svgW, height: svgH, channels: 3, background: { r: 180, g: 0, b: 0 } }
    }).png().toBuffer();
  }

  return new AttachmentBuilder(renderBuf, { name: 'watermark_diag.png' });
}

module.exports = { fetchAndWatermark, watermarkImage, debugWatermarkDiag };

