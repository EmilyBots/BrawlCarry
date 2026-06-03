const { Client, GatewayIntentBits, Partials, Collection, EmbedBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, ContainerBuilder, TextDisplayBuilder, SeparatorBuilder, SectionBuilder, ThumbnailBuilder, MessageFlags } = require('discord.js');
const { initDb } = require('./db/init');
const { loadCommands, registerCommands } = require('./commands/loader');
const { loadInteractions } = require('./interactions/loader');
const { startGiveawayEndLoop, startGiveawayReminderLoop } = require('./tasks/giveaway_end');
const { startInactiveTicketLoop } = require('./tasks/inactive_tickets');

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.DirectMessages,
  ],
  partials: [Partials.Channel],
});

const ALLOWED_GUILDS = process.env.ALLOWED_GUILDS
  ? process.env.ALLOWED_GUILDS.split(',').map(g => g.trim()).filter(Boolean)
  : [];

// ── Commands & interactions ─────────────────────────────────────────────────
client.commands = new Collection();
loadCommands(client);

// ── Guild guard ──────────────────────────────────────────────────────────────
client.on('interactionCreate', async (interaction) => {
  if (ALLOWED_GUILDS.length && !ALLOWED_GUILDS.includes(String(interaction.guildId))) {
    if (interaction.isRepliable()) {
      await interaction.reply({ content: '❌ This bot is not authorized to operate in this server.', ephemeral: true }).catch(() => {});
    }
    return;
  }

  // Slash commands
  if (interaction.isChatInputCommand()) {
    const command = client.commands.get(interaction.commandName);
    if (!command) return;
    try {
      await command.execute(interaction, client);
    } catch (err) {
      console.error(`[CMD ERROR] /${interaction.commandName}\n`, err);
      const msg = '❌ An internal error occurred. Please try again.';
      if (interaction.replied || interaction.deferred) {
        await interaction.followup.send({ content: msg, ephemeral: true }).catch(() => {});
      } else {
        await interaction.reply({ content: msg, ephemeral: true }).catch(() => {});
      }
    }
    return;
  }

  // Buttons, selects, modals
  loadInteractions(interaction, client);
});

// ── Message listener — update ticket activity ─────────────────────────────────
client.on('messageCreate', async (message) => {
  if (message.author.bot) return;

  // Auto-delete non-"/invites" messages in the invites-only channel
  if (message.channelId === '1495726939099500585' && message.content.trim() !== '/invites') {
    await message.delete().catch(() => {});
    return;
  }

  if (message.guild && message.channel.isThread()) {
    const { queryOne } = require('./db/index');
    const exists = await queryOne('SELECT 1 FROM ticket_activity WHERE channel_id = $1', [message.channelId]).catch(() => null);
    if (exists) {
      const { updateTicketActivity } = require('./utils/permissions');
      await updateTicketActivity(message.channelId, message.guildId).catch(() => {});
    }
  }
});

// ── Ready ────────────────────────────────────────────────────────────────────
client.once('ready', async () => {
  console.log(`[OK] Logged in as ${client.user.tag}`);

  await initDb();
  console.log('[OK] Database initialised');

  // ── Schema migrations ──────────────────────────────────────────────────────
  const { queryOne: _migrate } = require('./db/index');
  await _migrate(`ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS reminder_seconds INTEGER DEFAULT NULL`).catch(() => {});
  await _migrate(`ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS reminder_sent BOOLEAN NOT NULL DEFAULT FALSE`).catch(() => {});
  await _migrate(`ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS message_id TEXT DEFAULT NULL`).catch(() => {});
  console.log('[OK] Schema migrations applied');

  await registerCommands(client);
  console.log('[OK] Slash commands registered');

  startGiveawayEndLoop(client);
  startGiveawayReminderLoop(client);
  startInactiveTicketLoop(client);
  console.log('[OK] Background tasks started');
});


// ── Welcome DM ───────────────────────────────────────────────────────────────
client.on('guildMemberAdd', async (member) => {
  try {
    const container = new ContainerBuilder()
      .setAccentColor(0x5865F2)
      .addSectionComponents(
        new SectionBuilder()
          .addTextDisplayComponents(
            new TextDisplayBuilder().setContent(
              '# Welcome to BrawlCarry™\n' +
              '### Get your orders completed by trusted pro players <:Boost:1508378809676861573>\n\n' +
              '-# Join our [Server Backup](https://discord.com/channels/1355262062095372429/1491416796581068860)'
            )
          )
          .setThumbnailAccessory(
            new ThumbnailBuilder({ media: { url: 'https://i.imgur.com/VqC9n9k.png' } })
          )
      )
      .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
      .addActionRowComponents(
        new ActionRowBuilder().addComponents(
          new ButtonBuilder()
            .setLabel('Order Now')
            .setEmoji('🛒')
            .setStyle(ButtonStyle.Link)
            .setURL('https://discord.com/channels/1355262062095372429/1355262063089291463')
        )
      );

    await member.send({
      content: `<@${member.id}>`,
      components: [container],
      flags: MessageFlags.IsComponentsV2,
    });
    console.log(`[WELCOME DM] Sent to ${member.user.tag}`);
  } catch (err) {
    console.warn(`[WELCOME DM] Failed for ${member.user?.tag}: ${err.message}`);
  }
});
  


// ── Global error handlers ────────────────────────────────────────────────────
client.on('error', (err) => console.error('[BOT ERROR]', err));
process.on('unhandledRejection', (err) => console.error('[UNHANDLED REJECTION]', err));

function startBot(token) {
  client.login(token);
}

module.exports = { startBot, client };
