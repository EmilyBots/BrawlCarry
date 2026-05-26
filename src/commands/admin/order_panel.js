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
        .setStyle(ButtonStyle.Danger)
        .setEmoji({ name: 'master', id: '1491521740860428459' })
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
        .setStyle(ButtonStyle.Primary)
        .setEmoji({ name: 'copyright', id: '1485657838897467534' })
    );

    await interaction.channel.send({ embeds: [e, ...extraEmbeds], components: [view] });
    await interaction.reply({ content: '✅ Prestige Boost panel posted.', ephemeral: true });
  },
};

// ── Ranked Thread Channel info panel ─────────────────────────────────────────
const rankedThreadChannelCmd = {
  data: new SlashCommandBuilder()
    .setName('ranked_thread_panel')
    .setDescription('Post the Ranked Thread Channel info panel in this channel')
    .setDefaultMemberPermissions(0x10),

  async execute(interaction) {
    const BOT_LOGO = 'https://cdn.discordapp.com/attachments/1491058618735394896/1508757847242964992/C451729B-CE89-4480-9D02-A0D24BAB5556.png?ex=6a16b3be&is=6a15623e&hm=e426df4f9ccfc3e125f3ea4f4a7a72fbdcc89bc1dbf27ef97cfef747ffa6f3b7&';

    const e = new EmbedBuilder()
      .setColor(0x5865F2)
      .setTitle('<:reply:1507680110843658260> Ranked Thread Channel')
      .setDescription(
        '### <:Boost:1508378809676861573> All private ranked tickets created by clients will appear under this channel. <:Matcherino:1479152020312293650>'
      )
      .setThumbnail(BOT_LOGO)
      .setFooter({ text: FOOTER_BRAND, iconURL: BOT_LOGO });

    await interaction.channel.send({ embeds: [e] });
    await interaction.reply({ content: '✅ Ranked Thread Channel panel posted.', ephemeral: true });
  },
};

module.exports = [rankedPanelCmd, prestigePanelCmd, rankedThreadChannelCmd];
