const { SlashCommandBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle } = require('discord.js');
const { baseEmbed } = require('../../utils/embeds');
const { GOLD } = require('../../config/constants');

module.exports = {
  data: new SlashCommandBuilder()
    .setName('vouch_panel')
    .setDescription('Send a vouch request panel to a user or post in this channel')
    .setDefaultMemberPermissions(0x10)
    .addUserOption(o => o.setName('user').setDescription('DM the vouch panel to this user'))
    .addStringOption(o => o.setName('order_kind').setDescription('ranked or prestige (default: ranked)')),

  async execute(interaction) {
    if (!interaction.member.roles.cache.has('1479079737052762205') && !interaction.member.roles.cache.has('1484297795094581373')) {
      return interaction.reply({ content: '❌ You do not have the required role to use this command.', ephemeral: true });
    }
    const user      = interaction.options.getUser('user');
    const orderKind = ['ranked', 'prestige'].includes(interaction.options.getString('order_kind')?.toLowerCase())
      ? interaction.options.getString('order_kind').toLowerCase()
      : 'ranked';

    const e = baseEmbed('⭐ Leave a Vouch', GOLD);
    e.setDescription(
      'Thank you for your order! We\'d love your feedback.\n\n' +
      '📸 Attach a screenshot as proof\n' +
      '⭐ Rate your experience (1-5)\n' +
      '💬 Leave honest feedback\n\n' +
      'Click the button below to submit.'
    );

    const view = new ActionRowBuilder().addComponents(
      new ButtonBuilder()
        .setCustomId(`vouch_btn:${orderKind}`)
        .setLabel('Submit a Vouch')
        .setStyle(ButtonStyle.Success)
        .setEmoji('⭐')
    );

    if (user) {
      try {
        await user.send({ embeds: [e], components: [view] });
        await interaction.reply({ content: `✅ Vouch panel sent to ${user}.`, ephemeral: true });
      } catch (_) {
        await interaction.reply({ content: '❌ Could not DM that user. They may have DMs disabled.', ephemeral: true });
      }
    } else {
      await interaction.channel.send({ embeds: [e], components: [view] });
      await interaction.reply({ content: '✅ Vouch panel posted.', ephemeral: true });
    }
  },
};
