const { SlashCommandBuilder, ActionRowBuilder, StringSelectMenuBuilder, StringSelectMenuOptionBuilder, ContainerBuilder, TextDisplayBuilder, SeparatorBuilder, MediaGalleryBuilder, MessageFlags } = require('discord.js');
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
    if (!interaction.member.roles.cache.has('1479079737052762205')) {
      return interaction.reply({ content: '❌ You do not have the required role to use this command.', ephemeral: true });
    }
    const imageUrl = interaction.options.getString('image_url');

    const row1 = new ActionRowBuilder().addComponents(
      new StringSelectMenuBuilder()
        .setCustomId('support_center_select_v1')
        .setPlaceholder('Select an option...')
        .addOptions(
          new StringSelectMenuOptionBuilder()
            .setLabel('General Support')
            .setValue('support')
            .setEmoji({ name: 'ticket', id: '1508838977602457723' })
            .setDescription('Open a ticket with our support team'),
          new StringSelectMenuOptionBuilder()
            .setLabel('Staff Applications')
            .setValue('apply')
            .setEmoji({ name: 'staff2', id: '1508838600463351868' })
            .setDescription('Apply for a staff or b00ster role'),
          new StringSelectMenuOptionBuilder()
            .setLabel('Buy Our Services')
            .setValue('services')
            .setEmoji({ name: 'booster', id: '1508831601600106547' })
            .setDescription('View our available services'),
        )
    );

    const container = new ContainerBuilder()
      .setAccentColor(ACCENT)
      .addTextDisplayComponents(
        new TextDisplayBuilder()
          .setContent('## <:info:1508767700329959545> Support Center\n>>> Contact our team for support, applications, or server-related issues.')
      );

    if (imageUrl) {
      container
        .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
        .addMediaGalleryComponents(
          new MediaGalleryBuilder().addItems([{ media: { url: imageUrl } }])
        );
    }

    container
      .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
      .addActionRowComponents(row1);

    await interaction.channel.send({ components: [container], flags: MessageFlags.IsComponentsV2 });
    await interaction.reply({ content: '✅ Support Center panel posted.', ephemeral: true });
  },
};
