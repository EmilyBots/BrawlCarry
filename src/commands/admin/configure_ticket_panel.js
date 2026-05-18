const { SlashCommandBuilder, ModalBuilder, TextInputBuilder, TextInputStyle, ActionRowBuilder } = require('discord.js');
const { getConfig, setConfig } = require('../../db/index');

module.exports = {
  data: new SlashCommandBuilder()
    .setName('configure_ticket_panel')
    .setDescription('Customise the ticket panel title and description')
    .setDefaultMemberPermissions(0x8), // Administrator

  async execute(interaction) {
    const cfg = await getConfig(interaction.guildId);

    const modal = new ModalBuilder()
      .setCustomId('ticket_panel_setup_modal')
      .setTitle('Configure Ticket Panel');

    const titleInput = new TextInputBuilder()
      .setCustomId('panel_title')
      .setLabel('Panel Title')
      .setStyle(TextInputStyle.Short)
      .setMaxLength(100)
      .setRequired(false)
      .setPlaceholder('e.g. Support Center');

    const descInput = new TextInputBuilder()
      .setCustomId('panel_desc')
      .setLabel('Panel Description')
      .setStyle(TextInputStyle.Paragraph)
      .setMaxLength(1000)
      .setRequired(false)
      .setPlaceholder('e.g. Contact our team for support or applications.');

    if (cfg?.ticket_panel_title) titleInput.setValue(cfg.ticket_panel_title);
    if (cfg?.ticket_panel_desc)  descInput.setValue(cfg.ticket_panel_desc);

    modal.addComponents(
      new ActionRowBuilder().addComponents(titleInput),
      new ActionRowBuilder().addComponents(descInput),
    );

    await interaction.showModal(modal);
  },
};
