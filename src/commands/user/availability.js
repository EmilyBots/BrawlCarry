const { SlashCommandBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle } = require('discord.js');
const { baseEmbed } = require('../../utils/embeds');
const { GOLD } = require('../../config/constants');
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

module.exports = [reviewCmd];
