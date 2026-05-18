require('dotenv').config();
const { startBot } = require('./bot');
const { startOAuthServer } = require('./oauth/server');

const token = process.env.DISCORD_TOKEN;
if (!token) {
  console.error('[ERROR] DISCORD_TOKEN not set in environment.');
  process.exit(1);
}

startOAuthServer();
startBot(token);
