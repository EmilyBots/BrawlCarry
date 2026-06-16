const { SlashCommandBuilder, EmbedBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle,
        ContainerBuilder, TextDisplayBuilder, SeparatorBuilder, MediaGalleryBuilder, MessageFlags } = require('discord.js');
const { baseEmbed } = require('../../utils/embeds');
const { PRIMARY, ACCENT, SUCCESS, GOLD, FOOTER_BRAND } = require('../../config/constants');

const ADMIN_ROLE_ID = '1479079737052762205';
const guardAdmin = (i) => {
  if (i.member.roles.cache.has(ADMIN_ROLE_ID)) return false;
  i.reply({ content: '❌ You do not have the required role to use this command.', ephemeral: true });
  return true;
};

// ── Ranked panel ──────────────────────────────────────────────────────────────
const rankedPanelCmd = {
  data: new SlashCommandBuilder()
    .setName('ranked_panel')
    .setDescription('Post the Ranked Boost order panel in this channel')
    .setDefaultMemberPermissions(0x10) // ManageChannels
    .addStringOption(o => o.setName('image_url').setDescription('Image URLs separated by commas')),

  async execute(interaction) {
    if (guardAdmin(interaction)) return;
    const imageUrlRaw = interaction.options.getString('image_url');
    const imageUrls   = imageUrlRaw ? imageUrlRaw.split(',').map(u => u.trim()).filter(Boolean) : [];

    const container = new ContainerBuilder()
      .setAccentColor(PRIMARY)
      .addTextDisplayComponents(
        new TextDisplayBuilder()
          .setContent('## <:master:1491521740860428459> Ranked Service\n>>> ### <:arrow:1509857611816763482> **Reach higher ranks quickly and safely with our experienced players.**')
      );

    if (imageUrls.length > 0) {
  container
    .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
    .addMediaGalleryComponents(
      new MediaGalleryBuilder().addItems(imageUrls.map(url => ({ media: { url } })))
    );
}

    container
      .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
      .addActionRowComponents(
        new ActionRowBuilder().addComponents(
          new ButtonBuilder()
            .setCustomId('ranked_order_btn')
            .setLabel('Create Order')
            .setStyle(ButtonStyle.Danger)
            .setEmoji({ name: 'master', id: '1491521740860428459' })
        )
      );

    await interaction.channel.send({ components: [container], flags: MessageFlags.IsComponentsV2 });
    await interaction.reply({ content: '✅ Ranked panel posted.', ephemeral: true });
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
    if (guardAdmin(interaction)) return;
    const imageUrlRaw = interaction.options.getString('image_url');
    const imageUrls   = imageUrlRaw ? imageUrlRaw.split(',').map(u => u.trim()).filter(Boolean) : [];

    const container = new ContainerBuilder()
      .setAccentColor(ACCENT)
      .addTextDisplayComponents(
        new TextDisplayBuilder()
          .setContent('## <:RP3:1510915463146766407> Prestige Service\n>>> ### <:arrow:1509857611816763482> **Reach your desired Prestige quickly and safely with our experienced players.**')
      );

    if (imageUrls.length > 0) {
  container
    .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
    .addMediaGalleryComponents(
      new MediaGalleryBuilder().addItems(imageUrls.map(url => ({ media: { url } })))
    );
}

    container
      .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
      .addActionRowComponents(
        new ActionRowBuilder().addComponents(
          new ButtonBuilder()
            .setCustomId('prestige_order_btn')
            .setLabel('Create Order')
            .setStyle(ButtonStyle.Primary)
            .setEmoji({ name: 'RP3', id: '1510915463146766407' })
        )
      );

    await interaction.channel.send({ components: [container], flags: MessageFlags.IsComponentsV2 });
    await interaction.reply({ content: '✅ Prestige panel posted.', ephemeral: true });
  },
};

