const { EmbedBuilder } = require('discord.js');
const { PRIMARY, FOOTER_BRAND } = require('../config/constants');

/**
 * Create a branded embed with consistent footer.
 * @param {string|null} title
 * @param {number} color
 * @param {string|null} description
 */
function baseEmbed(title = null, color = PRIMARY, description = null) {
  const e = new EmbedBuilder().setColor(color).setFooter({ text: FOOTER_BRAND });
  if (title)       e.setTitle(title);
  if (description) e.setDescription(description);
  return e;
}

/**
 * Format a duration in seconds to a human-readable string.
 * @param {number} seconds
 */
function formatDuration(seconds) {
  if (seconds < 60)   return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

module.exports = { baseEmbed, formatDuration };
