const {
  SlashCommandBuilder, ModalBuilder, TextInputBuilder, TextInputStyle, ActionRowBuilder, ChannelType,
} = require('discord.js');
const { queryOne } = require('../../db/index');
const { pendingCompletions } = require('../../interactions/orders');

module.exports = {
    data: new SlashCommandBuilder()
      .setName('order_complete')
    .setDescription('Mark an order as completed (run inside the ticket thread)')
    .setDefaultMemberPermissions(0x10), // ManageChannels

  async execute(interaction) {
    if (!interaction.member.roles.cache.has('1479079737052762205')) {
      return interaction.reply({ content: '❌ You do not have the required role to use this command.', ephemeral: true });
    }
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
    );

    pendingCompletions.set(interaction.user.id, order.id);
    await interaction.showModal(modal);
  },
};
