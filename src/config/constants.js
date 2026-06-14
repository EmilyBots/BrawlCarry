// ── Colors ───────────────────────────────────────────────────────────────────
const PRIMARY  = 0x9B59B6;
const GOLD     = 0xF1C40F;
const SUCCESS  = 0x2ECC71;
const DANGER   = 0xE74C3C;
const DARK     = 0x0A0E1A;
const ACCENT   = 0xA855F7;

// ── Branding ─────────────────────────────────────────────────────────────────
const FOOTER_BRAND = 'Brawl Carry™';

// ── Hardcoded support role IDs ────────────────────────────────────────────────
const HARDCODED_SUPPORT_ROLES = [1491447093078921267n, 1355262062124859600n, 1479079737052762205n];

// ── Ranks ─────────────────────────────────────────────────────────────────────
const CURRENT_RANKS = [
  'Bronze I', 'Bronze II', 'Bronze III',
  'Silver I', 'Silver II', 'Silver III',
  'Gold I', 'Gold II', 'Gold III',
  'Diamond I', 'Diamond II', 'Diamond III',
  'Mythic I', 'Mythic II', 'Mythic III',
  'Legendary I', 'Legendary II', 'Legendary III',
  'Masters I', 'Masters II', 'Masters III',
];

const ALL_RANKS = [...CURRENT_RANKS];

// Minimum desired rank is Diamond I
const DESIRED_RANKS = [
  'Diamond I', 'Diamond II', 'Diamond III',
  'Mythic I', 'Mythic II', 'Mythic III',
  'Legendary I', 'Legendary II', 'Legendary III',
  'Masters I', 'Masters II', 'Masters III',
  'Pro',
];

const RANK_EMOJI = {
  Bronze:    '<:Bronze:1493263821375279135>',
  Silver:    '<:Silver:1493263822906196039>',
  Gold:      '<:Gold:1493263820318052473>',
  Diamond:   '<:Diamond:1493263818275426314>',
  Mythic:    '<:Mythic:1493263816069218544>',
  Legendary: '<:Legendary:1493263814802542796>',
  Masters:   '<:Masters:1493263813519343647>',
  Pro:       '<:Pro:1493263812109795459>',
};

// ── Prestige ──────────────────────────────────────────────────────────────────
const PRESTIGE_OPTIONS = [
  'Prestige 0 -> Prestige 1',
  'Prestige 1 -> Prestige 2',
  'Prestige 2 -> Prestige 3',
];

const PRESTIGE_PRICES = {
  'Prestige 0 -> Prestige 1': '8',
  'Prestige 1 -> Prestige 2': '20',
  'Prestige 2 -> Prestige 3': '90',
};

const PRESTIGE_BASE_TROPHIES = {
  'Prestige 0 -> Prestige 1': 0,
  'Prestige 1 -> Prestige 2': 1000,
  'Prestige 2 -> Prestige 3': 2000,
};

const PRESTIGE_EMOJI = {
  'Prestige 0 -> Prestige 1': '<:Prestige1:1491103698116677693>',
  'Prestige 1 -> Prestige 2': '<:Prestige2:1491103696153477161>',
  'Prestige 2 -> Prestige 3': '<:Prestige3:1491103694433816688>',
};

// ── Pricing ───────────────────────────────────────────────────────────────────
const TIER_DIVISION_PRICES = {
  Bronze:    0.80,
  Silver:    0.80,
  Gold:      1.00,
  Diamond:   2.00,
  Mythic:    2.00,
  Legendary: 4.00,
  Masters:   10.00,
};

// Key format: 'from_rank|to_rank'
const EXPLICIT_RANK_PRICES = {
  'Silver I|Gold I':         2.60,
  'Gold I|Diamond I':        4.00,
  'Diamond I|Mythic I':      5.65,
  'Mythic I|Legendary I':    14.00,
  'Legendary I|Masters I':   30.00,
  'Masters I|Pro':           225.00,
  'Mythic I|Mythic II':      4.00,
  'Mythic II|Mythic III':    5.00,
  'Mythic III|Legendary I':  5.00,
  'Diamond III|Mythic I':    2.25,
  'Legendary I|Legendary II':  9.00,
  'Legendary II|Legendary III': 9.00,
  'Legendary III|Masters I': 12.00,
  'Masters I|Masters II':    35.00,
  'Masters II|Masters III':  70.00,
  'Masters III|Pro':         120.00,
};

// ── Misc options ──────────────────────────────────────────────────────────────
const P11_OPTIONS    = ['0-10', '11-20', '21-30', '31-40', '41-50', '51-60', '61-70', '71+'];
const P11_EMOJI      = '<:P11:1491455088429109258>';
const TROPHY_OPTIONS = ['0 - 500', '501 - 1000', '1001 - 1500', '1501 - 2000', '2001 - 2500', '2501 - 3000', '3001+'];

const AVAILABILITY_STATUSES = ['available', 'busy', 'offline'];

const DEFAULT_PAYMENT_METHODS = [
  { label: 'PayPal',        emoji: '<:Paypal:1490768356960243764>' },
  { label: 'Bank Transfer', emoji: '🏦' },
  { label: 'Crypto',        emoji: '🪙' },
];

// ── Winstreak ─────────────────────────────────────────────────────────────────
const WINSTREAK_EMOJI   = '<:Winstreak:1508363674908102657>';
const WINSTREAK_OPTIONS = ['50 Wins', '67 Wins', '100 Wins', '111 Wins', '125 Wins', '200 Wins'];
const WINSTREAK_PRICES  = {
  '50 Wins':  20,
  '67 Wins':  30,
  '100 Wins': 50,
  '111 Wins': 60,
  '125 Wins': 70,
  '200 Wins': 105,
};

module.exports = {
  PRIMARY, GOLD, SUCCESS, DANGER, DARK, ACCENT,
  FOOTER_BRAND, HARDCODED_SUPPORT_ROLES,
  CURRENT_RANKS, ALL_RANKS, DESIRED_RANKS, RANK_EMOJI,
  PRESTIGE_OPTIONS, PRESTIGE_PRICES, PRESTIGE_BASE_TROPHIES, PRESTIGE_EMOJI,
  TIER_DIVISION_PRICES, EXPLICIT_RANK_PRICES,
  P11_OPTIONS, P11_EMOJI, TROPHY_OPTIONS,
  AVAILABILITY_STATUSES, DEFAULT_PAYMENT_METHODS,
  WINSTREAK_EMOJI, WINSTREAK_OPTIONS, WINSTREAK_PRICES,
};
