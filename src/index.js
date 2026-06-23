require('dotenv').config();
const { startBot, client } = require('./bot');       // ADD client to import
const { startOAuthServer } = require('./oauth/server');
const { startStatsServer } = require('./api/stats'); // ADD

const token = process.env.DISCORD_TOKEN;
if (!token) {
  console.error('[ERROR] DISCORD_TOKEN not set in environment.');
  process.exit(1);
}

startOAuthServer();
startBot(token);
startStatsServer(client); // ADD
