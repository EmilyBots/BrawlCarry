const { SlashCommandBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle } = require('discord.js');
const { baseEmbed } = require('../../utils/embeds');
const { DANGER, SUCCESS } = require('../../config/constants');
const { getConfig } = require('../../db/index');
const axios = require('axios');

const OAUTH_AUTHORIZE_URL = process.env.OAUTH_AUTHORIZE_URL ?? 'http://localhost:5000/authorize';
const OAUTH_BACKEND_URL   = process.env.OAUTH_BACKEND_URL   ?? 'http://localhost:5000';
const RESTORE_SECRET      = process.env.RESTORE_SECRET      ?? '';

// ── /backup_link ──────────────────────────────────────────────────────────────
const backupLinkCmd = {
  data: new SlashCommandBuilder()
    .setName('backup_link')
    .setDescription('DM all members the backup server link')
    .setDefaultMemberPermissions(0x8)
    .addStringOption(o => o.setName('link').setDescription('Backup server invite link').setRequired(true)),

  async execute(interaction) {
    await interaction.deferReply({ ephemeral: true });
    const link    = interaction.options.getString('link');
    const members = (await interaction.guild.members.fetch()).filter(m => !m.user.bot);
    const results = { sent: 0, failed: 0 };

    const CONCURRENCY = 20;
    const all = [...members.values()];

    async function sendDm(member) {
      try {
        const e = baseEmbed('⚠️ Backup Server', DANGER);
        e.setDescription(`If the main server becomes unavailable, join our backup:\n\n> **${link}**`);
        await member.send({ embeds: [e] });
        results.sent++;
      } catch (_) {
        results.failed++;
      }
    }

    // Process in batches to respect rate limits
    for (let i = 0; i < all.length; i += CONCURRENCY) {
      await Promise.all(all.slice(i, i + CONCURRENCY).map(sendDm));
    }

    const e = baseEmbed('📨 Backup Link Sent', SUCCESS);
    e.addFields(
      { name: '✅ Delivered', value: `**${results.sent}**`,  inline: true },
      { name: '❌ Failed',    value: `**${results.failed}**`, inline: true },
    );
    await interaction.followUp({ embeds: [e], ephemeral: true });
  },
};

// ── /backup_panel ─────────────────────────────────────────────────────────────
const backupPanelCmd = {
  data: new SlashCommandBuilder()
    .setName('backup_panel')
    .setDescription('Post the backup access panel so members can authorize')
    .setDefaultMemberPermissions(0x8),

  async execute(interaction) {
    const e = baseEmbed('🛡️ Secure Your Backup Access', DANGER);
    e.setDescription(
      'If the main server is ever deleted, raided or banned, we will automatically add you to our backup server.\n\n' +
      '**Click the button below and authorize with Discord.**\n\n' +
      '🔒 We only request:\n' +
      '> `identify` — to know who you are\n' +
      '> `guilds.join` — to add you to the backup server if needed\n\n' +
      '⚠️ You only need to do this once.'
    );

    const view = new ActionRowBuilder().addComponents(
      new ButtonBuilder()
        .setLabel('🛡️ Secure Backup Access')
        .setStyle(ButtonStyle.Link)
        .setURL(OAUTH_AUTHORIZE_URL)
        .setEmoji('🔒')
    );

    await interaction.channel.send({ embeds: [e], components: [view] });
    await interaction.reply({ content: '✅ Backup panel posted.', ephemeral: true });
  },
};

// ── /restore_backup ───────────────────────────────────────────────────────────
const restoreBackupCmd = {
  data: new SlashCommandBuilder()
    .setName('restore_backup')
    .setDescription('Trigger restore — adds all authorized members to the backup server')
    .setDefaultMemberPermissions(0x8)
    .addStringOption(o => o.setName('backup_server_id').setDescription('ID of the backup server').setRequired(true)),

  async execute(interaction) {
    const cfg     = await getConfig(interaction.guildId);
    const ownerId = cfg?.owner_id ? String(cfg.owner_id) : null;

    if (ownerId && interaction.user.id !== ownerId) {
      return interaction.reply({ content: '❌ Only the server owner can trigger a restore.', ephemeral: true });
    }

    await interaction.deferReply({ ephemeral: true });
    const backupGuildId = interaction.options.getString('backup_server_id');

    try {
      const { data } = await axios.post(`${OAUTH_BACKEND_URL}/restore`, {
        secret:   RESTORE_SECRET,
        guild_id: backupGuildId,
      }, { timeout: 60000 });

      const e = baseEmbed('🛡️ Restore Complete', SUCCESS);
      e.setDescription('All authorized members have been added to the backup server.');
      e.addFields(
        { name: '✅ Added',     value: `**${data.success  ?? 0}**`, inline: true },
        { name: '🔄 Refreshed', value: `**${data.refreshed ?? 0}**`, inline: true },
        { name: '❌ Failed',    value: `**${data.failed   ?? 0}**`, inline: true },
      );
      await interaction.followUp({ embeds: [e], ephemeral: true });
    } catch (err) {
      await interaction.followUp({ content: `❌ Restore failed: \`${err.message}\``, ephemeral: true });
    }
  },
};

module.exports = [backupLinkCmd, backupPanelCmd, restoreBackupCmd];
