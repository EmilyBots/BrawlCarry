const { SlashCommandBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle } = require('discord.js');
const { baseEmbed } = require('../../utils/embeds');
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
    const imageUrl = interaction.options.getString('image_url');

    // ── Main embed ────────────────────────────────────────────────────────────
    const embed = baseEmbed('', ACCENT);

    embed
      .setAuthor({
        name: 'Brawl Carry™  •  Support Center',
        iconURL: interaction.guild.iconURL({ dynamic: true }),
      })
      .setDescription(
        [
          '## <:Info:1501221322183934002> Welcome to Support',
          '',
          'Our team is here to help you with anything you need.',
          'Choose the appropriate category below to open a ticket.',
          '',
          '──────────────────────────────',
          '',
          '**<:Support:1> 🎫  General Support**',
          '> Billing issues, order questions, account help,',
          '> or anything else — we\'ve got you covered.',
          '',
          '**📋  Boost Order**',
          '> Ready to rank up? Open a ticket to place',
          '> a new boosting order with our team.',
          '',
          '**📝  Staff Application**',
          '> Interested in joining the Brawl Carry™ team?',
          '> Apply here and a manager will review your request.',
          '',
          '──────────────────────────────',
          '*Average response time: **< 5 minutes***',
        ].join('\n')
      )
      .setFooter({ text: 'Brawl Carry™  •  Tickets are logged and monitored' })
      .setTimestamp();

    if (imageUrl) embed.setImage(imageUrl);

    // ── Row 1 — Primary actions ───────────────────────────────────────────────
    const row1 = new ActionRowBuilder().addComponents(
      new ButtonBuilder()
        .setCustomId('ticket_general_btn')
        .setLabel('General Support')
        .setStyle(ButtonStyle.Primary)
        .setEmoji('🎫'),
      new ButtonBuilder()
        .setCustomId('ticket_order_btn')
        .setLabel('Boost Order')
        .setStyle(ButtonStyle.Success)
        .setEmoji('⚡'),
      new ButtonBuilder()
        .setCustomId('application_btn')
        .setLabel('Apply for Staff')
        .setStyle(ButtonStyle.Secondary)
        .setEmoji('📝'),
    );

    await interaction.channel.send({ embeds: [embed], components: [row1] });
    await interaction.reply({ content: '✅ Support Center panel posted.', ephemeral: true });
  },
};