// ── Ranked Thread Channel info panel ─────────────────────────────────────────
const rankedThreadChannelCmd = {
  data: new SlashCommandBuilder()
    .setName('ranked_thread_panel')
    .setDescription('Post the Ranked Thread Channel info panel in this channel')
    .setDefaultMemberPermissions(0x10),

  async execute(interaction) {
    if (guardAdmin(interaction)) return;
    const BOT_LOGO = 'https://i.imgur.com/DvZCqcJ.png';
    const BANNER = 'https://i.imgur.com/ZOcB74G.jpeg';
    const e = new EmbedBuilder()
      .setColor(0x5865F2)
      .setDescription(
        '# <:reply:1507680110843658260> Ranked Thread Channel\n' +
        '### <:Boost:1508378809676861573> All private ranked tickets created by clients will appear under this channel <:master:1491521740860428459>'
      )
      .setThumbnail(BOT_LOGO);

    // NUOVO
    const banner = new EmbedBuilder()
      .setColor(0x5865F2)
      .setImage(BANNER);

    await interaction.channel.send({ embeds: [e, banner] });
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
    if (guardAdmin(interaction)) return;
    const BOT_LOGO = 'https://i.imgur.com/xpP93hM.png';
    const BANNER = 'https://i.imgur.com/ZOcB74G.jpeg';
    const e = new EmbedBuilder()
      .setColor(0x5865F2)
      .setDescription(
        '# <:reply:1507680110843658260> Prestige Thread Channel\n' +
        '### <:Boost:1508378809676861573> All private prestige tickets created by clients will appear under this channel <:P3:1508147370947252345>'
      )
      .setThumbnail(BOT_LOGO);

    // NUOVO
    const banner = new EmbedBuilder()
      .setColor(0x5865F2)
      .setImage(BANNER);

    await interaction.channel.send({ embeds: [e, banner] });
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
    if (guardAdmin(interaction)) return;
    const BOT_LOGO = 'https://i.imgur.com/eyDmzmo.gif';
    const BANNER = 'https://i.imgur.com/ZOcB74G.jpeg';
    const e = new EmbedBuilder()
      .setColor(0x5865F2)
      .setDescription(
        '# <:reply:1507680110843658260> Support Thread Channel\n' +
        '### <:Boost:1508378809676861573> All private support tickets created by members will appear under this channel <:info:1508767700329959545>'
      )
      .setThumbnail(BOT_LOGO);

    // NUOVO
    const banner = new EmbedBuilder()
      .setColor(0x5865F2)
      .setImage(BANNER);

    await interaction.channel.send({ embeds: [e, banner] });
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
    if (guardAdmin(interaction)) return;
    const BOT_LOGO = 'https://i.imgur.com/eyDmzmo.gif';
    const BANNER = 'https://i.imgur.com/ZOcB74G.jpeg';
    const e = new EmbedBuilder()
      .setColor(0x5865F2)
      .setDescription(
        '# <:reply:1507680110843658260> 4ccount Thread Channel\n' +
        '### <:Boost:1508378809676861573> All private 4ccount tickets created by clients will appear under this channel <:Amount:1501221154650853450>'
      )
      .setThumbnail(BOT_LOGO);

    // NUOVO
    const banner = new EmbedBuilder()
      .setColor(0x5865F2)
      .setImage(BANNER);

    await interaction.channel.send({ embeds: [e, banner] });
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
    if (guardAdmin(interaction)) return;
    const BOT_LOGO = 'https://i.imgur.com/eyDmzmo.gif';
    const BANNER = 'https://i.imgur.com/ZOcB74G.jpeg';
    const e = new EmbedBuilder()
      .setColor(0x5865F2)
      .setDescription(
        '# <:reply:1507680110843658260> Winstreak Thread Channel\n' +
        '### <:Boost:1508378809676861573> All private winstreak tickets created by clients will appear under this channel <:Winstreak:1508363674908102657>'
      )
      .setThumbnail(BOT_LOGO);

    // NUOVO
    const banner = new EmbedBuilder()
      .setColor(0x5865F2)
      .setImage(BANNER);

    await interaction.channel.send({ embeds: [e, banner] });
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
    if (guardAdmin(interaction)) return;
    const BOT_LOGO = 'https://i.imgur.com/eyDmzmo.gif';
    const BANNER = 'https://i.imgur.com/ZOcB74G.jpeg';
    const e = new EmbedBuilder()
      .setColor(0x5865F2)
      .setDescription(
        '# <:reply:1507680110843658260> Trophies Thread Channel\n' +
        '### <:Boost:1508378809676861573> All private trophies tickets created by clients will appear under this channel <:Trophies:1485658086156013598>'
      )
      .setThumbnail(BOT_LOGO);

    // NUOVO
    const banner = new EmbedBuilder()
      .setColor(0x5865F2)
      .setImage(BANNER);

    await interaction.channel.send({ embeds: [e, banner] });
    await interaction.reply({ content: '✅ Trophies Thread Channel panel posted.', ephemeral: true });
  },
};

