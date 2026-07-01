const express = require('express');
const axios   = require('axios');
const { queryOne } = require('../db');
 
function startStatsServer(client) {
  const app = express();
  const PORT = process.env.STATS_PORT || 4000;
  const GUILD_ID = process.env.GUILD_ID;

  app.use((req, res, next) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    if (req.method === 'OPTIONS') return res.sendStatus(204);
    next();
  });

  app.use(express.json({ limit: '10mb' }));

  app.get('/api/stats', async (req, res) => {
    try {
      const guild = client.guilds.cache.get(GUILD_ID);

      const [orders, vouches] = await Promise.all([
        queryOne(`SELECT COUNT(*) as count FROM orders WHERE status = 'completed'`).catch(e => { console.error('[Stats API] orders query:', e.message); return null; }),
        queryOne(`SELECT COUNT(*) as count FROM vouchers`).catch(e => { console.error('[Stats API] vouches query:', e.message); return null; }),
      ]);

      console.log('[Stats API] orders row:', orders, '| vouches row:', vouches);
      res.json({
        memberCount:     guild?.memberCount ?? 0,
        ordersCompleted: parseInt(orders?.count ?? 0),
        totalVouches:    parseInt(vouches?.count ?? 0),
      });
    } catch (err) {
      console.error('[Stats API]', err);
      res.status(500).json({ error: 'Internal server error' });
    }
  });

  app.use(express.json({ limit: '10mb' }));

  app.post('/api/transcripts/upload', async (req, res) => {
    try {
      const { id, html } = req.body;
      if (!id || !html) return res.status(400).json({ error: 'Missing id or html' });
      await queryOne(
        `INSERT INTO transcripts (id, html) VALUES ($1, $2)
         ON CONFLICT (id) DO UPDATE SET html = EXCLUDED.html`,
        [id, html]
      );
      const url = `${process.env.SITE_URL ?? 'https://www.brawlcarry.com'}/transcripts/${id}`;
      res.json({ url });
    } catch (err) {
      console.error('[Transcripts] Upload error:', err);
      res.status(500).json({ error: 'Internal server error' });
    }
  });

  app.get('/transcripts/:id', async (req, res) => {
    try {
      const row = await queryOne('SELECT html FROM transcripts WHERE id = $1', [req.params.id]);
      if (!row) return res.status(404).send('<h1>Transcript not found</h1>');
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.send(row.html);
    } catch (err) {
      console.error('[Transcripts] Serve error:', err);
      res.status(500).send('<h1>Internal server error</h1>');
    }
  });

  // NUOVO
  // ── /auth/founder ──────────────────────────────────────────────────────────
  app.get('/auth/founder', (req, res) => {
    const CLIENT_ID = process.env.DISCORD_CLIENT_ID;
    const url = `https://discord.com/oauth2/authorize?client_id=${CLIENT_ID}&redirect_uri=${encodeURIComponent(process.env.FOUNDER_REDIRECT_URI)}&response_type=code&scope=role_connections.write%20identify`;
    res.redirect(url);
  });

  app.get('/callback/founder', async (req, res) => {
    const CLIENT_ID     = process.env.DISCORD_CLIENT_ID;
    const CLIENT_SECRET = process.env.DISCORD_CLIENT_SECRET;
    const code = req.query.code;
    if (!code) return res.send('❌ Nessun codice');
    try {
      const tokenResp = await axios.post(
        'https://discord.com/api/oauth2/token',
        new URLSearchParams({
          client_id:     CLIENT_ID,
          client_secret: CLIENT_SECRET,
          grant_type:    'authorization_code',
          code,
          redirect_uri:  process.env.FOUNDER_REDIRECT_URI,
        }),
        { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
      );
      const { access_token } = tokenResp.data;

// Who is this?
const userResp = await axios.get('https://discord.com/api/v10/users/@me', {
  headers: { Authorization: `Bearer ${access_token}` },
});
const userId = userResp.data.id;

const FOUNDER_USER_ID = process.env.FOUNDER_USER_ID; // your Discord user ID

if (userId !== FOUNDER_USER_ID) {
  // Not you: explicitly set false, don't assign the role
  await axios.put(
    `https://discord.com/api/v10/users/@me/applications/${process.env.DISCORD_APPLICATION_ID}/role-connection`,
    { platform_name: 'BrawlCarry', metadata: { is_founder: 0 } },
    { headers: { Authorization: `Bearer ${access_token}`, 'Content-Type': 'application/json' } }
  );
  return res.send('❌ This role is not available for your account.');
}

await axios.put(
  `https://discord.com/api/v10/users/@me/applications/${process.env.DISCORD_APPLICATION_ID}/role-connection`,
  { platform_name: 'BrawlCarry', metadata: { is_founder: 1 } },
  { headers: { Authorization: `Bearer ${access_token}`, 'Content-Type': 'application/json' } }
);
res.send('✅ You are Founder! Check your Discord profile.');
    } catch (err) {
      console.error('[Founder OAuth] error:', err.message);
      res.status(500).send('❌ Errore interno. Riprova.');
    }
  });

  app.listen(PORT, () => {
    console.log(`[Stats API] Running on port ${PORT}`);
  });
}

module.exports = { startStatsServer };
