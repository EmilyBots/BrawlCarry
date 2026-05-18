const { SlashCommandBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle } = require('discord.js');
const { baseEmbed } = require('../../utils/embeds');
const { PRIMARY } = require('../../config/constants');

module.exports = {
  data: new SlashCommandBuilder()
    .setName('ticket_panel')
    .setDescription('Post the combined support & application panel in this channel')
    .setDefaultMemberPermissions(0x10)
    .addStringOption(o => o.setName('image_url').setDescription('Optional banner image URL')),

  async execute(interaction) {
    const imageUrl = interaction.options.getString('image_url');

    const e = baseEmbed('<:Info:1501221322183934002> Support Center', PRIMARY);
    e.setDescription('>>> Contact our team for support, applications, or server-related issues.');
    if (imageUrl) e.setImage(imageUrl);

    const view = new ActionRowBuilder().addComponents(
      new ButtonBuilder()
        .setCustomId('ticket_general_btn')
        .setLabel('General Support')
        .setStyle(ButtonStyle.Primary)
        .setEmoji('ℹ️'),
      new ButtonBuilder()
        .setCustomId('application_btn')
        .setLabel('Apply')
        .setStyle(ButtonStyle.Secondary)
        .setEmoji('📝'),
    );

    await interaction.channel.send({ embeds: [e], components: [view] });
    await interaction.reply({ content: '✅ Support Center panel posted.', ephemeral: true });
  },
};
