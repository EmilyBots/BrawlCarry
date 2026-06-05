const { SlashCommandBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder } = require('discord.js');
const { baseEmbed } = require('../../utils/embeds');
const { PRIMARY, GOLD } = require('../../config/constants');
const { getBoosterStatus } = require('../../utils/permissions');

// ── /availability ─────────────────────────────────────────────────────────────
const availabilityCmd = {
  data: new SlashCommandBuilder()
    .setName('availability')
    .setDescription('Set your booster availability status'),

  async execute(interaction) {
    if (!interaction.member.roles.cache.has('1479079737052762205') && !interaction.member.roles.cache.has('1485296409795235910')) {
      return interaction.reply({ content: '❌ You do not have the required role to use this command.', ephemeral: true });
    }
    const current   = await getBoosterStatus(interaction.user.id);
    const statusMap = { available: '🟢 Available', busy: '🟡 Busy', offline: '🔴 Offline' };

    const e = baseEmbed('🔄 Set Availability', PRIMARY);
    e.setDescription(
      `Your current status: **${statusMap[current] ?? current}**\n\nSelect your new availability status below.`
    );

    const view = new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId('avail_available').setLabel('🟢 Available').setStyle(ButtonStyle.Success),
      new ButtonBuilder().setCustomId('avail_busy').setLabel('🟡 Busy').setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId('avail_offline').setLabel('🔴 Offline').setStyle(ButtonStyle.Danger),
    );

    await interaction.reply({ embeds: [e], components: [view], ephemeral: true });
  },
};

// ── /review ───────────────────────────────────────────────────────────────────
const reviewCmd = {
  data: new SlashCommandBuilder()
    .setName('review')
    .setDescription('Submit a review for your completed order'),

  async execute(interaction) {
    if (!interaction.member.roles.cache.has('1484297795094581373') && !interaction.member.roles.cache.has('1479079737052762205')) {
      return interaction.reply({ content: '❌ You do not have the required role to use this command.', ephemeral: true });
    }
    const e = baseEmbed('⭐ Submit Your Vouch', GOLD);
    e.setDescription(
      'Select your **rating**, **payment method** and **service type**, then click **Continue** ' +
      'to fill in your feedback and proof.\n\nThank you for taking the time to vouch!'
    );

    // VouchSelectorView is initialized in interactions/vouches.js
    // We emit this interaction there via the custom_id prefix 'vouch_selector'
    const view = new ActionRowBuilder().addComponents(
      new ButtonBuilder()
        .setCustomId(`vouch_btn:ranked`)
        .setLabel('Submit a Vouch')
        .setStyle(ButtonStyle.Success)
        .setEmoji('⭐')
    );

    await interaction.reply({ embeds: [e], components: [view], ephemeral: true });
  },
};

module.exports = [availabilityCmd, reviewCmd];
