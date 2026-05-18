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
  try {
    const response = await axios.get(url, { responseType: 'arraybuffer', timeout: 10000 });
    const rawBuffer = Buffer.from(response.data);
    const marked = await watermarkImage(rawBuffer, 'Brawl Carry Vouches', blur);
    return new AttachmentBuilder(marked, { name: 'proof.jpg' });
  } catch (_) {
    return null;
  }
}

/**
 * Apply a tiled diagonal watermark to an image buffer.
 * @param {Buffer} imageBuffer
 * @param {string} text
 * @param {boolean} blur
 * @returns {Promise<Buffer>}
 */
async function watermarkImage(imageBuffer, text = 'Brawl Carry Vouches', blur = false) {
  let pipeline = sharp(imageBuffer);
  const meta   = await pipeline.metadata();
  const w      = meta.width  ?? 800;
  const h      = meta.height ?? 600;

  if (blur) pipeline = pipeline.blur(6);

  // Build an SVG overlay with tiled diagonal text
  const fontSize = Math.max(16, Math.floor(w / 18));
  const stepX    = fontSize * text.length * 0.55 + 60;
  const stepY    = fontSize + 40;

  const textElements = [];
  for (let y = -h; y < h * 2; y += stepY) {
    for (let x = -w; x < w * 2; x += stepX) {
      textElements.push(
        `<text
          x="${x}" y="${y}"
          font-family="DejaVu Sans, Arial, sans-serif"
          font-size="${fontSize}"
          font-weight="bold"
          fill="rgba(255,255,255,0.22)"
          transform="rotate(-30 ${x} ${y})"
        >${escapeXml(text)}</text>`
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
