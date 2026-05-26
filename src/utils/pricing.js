const { queryOne } = require('../db/index');
const {
  ALL_RANKS, RANK_EMOJI, PRESTIGE_EMOJI,
  TIER_DIVISION_PRICES, EXPLICIT_RANK_PRICES,
  PRESTIGE_BASE_TROPHIES,
} = require('../config/constants');

function rankEmoji(rankName) {
  for (const [prefix, emoji] of Object.entries(RANK_EMOJI)) {
    if (rankName.startsWith(prefix)) return emoji;
  }
  return '';
}

function prestigeEmoji(spec) {
  return PRESTIGE_EMOJI[spec] ?? '✨';
}

function buildOrderDetailsStr(orderType, fromTier, toTier, serviceType) {
  if (orderType === 'prestige') {
    const spec = `${fromTier} -> ${toTier}`;
    return `${prestigeEmoji(spec)} \`${fromTier}\` → \`${toTier}\``;
  }
  return `${rankEmoji(fromTier ?? '')} \`${fromTier}\` → ${rankEmoji(toTier ?? '')} \`${toTier}\``;
}

/**
 * @param {string} fromRank
 * @param {string} toRank
 * @param {string} p11Str   e.g. "41-50"
 * @param {string} serviceType  "boost" | "carry"
 * @param {string|bigint} guildId
 */
async function calculateRankPrice(fromRank, toRank, p11Str, serviceType, guildId) {
  // Check for a custom guild price override first
  const custom = await queryOne(
    'SELECT base_price FROM rank_prices WHERE guild_id = $1 AND from_rank = $2 AND to_rank = $3',
    [guildId, fromRank, toRank]
  );

  let base;
  if (custom) {
    base = parseFloat(custom.base_price);
  } else {
    const explicitKey = `${fromRank}|${toRank}`;
    if (EXPLICIT_RANK_PRICES[explicitKey] !== undefined) {
      base = EXPLICIT_RANK_PRICES[explicitKey];
    } else {
      const fi = ALL_RANKS.indexOf(fromRank);
      const ti = toRank === 'Pro' ? ALL_RANKS.length : ALL_RANKS.indexOf(toRank);
      if (fi === -1 || ti <= fi) return 0;

      base = 0;
      for (let i = fi; i < Math.min(ti, ALL_RANKS.length - 1); i++) {
        const stepKey = `${ALL_RANKS[i]}|${ALL_RANKS[i + 1]}`;
        if (EXPLICIT_RANK_PRICES[stepKey] !== undefined) {
          base += EXPLICIT_RANK_PRICES[stepKey];
        } else {
          const tier = ALL_RANKS[i].split(' ')[0];
          base += TIER_DIVISION_PRICES[tier] ?? 0.80;
        }
      }
      if (toRank === 'Pro') {
        const finalKey = `${ALL_RANKS[ALL_RANKS.length - 1]}|Pro`;
        base += EXPLICIT_RANK_PRICES[finalKey] ?? TIER_DIVISION_PRICES['Masters'] ?? 10;
      }
    }
  }

  // P11 adjustment
  let p11Num = 45;
  if (p11Str) {
    try {
      if (p11Str.includes('-')) {
        const parts = p11Str.split('-');
        p11Num = (parseInt(parts[0]) + parseInt(parts[1])) >> 1;
      } else if (p11Str.includes('+')) {
        p11Num = parseInt(p11Str) + 5;
      } else {
        p11Num = parseInt(p11Str);
      }
    } catch (_) {
      p11Num = 45;
    }
  }

  let multiplier = 1.0;
if (p11Num < 40) multiplier = 1.0 + Math.min((40 - p11Num) * 0.005, 0.25);
else if (p11Num > 50) multiplier = 1.0 - Math.min((p11Num - 50) * 0.004, 0.20);

const masterOneIdx = ALL_RANKS.indexOf('Masters I');
const fromIdx = ALL_RANKS.indexOf(fromRank);
if (masterOneIdx !== -1 && fromIdx >= masterOneIdx) base *= multiplier;
  if (serviceType === 'carry') base *= 2.0;
  return Math.round(base * 100) / 100;
}

// ── Prestige pricing ──────────────────────────────────────────────────────────
// Source of truth: rangeStart/rangeEnd (trophies) and fullPrice (€) per spec.
// To update prices: change fullPrice here only.
// To upgrade to weighted logic (v2): replace calculatePrestigePrice body only —
// signature (prestigeSpec, trophyVal, serviceType) => number stays the same.
const PRESTIGE_CONFIG = {
  'Prestige 0 -> Prestige 1': { rangeStart:    0, rangeEnd: 1000, fullPrice:  8 },
  'Prestige 1 -> Prestige 2': { rangeStart: 1000, rangeEnd: 2000, fullPrice: 20 },
  'Prestige 2 -> Prestige 3': { rangeStart: 2000, rangeEnd: 3000, fullPrice: 80 },
};

/**
 * Returns an error string if trophyVal is outside the valid range for the spec,
 * or null if valid.
 */
function validatePrestigeTrophies(prestigeSpec, trophyVal) {
  const cfg = PRESTIGE_CONFIG[prestigeSpec];
  if (!cfg) return `❌ Unknown prestige spec: \`${prestigeSpec}\`.`;
  if (isNaN(trophyVal)) return '❌ Please enter a valid number like `750`.';
  if (trophyVal < cfg.rangeStart || trophyVal > cfg.rangeEnd) {
    return `❌ For **${prestigeSpec}**, trophies must be between **${cfg.rangeStart.toLocaleString()}** and **${cfg.rangeEnd.toLocaleString()}**.\nYou entered \`${trophyVal.toLocaleString()}\`.`;
  }
  return null;
}

/**
 * Calculate prestige price — v1: linear system.
 * Range divided into 50-trophy blocks, each worth an equal share of fullPrice.
 *
 * @param {string} prestigeSpec  e.g. 'Prestige 1 -> Prestige 2'
 * @param {number} trophyVal     current trophies on the brawler
 * @param {string} serviceType   'boost' | 'carry'
 * @returns {number}             estimated price in €
 */
const PRESTIGE_2_3_PRICES = {
  2000: 80,    2050: 77,  2100: 73.5,    2150: 70,
  2200: 67,    2250: 63,    2300: 60, 2350: 56,
  2400: 52, 2450: 48,    2500: 44.5, 2550: 40,
  2600: 36, 2650: 33,    2700: 30,    2750: 25,
  2800: 22,  2850: 18,    2900: 14,    2950: 9,
};

function calculatePrestigePrice(prestigeSpec, trophyVal, serviceType) {
  const cfg = PRESTIGE_CONFIG[prestigeSpec];
  if (!cfg) return 0;

  let base;

  if (prestigeSpec === 'Prestige 2 -> Prestige 3') {
    const blockStart = Math.floor((trophyVal - 2000) / 50) * 50 + 2000;
    base = PRESTIGE_2_3_PRICES[blockStart] ?? 0;
  } else {
    const totalBlocks      = (cfg.rangeEnd - cfg.rangeStart) / 50;
    const blocksCompleted  = Math.floor((trophyVal - cfg.rangeStart) / 50);
    const discountPerBlock = cfg.fullPrice / totalBlocks;
    base = Math.max(0, cfg.fullPrice - blocksCompleted * discountPerBlock);
  }

  const price = serviceType === 'carry' ? base * 2 : base;
  return Math.round(price * 100) / 100;
}

module.exports = { calculateRankPrice, calculatePrestigePrice, validatePrestigeTrophies, rankEmoji, prestigeEmoji, buildOrderDetailsStr };
