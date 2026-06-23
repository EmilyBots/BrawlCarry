const express = require('express');
const axios   = require('axios');
const { queryOne, queryAll } = require('../db/index');

const app = express();
app.use(express.json());

const CLIENT_ID      = process.env.DISCORD_CLIENT_ID;
const CLIENT_SECRET  = process.env.DISCORD_CLIENT_SECRET;
const REDIRECT_URI   = process.env.OAUTH_REDIRECT_URI;
const BOT_TOKEN      = process.env.DISCORD_TOKEN;
const RESTORE_SECRET = process.env.RESTORE_SECRET;
const PORT           = parseInt(process.env.OAUTH_PORT ?? '5000');

// ── /authorize ────────────────────────────────────────────────────────────────
app.get('/authorize', (req, res) => {
  const url =
    `https://discord.com/api/oauth2/authorize` +
    `?client_id=${CLIENT_ID}` +
    `&redirect_uri=${encodeURIComponent(REDIRECT_URI)}` +
    `&response_type=code` +
    `&scope=identify%20guilds.join`;
  res.redirect(url);
});

// ── /callback ─────────────────────────────────────────────────────────────────
app.get('/callback', async (req, res) => {
  const code = req.query.code;
  if (!code) return res.status(400).send('<h2>❌ Authorization failed. Missing code.</h2>');

  try {
    const tokenResp = await axios.post(
      'https://discord.com/api/oauth2/token',
      new URLSearchParams({
        client_id:     CLIENT_ID,
        client_secret: CLIENT_SECRET,
        grant_type:    'authorization_code',
        code,
        redirect_uri:  REDIRECT_URI,
      }),
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
    );

    const { access_token, refresh_token } = tokenResp.data;
    if (!access_token) return res.status(400).send('<h2>❌ OAuth failed. Please try again.</h2>');

    const userResp = await axios.get('https://discord.com/api/users/@me', {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    const userId = userResp.data.id;

    await queryOne(
      `INSERT INTO oauth_users (user_id, access_token, refresh_token)
       VALUES ($1, $2, $3)
       ON CONFLICT (user_id) DO UPDATE SET access_token = EXCLUDED.access_token, refresh_token = EXCLUDED.refresh_token`,
      [userId, access_token, refresh_token]
    );

    res.send(`
      <html>
      <body style="background:#0A0E1A;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;">
      <div style="text-align:center;color:white;">
        <h1 style="color:#2ECC71;font-size:48px;">✅</h1>
        <h2>Backup Access Secured!</h2>
        <p style="color:#aaa;">You will automatically be added to the backup server if needed.<br>You may close this tab.</p>
      </div>
      </body>
      </html>
    `);
  } catch (err) {
    console.error('[OAUTH] /callback error:', err.message);
    res.status(500).send('<h2>❌ Internal error. Please try again.</h2>');
  }
});

// ── /restore ──────────────────────────────────────────────────────────────────
app.post('/restore', async (req, res) => {
  const { secret, guild_id } = req.body;
  if (secret !== RESTORE_SECRET) return res.status(403).json({ error: 'Unauthorized' });
  if (!guild_id)                 return res.status(400).json({ error: 'Missing guild_id' });

  const users   = await queryAll('SELECT * FROM oauth_users');
  const results = { success: 0, failed: 0, refreshed: 0 };

  for (const user of users) {
    let token = user.access_token;

    let resp = await addToGuild(guild_id, user.user_id, token);

    if (resp === 401) {
      const newToken = await refreshUserToken(user);
      if (newToken) {
        results.refreshed++;
        token = newToken;
        resp  = await addToGuild(guild_id, user.user_id, token);
      }
    }

    if (resp === 200 || resp === 201 || resp === 204) results.success++;
    else if (resp !== 401) results.failed++;
  }

  res.json(results);
});

// ── /count ────────────────────────────────────────────────────────────────────
app.get('/count', async (req, res) => {
  const row = await queryOne('SELECT COUNT(*) AS cnt FROM oauth_users');
  res.json({ authorized_users: parseInt(row?.cnt ?? 0) });
});

// ── Helpers ───────────────────────────────────────────────────────────────────
async function addToGuild(guildId, userId, accessToken) {
  try {
    const { status } = await axios.put(
      `https://discord.com/api/guilds/${guildId}/members/${userId}`,
      { access_token: accessToken },
      { headers: { Authorization: `Bot ${BOT_TOKEN}` } }
    );
    return status;
  } catch (err) {
    return err.response?.status ?? 500;
  }
}

async function refreshUserToken(user) {
  try {
    const { data } = await axios.post(
      'https://discord.com/api/oauth2/token',
      new URLSearchParams({
        client_id:     CLIENT_ID,
        client_secret: CLIENT_SECRET,
        grant_type:    'refresh_token',
        refresh_token: user.refresh_token,
      }),
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
    );
    if (data.access_token) {
      await queryOne(
        'UPDATE oauth_users SET access_token = $1, refresh_token = $2 WHERE user_id = $3',
        [data.access_token, data.refresh_token, user.user_id]
      );
      return data.access_token;
    }
    return null;
  } catch (_) {
    return null;
  }
}

// ── /auth/founder ─────────────────────────────────────────────────────────────
app.get('/auth/founder', (req, res) => {
  const url = `https://discord.com/oauth2/authorize?client_id=${CLIENT_ID}&redirect_uri=${encodeURIComponent(process.env.FOUNDER_REDIRECT_URI)}&response_type=code&scope=role_connections.write%20identify`;
  res.redirect(url);
});

app.get('/callback/founder', async (req, res) => {
  const code = req.query.code;
  if (!code) return res.send('❌ Nessun codice');

  const tokenResp = await axios.post(
    'https://discord.com/api/oauth2/token',
    new URLSearchParams({
      client_id: CLIENT_ID,
      client_secret: CLIENT_SECRET,
      grant_type: 'authorization_code',
      code,
      redirect_uri: process.env.FOUNDER_REDIRECT_URI,
    }),
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
  );

  const { access_token } = tokenResp.data;

  await axios.put(
    `https://discord.com/api/v10/users/@me/applications/${process.env.DISCORD_APPLICATION_ID}/role-connection`,
    { platform_name: 'BrawlCarry', metadata: { is_founder: true } },
    { headers: { Authorization: `Bearer ${access_token}`, 'Content-Type': 'application/json' } }
  );

  res.send('✅ Sei Founder! Controlla il profilo Discord.');
});

// ── Start ─────────────────────────────────────────────────────────────────────
function startOAuthServer() {
  app.listen(PORT, () => {
    console.log(`[OK] OAuth server listening on port ${PORT}`);
  });
}

module.exports = { startOAuthServer };
