const express = require('express');
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

  app.listen(PORT, () => {
    console.log(`[Stats API] Running on port ${PORT}`);
  });
}

module.exports = { startStatsServer };
