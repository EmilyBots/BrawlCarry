const { Pool } = require('pg');

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.DATABASE_URL?.includes('railway') ? { rejectUnauthorized: false } : false,
});

/**
 * Run a parameterized query and return all rows.
 * @param {string} text
 * @param {any[]} params
 * @returns {Promise<import('pg').QueryResult>}
 */
async function query(text, params) {
  const client = await pool.connect();
  try {
    return await client.query(text, params);
  } finally {
    client.release();
  }
}

/**
 * Fetch a single row or null.
 */
async function queryOne(text, params) {
  const result = await query(text, params);
  return result.rows[0] ?? null;
}

/**
 * Fetch all rows.
 */
async function queryAll(text, params) {
  const result = await query(text, params);
  return result.rows;
}

// ── Guild config helpers ─────────────────────────────────────────────────────

async function getConfig(guildId) {
  return queryOne('SELECT * FROM guild_config WHERE guild_id = $1', [guildId]);
}

async function setConfig(guildId, updates) {
  if (!updates || Object.keys(updates).length === 0) return;

  const existing = await queryOne('SELECT guild_id FROM guild_config WHERE guild_id = $1', [guildId]);
  if (!existing) {
    await query('INSERT INTO guild_config (guild_id) VALUES ($1)', [guildId]);
  }

  const keys = Object.keys(updates);
  const values = Object.values(updates);
  const setClause = keys.map((k, i) => `${k} = $${i + 1}`).join(', ');
  await query(
    `UPDATE guild_config SET ${setClause} WHERE guild_id = $${keys.length + 1}`,
    [...values, guildId]
  );
}

module.exports = { pool, query, queryOne, queryAll, getConfig, setConfig };
