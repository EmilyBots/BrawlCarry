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
  const opacity    = 0.13;
  const subSize    = Math.floor(fontSize * 0.78);

  // Tile spacing calculated in rotated space to prevent overlap at -30° angle
  const cos30  = Math.cos(30 * Math.PI / 180);
  const stampW = Math.ceil(21 * fontSize * 0.58); // widest line: "discord.gg/brawlcarry"
  const stampH = lineHeight * 2;
  const stepX  = Math.ceil((stampW / cos30) * 1.13); // min non-overlapping X + 13% margin
  const stepY  = Math.ceil((stampH / cos30) * 1.13); // min non-overlapping Y + 13% margin

  const angle = -30;
  const textElements = [];

  for (let row = -2; row * stepY < h * 2 + h; row++) {
    for (let col = -2; col * stepX < w * 2 + w; col++) {
      // Offset every other row for a diagonal brick pattern
      const x = col * stepX + (row % 2 === 0 ? 0 : stepX / 2);
      const y = row * stepY;

      textElements.push(`
        <g transform="rotate(${angle} ${x} ${y})">
          <text x="${x}" y="${y}"
            font-family="DejaVu Sans, Arial, sans-serif"
            font-size="${fontSize}"
            font-weight="bold"
            fill="rgba(255,255,255,${opacity})"
            text-anchor="middle"
          >${escapeXml('BrawlCarry™')}</text>
          <text x="${x}" y="${y + lineHeight}"
            font-family="DejaVu Sans, Arial, sans-serif"
            font-size="${subSize}"
            font-weight="bold"
            fill="rgba(255,255,255,${opacity})"
            text-anchor="middle"
          >${escapeXml('discord.gg/brawlcarry')}</text>
        </g>`
      );
    }
  }

  const svg = Buffer.from(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
      ${textElements.join('\n')}
    </svg>`
  );

  return pipeline
    .composite([{ input: svg, blend: 'over' }])
    .jpeg({ quality: 92 })
    .toBuffer();
}

function escapeXml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

module.exports = { fetchAndWatermark, watermarkImage };
