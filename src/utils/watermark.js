const sharp = require('sharp');
const axios = require('axios');
const { AttachmentBuilder } = require('discord.js');

/**
 * Fetch an image from a URL, watermark it, and return a Discord AttachmentBuilder.
 * @param {string} url
 * @param {boolean} blur
 * @returns {Promise<AttachmentBuilder|null>}
 */
async function fetchAndWatermark(url, blur = false) {
  const response = await axios.get(url, { responseType: 'arraybuffer', timeout: 10000 });
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
  const fontSize   = Math.max(18, Math.floor(w / 22));
  const lineHeight = Math.floor(fontSize * 1.3);
  const opacity    = 0.45;
  const subSize    = Math.floor(fontSize * 0.78);

  // Tile spacing calculated in rotated space to prevent overlap at -30° angle
  const cos30  = Math.cos(30 * Math.PI / 180);
  const tileW = Math.ceil(21 * fontSize * 0.58);
  const tileH = lineHeight * 2;
  const stepX  = Math.ceil((tileW / cos30) * 1.13);
  const stepY  = Math.ceil((tileH / cos30) * 1.13);

  // Render line 1
const line1Buf = await sharp({
  text: {
    text: '<span foreground="#ffffff">BrawlCarry™</span>',
    font: `DejaVu Sans Bold ${fontSize}`,
    dpi:  72,
    rgba: true,
  },
}).png().toBuffer();

// Render line 2
const line2Buf = await sharp({
  text: {
    text: '<span foreground="#ffffff">discord.gg/brawlcarry</span>',
    font: `DejaVu Sans Bold ${subSize}`,
    dpi:  72,
    rgba: true,
  },
}).png().toBuffer();

const m1 = await sharp(line1Buf).metadata();
const m2 = await sharp(line2Buf).metadata();

// Assemble stamp
const gap    = Math.max(0, lineHeight - m1.height);
const stampW = Math.max(m1.width, m2.width);
const stampH = m1.height + gap + m2.height;

const stampRaw = await sharp({
  create: { width: stampW, height: stampH, channels: 4,
            background: { r: 0, g: 0, b: 0, alpha: 0 } },
})
.composite([
  { input: line1Buf, top: 0,               left: Math.floor((stampW - m1.width) / 2) },
  { input: line2Buf, top: m1.height + gap, left: Math.floor((stampW - m2.width) / 2) },
])
.png().toBuffer();

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
for (let row = -2; row * stepY < h + rH; row++) {
  for (let col = -2; col * stepX < w + rW; col++) {
    const cx = col * stepX + (row % 2 === 0 ? 0 : Math.floor(stepX / 2));
    const cy = row * stepY;
    composites.push({
      input: rotated,
      top:   Math.round(cy - rH / 2),
      left:  Math.round(cx - rW / 2),
    });
  }
}

const overlayPng = await sharp({
  create: { width: w, height: h, channels: 4,
            background: { r: 0, g: 0, b: 0, alpha: 0 } },
})
.composite(composites)
.png().toBuffer();

return pipeline
  .composite([{ input: overlayPng, blend: 'over' }])
  .jpeg({ quality: 92 })
  .toBuffer();
}



module.exports = { fetchAndWatermark, watermarkImage };
