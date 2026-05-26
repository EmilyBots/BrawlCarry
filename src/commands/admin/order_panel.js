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

    const BANNER = 'https://cdn.discordapp.com/attachments/1491058618735394896/1508759035216924724/51CB4E50-64FC-4009-992E-C322421DA723.png?ex=6a16b4d9&is=6a156359&hm=02fc8a8a01e77763ebede060edd082115790f78d47bbed6570c86ca67cee5ac5&';

    const e = new EmbedBuilder()
      .setColor(0x5865F2)
      .setDescription(
        '# <:reply:1507680110843658260> Ranked Thread Channel\n' +
        '### <:Boost:1508378809676861573> All private ranked tickets created by clients will appear under this channel <:master:1491521740860428459>'
      )
      .setThumbnail(BOT_LOGO);

    const banner = new EmbedBuilder()
      .setColor(0x5865F2)
      .setImage(BANNER)
      .setFooter({ text: FOOTER_BRAND, iconURL: BOT_LOGO });

    await interaction.channel.send({ embeds: [e] });
    await interaction.channel.send({ embeds: [banner] });
    await interaction.reply({ content: '✅ Ranked Thread Channel panel posted.', ephemeral: true });
  },
};

// ── Prestige Thread Channel info panel ───────────────────────────────────────
const prestigeThreadChannelCmd = {
  data: new SlashCommandBuilder()
    .setName('prestige_thread_panel')
    .setDescription('Post the Prestige Thread Channel info panel in this channel')
    .setDefaultMemberPermissions(0x10),

  async execute(interaction) {
    const BOT_LOGO = 'https://cdn.discordapp.com/attachments/1491058618735394896/1508757847242964992/C451729B-CE89-4480-9D02-A0D24BAB5556.png?ex=6a16b3be&is=6a15623e&hm=e426df4f9ccfc3e125f3ea4f4a7a72fbdcc89bc1dbf27ef97cfef747ffa6f3b7&';

    const BANNER = 'https://cdn.discordapp.com/attachments/1491058618735394896/1508759035216924724/51CB4E50-64FC-4009-992E-C322421DA723.png?ex=6a16b4d9&is=6a156359&hm=02fc8a8a01e77763ebede060edd082115790f78d47bbed6570c86ca67cee5ac5&';

    const e = new EmbedBuilder()
      .setColor(0x5865F2)
      .setDescription(
        '# <:reply:1507680110843658260> Prestige Thread Channel\n' +
        '### <:Boost:1508378809676861573> All private prestige tickets created by clients will appear under this channel <:P3:1508147370947252345>'
      )
      .setThumbnail(BOT_LOGO);

    const banner = new EmbedBuilder()
      .setColor(0x5865F2)
      .setImage(BANNER)
      .setFooter({ text: FOOTER_BRAND, iconURL: BOT_LOGO });

    await interaction.channel.send({ embeds: [e] });
    await interaction.channel.send({ embeds: [banner] });
    await interaction.reply({ content: '✅ Prestige Thread Channel panel posted.', ephemeral: true });
  },
};

// ── Support Thread Channel info panel ────────────────────────────────────────
const supportThreadChannelCmd = {
  data: new SlashCommandBuilder()
    .setName('support_thread_panel')
    .setDescription('Post the Support Thread Channel info panel in this channel')
    .setDefaultMemberPermissions(0x10),

  async execute(interaction) {
    const BOT_LOGO = 'https://cdn.discordapp.com/attachments/1491058618735394896/1508757847242964992/C451729B-CE89-4480-9D02-A0D24BAB5556.png?ex=6a16b3be&is=6a15623e&hm=e426df4f9ccfc3e125f3ea4f4a7a72fbdcc89bc1dbf27ef97cfef747ffa6f3b7&';

    const BANNER = 'https://cdn.discordapp.com/attachments/1491058618735394896/1508759035216924724/51CB4E50-64FC-4009-992E-C322421DA723.png?ex=6a16b4d9&is=6a156359&hm=02fc8a8a01e77763ebede060edd082115790f78d47bbed6570c86ca67cee5ac5&';

    const e = new EmbedBuilder()
      .setColor(0x5865F2)
      .setDescription(
        '# <:reply:1507680110843658260> Support Thread Channel\n' +
        '### <:Boost:1508378809676861573> All private support tickets created by members will appear under this channel <:info:1508767700329959545>'
      )
      .setThumbnail(BOT_LOGO);

    const banner = new EmbedBuilder()
      .setColor(0x5865F2)
      .setImage(BANNER)
      .setFooter({ text: FOOTER_BRAND, iconURL: BOT_LOGO });

    await interaction.channel.send({ embeds: [e] });
    await interaction.channel.send({ embeds: [banner] });
    await interaction.reply({ content: '✅ Support Thread Channel panel posted.', ephemeral: true });
  },
};

