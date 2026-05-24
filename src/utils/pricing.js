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

/**
 * Apply trophy-based discount to a prestige price.
 */
function applyTrophyDiscount(price, trophyVal = 0, prestigeSpec = null) {
  const base = PRESTIGE_BASE_TROPHIES[prestigeSpec] ?? 0;
  const relativeTrophies = Math.max(0, trophyVal - base);
  if (relativeTrophies <= 500) price *= 0.5;
  const bands = Math.floor(relativeTrophies / 50);
  const discount = Math.min(bands * 0.02, 0.20);
  price *= (1.0 - discount);
  return Math.round(price * 100) / 100;
}

const PRESTIGE_FLAT_PRICES = {
  'Prestige 0 -> Prestige 1': 8,
  'Prestige 1 -> Prestige 2': 20,
  'Prestige 2 -> Prestige 3': 85,
};

function calculatePrestigePriceFlat(prestigeSpec, serviceType) {
  const base = PRESTIGE_FLAT_PRICES[prestigeSpec] ?? 0;
  return serviceType === 'carry' ? base * 2 : base;
}

module.exports = { calculateRankPrice, applyTrophyDiscount, calculatePrestigePriceFlat, rankEmoji, prestigeEmoji, buildOrderDetailsStr };
