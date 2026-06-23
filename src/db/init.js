const { query } = require('./index');

async function initDb() {
  // ── Core tables ────────────────────────────────────────────────────────────
  await query(`CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    user_id BIGINT,
    from_tier TEXT,
    to_tier TEXT,
    price FLOAT,
    method TEXT,
    status TEXT DEFAULT 'pending',
    image_url TEXT,
    ticket_channel_id BIGINT,
    booster_id BIGINT,
    booster_earnings FLOAT,
    order_type TEXT,
    service_type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    claimed_at TIMESTAMP,
    estimated_price FLOAT,
    p11_count TEXT,
    booster_rating INT,
    completion_time_seconds INT,
    workspace_channel_id BIGINT,
    brawler_name TEXT,
    trophy_val INT
  )`);

  await query(`CREATE TABLE IF NOT EXISTS vouchers (
    id TEXT PRIMARY KEY,
    code TEXT UNIQUE,
    amount FLOAT,
    used_by BIGINT,
    rating INT DEFAULT 5,
    feedback TEXT,
    image_url TEXT,
    method TEXT,
    order_kind TEXT,
    service_type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  )`);

  await query(`CREATE TABLE IF NOT EXISTS giveaways (
    id TEXT PRIMARY KEY,
    prize TEXT,
    description TEXT,
    winners INT,
    hosted_by BIGINT,
    participants TEXT,
    winner_ids TEXT,
    image_url TEXT,
    extra_entries TEXT,
    ping TEXT,
    bonus_role_id BIGINT,
    ended_at TIMESTAMP,
    channel_id BIGINT
  )`);

  await query(`CREATE TABLE IF NOT EXISTS guild_config (
    guild_id BIGINT PRIMARY KEY,
    vouch_channel_id BIGINT,
    ticket_channel_id BIGINT,
    completed_channel_id BIGINT,
    ticket_category_id BIGINT,
    ticket_panel_title TEXT,
    ticket_panel_desc TEXT,
    ranked_panel_channel_id BIGINT,
    prestige_panel_channel_id BIGINT,
    ranked_ticket_channel_id BIGINT,
    prestige_ticket_channel_id BIGINT,
    winstreak_ticket_channel_id BIGINT,
    owner_id BIGINT,
    ticket_log_channel_id BIGINT,
    application_channel_id BIGINT,
    application_review_channel_id BIGINT,
    account_sale_channel_id BIGINT,
    account_sale_ticket_channel_id BIGINT,
    booster_role_id BIGINT,
    proof_channel_id BIGINT,
    inactive_ticket_hours INT DEFAULT 24,
    application_ticket_channel_id BIGINT,
    carrier_role_id BIGINT,
    ticket_support_roles TEXT,
    reviewer_roles TEXT
  )`);

  await query(`CREATE TABLE IF NOT EXISTS payment_methods (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT,
    label TEXT,
    emoji TEXT,
    UNIQUE(guild_id, label)
  )`);

  await query(`CREATE TABLE IF NOT EXISTS account_listings (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT,
    seller_id BIGINT,
    game TEXT,
    description TEXT,
    price FLOAT,
    contact TEXT,
    image_url TEXT,
    status TEXT DEFAULT 'available',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  )`);

  await query(`CREATE TABLE IF NOT EXISTS booster_availability (
    user_id BIGINT PRIMARY KEY,
    guild_id BIGINT,
    status TEXT DEFAULT 'available',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  )`);

  await query(`CREATE TABLE IF NOT EXISTS rank_prices (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT,
    from_rank TEXT,
    to_rank TEXT,
    base_price FLOAT,
    UNIQUE(guild_id, from_rank, to_rank)
  )`);

  await query(`CREATE TABLE IF NOT EXISTS ticket_activity (
    channel_id BIGINT PRIMARY KEY,
    guild_id BIGINT,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    warned INT DEFAULT 0
  )`);

  await query(`CREATE TABLE IF NOT EXISTS oauth_users (
    user_id BIGINT PRIMARY KEY,
    access_token TEXT,
    refresh_token TEXT
  )`);

  // ── Safe migrations (ADD COLUMN IF NOT EXISTS) ────────────────────────────
  await query(`CREATE TABLE IF NOT EXISTS transcripts (
    id TEXT PRIMARY KEY,
    html TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  )`);

  const migrations = [
    ['orders', 'brawler_name TEXT'],
    ['orders', 'trophy_val INT'],
    ['orders', 'workspace_channel_id BIGINT'],
    ['guild_config', 'account_sale_ticket_channel_id BIGINT'],
    ['guild_config', 'carrier_role_id BIGINT'],
    ['guild_config', 'ticket_support_roles TEXT'],
    ['guild_config', 'reviewer_roles TEXT'],
    ['guild_config', 'winstreak_ticket_channel_id BIGINT'],
    ['guild_config', 'trophies_ticket_channel_id BIGINT'],
    ['guild_config', 'matcherino_ticket_channel_id BIGINT'],
    ['ticket_activity', 'creator_id TEXT'],
  ];

  for (const [table, colDef] of migrations) {
    try {
      await query(`ALTER TABLE ${table} ADD COLUMN IF NOT EXISTS ${colDef}`);
    } catch (_) {
      // Older Postgres without IF NOT EXISTS — silently skip
    }
  }
}

module.exports = { initDb };
