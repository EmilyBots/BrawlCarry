const {
  SlashCommandBuilder, ModalBuilder, TextInputBuilder, TextInputStyle, ActionRowBuilder, ChannelType,
} = require('discord.js');
const { queryOne } = require('../../db/index');

const { debugWatermarkDiag } = require('../utils/watermark'); // aggiusta se watermark.js è altrove

module.exports = [
  {
    data: new SlashCommandBuilder()
      .setName('order_complete')
    .setDescription('Mark an order as completed (run inside the ticket thread)')
    .setDefaultMemberPermissions(0x10), // ManageChannels

  async execute(interaction) {
    const channel = interaction.channel;

    if (channel.type !== ChannelType.PublicThread && channel.type !== ChannelType.PrivateThread) {
      return interaction.reply({ content: '❌ This command must be used **inside a ticket thread**.', ephemeral: true });
    }

    const order = await queryOne(
      'SELECT * FROM orders WHERE ticket_channel_id = $1 ORDER BY created_at DESC LIMIT 1',
      [channel.id]
    );

    if (!order) return interaction.reply({ content: '❌ No order is linked to this ticket thread.', ephemeral: true });
    if (order.status === 'completed') return interaction.reply({ content: `❌ Order \`${order.id}\` is already marked as completed.`, ephemeral: true });

    const modal = new ModalBuilder()
      .setCustomId('order_complete_modal')
      .setTitle('Complete Order')
      .addComponents(
        new ActionRowBuilder().addComponents(
          new TextInputBuilder()
            .setCustomId('order_id')
            .setLabel('Order ID')
            .setStyle(TextInputStyle.Short)
            .setValue(order.id)
            .setRequired(true)
        ),
        new ActionRowBuilder().addComponents(
          new TextInputBuilder()
            .setCustomId('final_price')
            .setLabel('Final Price (EUR)')
            .setStyle(TextInputStyle.Short)
            .setPlaceholder('e.g. 25.00')
            .setRequired(true)
        ),
        new ActionRowBuilder().addComponents(
      new TextInputBuilder()
        .setCustomId('proof_image')
        .setLabel('Proof Image URL (optional)')
        .setStyle(TextInputStyle.Short)
        .setPlaceholder('https://i.imgur.com/...')
        .setRequired(false)
    ),
    new ActionRowBuilder().addComponents(
      new TextInputBuilder()
        .setCustomId('apply_watermark')
        .setLabel('Apply Watermark? (yes / no)')
        .setStyle(TextInputStyle.Short)
        .setValue('yes')
        .setRequired(true)
    ),
  )
  );

    await interaction.showModal(modal);
  },
},
{
    data: new SlashCommandBuilder()
      .setName('watermark_diag')
      .setDescription('Debug watermark font rendering')
      .setDefaultMemberPermissions(0x8),

    async execute(interaction) {
      await interaction.deferReply({ ephemeral: true });
      const diag = await debugWatermarkDiag();
      await interaction.editReply({ files: [diag] });
    },
  },
];
