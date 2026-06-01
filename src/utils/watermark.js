const sharp = require('sharp');
const axios = require('axios');
const fs    = require('fs');
const path  = require('path');
const { AttachmentBuilder } = require('discord.js');

const opentype = require('opentype.js');

const FONT_PATHS = [
  path.join(__dirname, 'fonts', 'DejaVuSans-Bold.ttf'),
  path.join(__dirname, 'DejaVuSans-Bold.ttf'),
  '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
  '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
];
let _font = null;
for (const fp of FONT_PATHS) {
  try {
    _font = opentype.loadSync(fp);
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
  const fontSize = Math.max(11, Math.floor(w / 44));
  const lineGap = Math.floor(fontSize * 0.30);
  const opacity    = 0.28;
  const subSize = Math.floor(fontSize * 0.68);

  // Render line 1
// ── Stamp PNG via opentype paths — nessun SVG text, nessun font di sistema ──
let stampSvg;
if (_font) {
  // Prima passata: misura le bounding box per calcolare le dimensioni del canvas
  const probe1 = _font.getPath('BrawlCarry',             0, fontSize,                    fontSize);
  const probe2 = _font.getPath('discord.gg/brawlcarry',  0, fontSize + lineGap + subSize, subSize);
  const bb1 = probe1.getBoundingBox();
  const bb2 = probe2.getBoundingBox();

  const svgW = Math.ceil(Math.max(bb1.x2 - bb1.x1, bb2.x2 - bb2.x1) * 1.15);
  const svgH = Math.ceil(fontSize + lineGap + subSize + fontSize * 0.25);

  // Seconda passata: posiziona centrato
  const cx1 = (svgW - (bb1.x2 - bb1.x1)) / 2 - bb1.x1;
  const cx2 = (svgW - (bb2.x2 - bb2.x1)) / 2 - bb2.x1;
  const p1 = _font.getPath('BrawlCarry',             cx1, fontSize,                    fontSize);
  const p2 = _font.getPath('discord.gg/brawlcarry',  cx2, fontSize + lineGap + subSize, subSize);

  const svgBuf = Buffer.from(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${svgW}" height="${svgH}">
      <path d="${p1.toPathData(2)}" fill="white"/>
      <path d="${p2.toPathData(2)}" fill="white"/>
    </svg>`
  );
  stampSvg = await sharp(svgBuf).png().toBuffer();
} else {
  // Fallback geometrico (non dovrebbe mai accadere: il font è nel repo)
  const svgW = Math.ceil(fontSize * 14);
  const svgH = fontSize + lineGap + subSize + Math.ceil(fontSize * 0.2);
  const svgBuf = Buffer.from(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${svgW}" height="${svgH}">
      <rect x="4" y="2"  width="${svgW - 8}"        height="${fontSize - 4}" fill="white" rx="3"/>
      <rect x="4" y="${fontSize + lineGap + 2}" width="${(svgW - 8) * 0.82}" height="${subSize - 4}" fill="white" rx="2"/>
    </svg>`
  );
  stampSvg = await sharp(svgBuf).png().toBuffer();
}
const m1 = await sharp(stampSvg).metadata();

const stampRaw = stampSvg;
const stampW = m1.width;
const stampH = m1.height;

// Apply 45% opacity directly on raw alpha bytes
const { data, info } = await sharp(stampRaw).ensureAlpha().raw()
  .toBuffer({ resolveWithObject: true });
for (let i = 3; i < data.length; i += 4) data[i] = Math.round(data[i] * 0.28);
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
const stepX = Math.ceil(rW * 1.55);
const stepY = Math.ceil(rH * 1.55);

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


module.exports = { fetchAndWatermark, watermarkImage };

