const { SlashCommandBuilder, EmbedBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle } = require('discord.js');
const { baseEmbed } = require('../../utils/embeds');
const { PRIMARY, ACCENT, FOOTER_BRAND } = require('../../config/constants');

// ── Ranked panel ──────────────────────────────────────────────────────────────
const rankedPanelCmd = {
  data: new SlashCommandBuilder()
    .setName('ranked_panel')
    .setDescription('Post the Ranked Boost order panel in this channel')
    .setDefaultMemberPermissions(0x10) // ManageChannels
    .addStringOption(o => o.setName('image_url').setDescription('Image URLs separated by commas')),

  async execute(interaction) {
    const imageUrlRaw = interaction.options.getString('image_url');
    const imageUrls   = imageUrlRaw ? imageUrlRaw.split(',').map(u => u.trim()).filter(Boolean) : [];

    const e = baseEmbed('<:master:1491521740860428459> Ranked Service', PRIMARY);
    e.setDescription('>>> **Climb the Ranked leaderboard quickly and safely with our experienced boosters.**\n\n⚡ Fast • 🔒 Secure • ⭐ Trusted');
    if (imageUrls[0]) e.setImage(imageUrls[0]);

    const extraEmbeds = imageUrls.slice(1).map(url =>
      new EmbedBuilder().setColor(PRIMARY).setImage(url).setFooter({ text: FOOTER_BRAND })
    );

    const view = new ActionRowBuilder().addComponents(
      new ButtonBuilder()
        .setCustomId('ranked_order_btn')
        .setLabel('Ranked Order')
.setStyle(ButtonStyle.Primary)
        .setEmoji({ name: 'masters', id: '1506001723657945262' })
    );

    await interaction.channel.send({ embeds: [e, ...extraEmbeds], components: [view] });
    await interaction.reply({ content: '✅ Ranked Boost panel posted.', ephemeral: true });
  },
};

// ── Prestige panel ────────────────────────────────────────────────────────────
const prestigePanelCmd = {
  data: new SlashCommandBuilder()
    .setName('prestige_panel')
    .setDescription('Post the Prestige Boost order panel in this channel')
    .setDefaultMemberPermissions(0x10)
    .addStringOption(o => o.setName('image_url').setDescription('Image URLs separated by commas')),

  async execute(interaction) {
    const imageUrlRaw = interaction.options.getString('image_url');
    const imageUrls   = imageUrlRaw ? imageUrlRaw.split(',').map(u => u.trim()).filter(Boolean) : [];

    const e = baseEmbed('<:copyright:1485657838897467534> Prestige Service', ACCENT);
    e.setDescription('>>> **Reach your desired Prestige quickly and safely with our experienced boosters.**\n\n⚡ Fast • 🔒 Secure • ⭐ Trusted');
    if (imageUrls[0]) e.setImage(imageUrls[0]);

    const extraEmbeds = imageUrls.slice(1).map(url =>
      new EmbedBuilder().setColor(ACCENT).setImage(url).setFooter({ text: FOOTER_BRAND })
    );

    const view = new ActionRowBuilder().addComponents(
      new ButtonBuilder()
        .setCustomId('prestige_order_btn')
        .setLabel('Prestige Order')
.setStyle(ButtonStyle.Secondary)
        .setEmoji({ name: 'copyright', id: '1505997750620131408' })
    );

    await interaction.channel.send({ embeds: [e, ...extraEmbeds], components: [view] });
    await interaction.reply({ content: '✅ Prestige Boost panel posted.', ephemeral: true });
  },
};

module.exports = [rankedPanelCmd, prestigePanelCmd];