// ── 4ccount Thread Channel info panel ────────────────────────────────────────
const accountThreadChannelCmd = {
  data: new SlashCommandBuilder()
    .setName('account_thread_panel')
    .setDescription('Post the 4ccount Thread Channel info panel in this channel')
    .setDefaultMemberPermissions(0x10),

  async execute(interaction) {
    const BOT_LOGO = 'https://cdn.discordapp.com/attachments/1491058618735394896/1508757847242964992/C451729B-CE89-4480-9D02-A0D24BAB5556.png?ex=6a16b3be&is=6a15623e&hm=e426df4f9ccfc3e125f3ea4f4a7a72fbdcc89bc1dbf27ef97cfef747ffa6f3b7&';

    const BANNER = 'https://cdn.discordapp.com/attachments/1491058618735394896/1508759035216924724/51CB4E50-64FC-4009-992E-C322421DA723.png?ex=6a16b4d9&is=6a156359&hm=02fc8a8a01e77763ebede060edd082115790f78d47bbed6570c86ca67cee5ac5&';

    const e = new EmbedBuilder()
      .setColor(0x5865F2)
      .setDescription(
        '# <:reply:1507680110843658260> 4ccount Thread Channel\n' +
        '### <:Boost:1508378809676861573> All private 4ccount tickets created by clients will appear under this channel <:Amount:1501221154650853450>'
      )
      .setThumbnail(BOT_LOGO);

    const banner = new EmbedBuilder()
      .setColor(0x5865F2)
      .setImage(BANNER)
      .setFooter({ text: FOOTER_BRAND, iconURL: BOT_LOGO });

    await interaction.channel.send({ embeds: [e] });
    await interaction.channel.send({ embeds: [banner] });
    await interaction.reply({ content: '✅ 4ccount Thread Channel panel posted.', ephemeral: true });
  },
};

// ── Winstreak Thread Channel info panel ──────────────────────────────────────
const winstreakThreadChannelCmd = {
  data: new SlashCommandBuilder()
    .setName('winstreak_thread_panel')
    .setDescription('Post the Winstreak Thread Channel info panel in this channel')
    .setDefaultMemberPermissions(0x10),

  async execute(interaction) {
    const BOT_LOGO = 'https://cdn.discordapp.com/attachments/1491058618735394896/1508757847242964992/C451729B-CE89-4480-9D02-A0D24BAB5556.png?ex=6a16b3be&is=6a15623e&hm=e426df4f9ccfc3e125f3ea4f4a7a72fbdcc89bc1dbf27ef97cfef747ffa6f3b7&';

    const BANNER = 'https://cdn.discordapp.com/attachments/1491058618735394896/1508759035216924724/51CB4E50-64FC-4009-992E-C322421DA723.png?ex=6a16b4d9&is=6a156359&hm=02fc8a8a01e77763ebede060edd082115790f78d47bbed6570c86ca67cee5ac5&';

    const e = new EmbedBuilder()
      .setColor(0x5865F2)
      .setDescription(
        '# <:reply:1507680110843658260> Winstreak Thread Channel\n' +
        '### <:Boost:1508378809676861573> All private winstreak tickets created by clients will appear under this channel <:Winstreak:1508363674908102657>'
      )
      .setThumbnail(BOT_LOGO);

    const banner = new EmbedBuilder()
      .setColor(0x5865F2)
      .setImage(BANNER)
      .setFooter({ text: FOOTER_BRAND, iconURL: BOT_LOGO });

    await interaction.channel.send({ embeds: [e] });
    await interaction.channel.send({ embeds: [banner] });
    await interaction.reply({ content: '✅ Winstreak Thread Channel panel posted.', ephemeral: true });
  },
};

// ── Trophies Thread Channel info panel ───────────────────────────────────────
const trophiesThreadChannelCmd = {
  data: new SlashCommandBuilder()
    .setName('trophies_thread_panel')
    .setDescription('Post the Trophies Thread Channel info panel in this channel')
    .setDefaultMemberPermissions(0x10),

  async execute(interaction) {
    const BOT_LOGO = 'https://cdn.discordapp.com/attachments/1491058618735394896/1508757847242964992/C451729B-CE89-4480-9D02-A0D24BAB5556.png?ex=6a16b3be&is=6a15623e&hm=e426df4f9ccfc3e125f3ea4f4a7a72fbdcc89bc1dbf27ef97cfef747ffa6f3b7&';

    const BANNER = 'https://cdn.discordapp.com/attachments/1491058618735394896/1508759035216924724/51CB4E50-64FC-4009-992E-C322421DA723.png?ex=6a16b4d9&is=6a156359&hm=02fc8a8a01e77763ebede060edd082115790f78d47bbed6570c86ca67cee5ac5&';

    const e = new EmbedBuilder()
      .setColor(0x5865F2)
      .setDescription(
        '# <:reply:1507680110843658260> Trophies Thread Channel\n' +
        '### <:Boost:1508378809676861573> All private trophies tickets created by clients will appear under this channel <:Trophies:1485658086156013598>'
      )
      .setThumbnail(BOT_LOGO);

    const banner = new EmbedBuilder()
      .setColor(0x5865F2)
      .setImage(BANNER)
      .setFooter({ text: FOOTER_BRAND, iconURL: BOT_LOGO });

    await interaction.channel.send({ embeds: [e] });
    await interaction.channel.send({ embeds: [banner] });
    await interaction.reply({ content: '✅ Trophies Thread Channel panel posted.', ephemeral: true });
  },
};

module.exports = [rankedPanelCmd, prestigePanelCmd, rankedThreadChannelCmd, prestigeThreadChannelCmd, supportThreadChannelCmd, accountThreadChannelCmd, winstreakThreadChannelCmd, trophiesThreadChannelCmd];
