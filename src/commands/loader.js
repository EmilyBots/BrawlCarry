const fs   = require('fs');
const path = require('path');
const { REST, Routes } = require('discord.js');

function loadCommands(client) {
  const dirs = ['admin', 'user'];
  for (const dir of dirs) {
    const folder = path.join(__dirname, dir);
    if (!fs.existsSync(folder)) continue;
    for (const file of fs.readdirSync(folder).filter(f => f.endsWith('.js'))) {
      const exported = require(path.join(folder, file));
      // Support both single-export and array-export patterns
      const commands = Array.isArray(exported) ? exported : [exported];
      for (const command of commands) {
        if (!command?.data?.name || !command?.execute) {
          console.warn(`[WARN] Skipping entry in ${file} — missing data.name or execute`);
          continue;
        }
        client.commands.set(command.data.name, command);
      }
    }
  }
  console.log(`[OK] Loaded ${client.commands.size} commands`);
}

async function registerCommands(client) {
  const token    = process.env.DISCORD_TOKEN;
  const clientId = process.env.DISCORD_CLIENT_ID;
  if (!token || !clientId) {
    console.warn('[WARN] Missing DISCORD_TOKEN or DISCORD_CLIENT_ID — skipping command registration');
    return;
  }

  const rest    = new REST({ version: '10' }).setToken(token);
  const payload = client.commands.map(c => c.data.toJSON());

  const guilds = process.env.ALLOWED_GUILDS
    ? process.env.ALLOWED_GUILDS.split(',').map(g => g.trim()).filter(Boolean)
    : [];

  if (guilds.length) {
    // Register per-guild for instant updates
    for (const guildId of guilds) {
      await rest.put(Routes.applicationGuildCommands(clientId, guildId), { body: payload });
      console.log(`[OK] Commands registered to guild ${guildId}`);
    }
  } else {
    // Global registration (takes up to 1 hour to propagate)
    await rest.put(Routes.applicationCommands(clientId), { body: payload });
    console.log('[OK] Commands registered globally');
  }
}

module.exports = { loadCommands, registerCommands };