// ── Application Thread Channel info panel ────────────────────────────────────
const applicationThreadChannelCmd = {
  data: new SlashCommandBuilder()
    .setName('application_thread_panel')
    .setDescription('Post the Application Thread Channel info panel in this channel')
    .setDefaultMemberPermissions(0x10),

  async execute(interaction) {
    if (guardAdmin(interaction)) return;
    const BOT_LOGO = 'https://i.imgur.com/eyDmzmo.gif';
    const BANNER = 'https://i.imgur.com/ZOcB74G.jpeg';
    const e = new EmbedBuilder()
      .setColor(0x5865F2)
      .setDescription(
        '# <:reply:1507680110843658260> Apply Thread Channel\n' +
        '### <:Boost:1508378809676861573> All private application tickets created by members will appear under this channel <:shield:1491489447445794866>'
      )
      .setThumbnail(BOT_LOGO);

    // NUOVO
    const banner = new EmbedBuilder()
      .setColor(0x5865F2)
      .setImage(BANNER);

    await interaction.channel.send({ embeds: [e, banner] });
    await interaction.reply({ content: '✅ Application Thread Channel panel posted.', ephemeral: true });
  },
};

// ── Winstreak panel ───────────────────────────────────────────────────────────
const winstreakPanelCmd = {
  data: new SlashCommandBuilder()
    .setName('winstreak_panel')
    .setDescription('Post the Winstreak order panel in this channel')
    .setDefaultMemberPermissions(0x10)
    .addStringOption(o => o.setName('image_url').setDescription('Image URLs separated by commas')),

  async execute(interaction) {
    if (guardAdmin(interaction)) return;
    const imageUrlRaw = interaction.options.getString('image_url');
    const imageUrls   = imageUrlRaw ? imageUrlRaw.split(',').map(u => u.trim()).filter(Boolean) : [];

    const container = new ContainerBuilder()
      .setAccentColor(SUCCESS)
      .addTextDisplayComponents(
        new TextDisplayBuilder()
          .setContent('## <:Winstreak:1508363674908102657> Winstreak Service\n>>> ### <:arrow:1509857611816763482> **Build your streak with trusted pro players.**')
      );

    if (imageUrls.length > 0) {
      container
        .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
        .addMediaGalleryComponents(
          new MediaGalleryBuilder().addItems(imageUrls.map(url => ({ media: { url } })))
        );
    }

    container
      .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
      .addActionRowComponents(
        new ActionRowBuilder().addComponents(
          new ButtonBuilder()
            .setCustomId('winstreak_order_btn')
            .setLabel('Create Order')
            .setStyle(ButtonStyle.Success)
            .setEmoji({ name: 'Winstreak', id: '1508363674908102657' })
        )
      );

    await interaction.channel.send({ components: [container], flags: MessageFlags.IsComponentsV2 });
    await interaction.reply({ content: '✅ Winstreak panel posted.', ephemeral: true });
  },
};

// ── Trophies panel ────────────────────────────────────────────────────────────
const trophiesPanelCmd = {
  data: new SlashCommandBuilder()
    .setName('trophies_panel')
    .setDescription('Post the Trophies order panel in this channel')
    .setDefaultMemberPermissions(0x10)
    .addStringOption(o => o.setName('image_url').setDescription('Image URLs separated by commas')),

  async execute(interaction) {
    if (guardAdmin(interaction)) return;
    const imageUrlRaw = interaction.options.getString('image_url');
    const imageUrls   = imageUrlRaw ? imageUrlRaw.split(',').map(u => u.trim()).filter(Boolean) : [];

    const container = new ContainerBuilder()
      .setAccentColor(GOLD)
      .addTextDisplayComponents(
        new TextDisplayBuilder()
          .setContent('## <:Trophies:1485658086156013598> Trophy Service\n>>> ### <:arrow:1509857611816763482> **Push your overall trophies with trusted pro players.**')
      );

    if (imageUrls.length > 0) {
      container
        .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
        .addMediaGalleryComponents(
          new MediaGalleryBuilder().addItems(imageUrls.map(url => ({ media: { url } })))
        );
    }

    container
      .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
      .addActionRowComponents(
        new ActionRowBuilder().addComponents(
          new ButtonBuilder()
            .setCustomId('trophies_order_btn')
            .setLabel('Create Order')
            .setStyle(ButtonStyle.Primary)
            .setEmoji({ name: 'Trophies', id: '1485658086156013598' })
        )
      );

    await interaction.channel.send({ components: [container], flags: MessageFlags.IsComponentsV2 });
    await interaction.reply({ content: '✅ Trophies panel posted.', ephemeral: true });
  },
};

module.exports = [rankedPanelCmd, prestigePanelCmd, winstreakPanelCmd, trophiesPanelCmd, rankedThreadChannelCmd, prestigeThreadChannelCmd, supportThreadChannelCmd, accountThreadChannelCmd, winstreakThreadChannelCmd, trophiesThreadChannelCmd, applicationThreadChannelCmd];
