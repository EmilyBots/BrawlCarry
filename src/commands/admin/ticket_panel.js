const { SlashCommandBuilder, ActionRowBuilder, StringSelectMenuBuilder, StringSelectMenuOptionBuilder } = require('discord.js');
const { baseEmbed } = require('../../utils/embeds');
const { PRIMARY, GOLD, DARK, ACCENT } = require('../../config/constants');

module.exports = {
  data: new SlashCommandBuilder()
    .setName('ticket_panel')
    .setDescription('Post the combined support & application panel in this channel')
    .setDefaultMemberPermissions(0x10)
    .addStringOption(o =>
      o.setName('image_url').setDescription('Optional banner image URL')
    ),

  async execute(interaction) {
    const imageUrl = interaction.options.getString('image_url');

    // ── Main embed ────────────────────────────────────────────────────────────
    const embed = baseEmbed('<:Info:1501221322183934002> Support Center', ACCENT);

embed.setDescription('>>> Contact our team for support, applications, or server-related issues.');

if (imageUrl) embed.setImage(imageUrl);

    // ── Row 1 — Support center dropdown ──────────────────────────────────────
const row1 = new ActionRowBuilder().addComponents(
  new StringSelectMenuBuilder()
    .setCustomId('support_center_select_v1')
    .setPlaceholder('Select an option...')
    .addOptions(
      new StringSelectMenuOptionBuilder()
        .setLabel('General Support')
        .setValue('support')
        .setEmoji('🎫')
        .setDescription('Billing, order questions, or general help'),
      new StringSelectMenuOptionBuilder()
        .setLabel('Staff Applications')
        .setValue('apply')
        .setEmoji('📝')
        .setDescription('Apply to join the Brawl Carry™ team'),
      new StringSelectMenuOptionBuilder()
        .setLabel('Buy Our Services')
        .setValue('services')
        .setEmoji('<:rocket:1491490870979985438>')
        .setDescription('View our boosting and carry services'),
    )
);

await interaction.channel.send({ embeds: [embed], components: [row1] });
await interaction.reply({ content: '✅ Support Center panel posted.', ephemeral: true });
  },
};
