const { SlashCommandBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder } = require('discord.js');
const { queryOne, queryAll } = require('../../db/index');
const { baseEmbed } = require('../../utils/embeds');
const { PRIMARY, SUCCESS } = require('../../config/constants');
const { v4: uuidv4 } = require('uuid');

// ── /giveaway ─────────────────────────────────────────────────────────────────
const giveawayCmd = {
  data: (() => {
    const cmd = new SlashCommandBuilder()
      .setName('giveaway')
      .setDescription('Start a new giveaway')
      .setDefaultMemberPermissions(0x10)
      .addStringOption(o => o.setName('prize').setDescription('Prize name').setRequired(true))
      .addIntegerOption(o => o.setName('hours').setDescription('Duration in hours').setRequired(true).setMinValue(1))
      .addIntegerOption(o => o.setName('winners').setDescription('Number of winners').setRequired(true).setMinValue(1))
      .addStringOption(o => o.setName('description').setDescription('Giveaway description or rules').setRequired(true));

    for (let i = 1; i <= 8; i++) {
      cmd
        .addRoleOption(o => o.setName(`role_${i}`).setDescription(`Bonus role ${i}`))
        .addIntegerOption(o => o.setName(`entries_${i}`).setDescription(`Extra entries for role ${i}`).setMinValue(1));
    }

    return cmd;
  })(),

  async execute(interaction) {
    const prize       = interaction.options.getString('prize');
    const hours       = interaction.options.getInteger('hours');
    const winners     = interaction.options.getInteger('winners');
    const description = interaction.options.getString('description');
    
    

    const extraEntriesData = [];
    for (let i = 1; i <= 8; i++) {
      const role    = interaction.options.getRole(`role_${i}`);
      const entries = interaction.options.getInteger(`entries_${i}`) ?? 1;
      if (role) extraEntriesData.push({ role_id: role.id, count: Math.max(1, entries) });
    }

    const gaId   = `G${uuidv4().replace(/-/g, '').slice(0, 8).toUpperCase()}`;
    const endsAt = new Date(Date.now() + hours * 3600_000);

    await queryOne(
      `INSERT INTO giveaways
        (id, prize, description, winners, hosted_by, participants, winner_ids, image_url, extra_entries, ended_at, channel_id)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)`,
      [gaId, prize, description, winners, interaction.user.id, '[]', null, null,
       extraEntriesData.length ? JSON.stringify(extraEntriesData) : null,
       endsAt, interaction.channelId]
    );

    const endTs = Math.floor(endsAt.getTime() / 1000);
    // NUOVO
const statsLines = [
  `### <:vip:1508831641135612068> **${winners}** ${winners !== 1 ? 'Winners' : 'Winner'}`,
  `### <:user:1508831475796148285> **0** Participants`,
  `### ⏰ Ends <t:${endTs}:R>`,
];

statsLines.push(`\n### <:arrow:1509857611816763482> <:Boost:1508378809676861573> Hosted by ${interaction.user}`);

const e = new EmbedBuilder()
  .setColor(PRIMARY)
  .setTitle(`<:Gift:1509855137156567130>  ${prize}`)
  .setDescription(`# > <:info:1508767700329959545> ${description}\n\n` + statsLines.join('\n'));


const view = new ActionRowBuilder().addComponents(
  new ButtonBuilder().setCustomId(`ga_enter:${gaId}`).setLabel('Enter Giveaway').setStyle(ButtonStyle.Success).setEmoji({ name: 'giveaway', id: '1506218898255773827', animated: true }),
  new ButtonBuilder().setCustomId(`ga_view:${gaId}`).setLabel('Participants List').setStyle(ButtonStyle.Primary).setEmoji({ name: 'user', id: '1508831475796148285' }),
  new ButtonBuilder().setCustomId(`ga_roles:${gaId}`).setLabel('Extra Entries').setStyle(ButtonStyle.Secondary).setEmoji({ name: 'Gift', id: '1509855137156567130' }),
);

    

    await interaction.channel.send({
      content: '<a:giveaway:1506218898255773827> @everyone NEW GIVEAWAY <a:giveaway:1506218898255773827>',
      embeds: [e],
      components: [view],
      allowedMentions: { parse: ['everyone'] },
    });
    await interaction.reply({ content: `✅ Giveaway started! ID: \`${gaId}\``, ephemeral: true });
  },
};

// ── /end_giveaway ─────────────────────────────────────────────────────────────
const endGiveawayCmd = {
  data: new SlashCommandBuilder()
    .setName('end_giveaway')
    .setDescription('End a giveaway and pick winners')
    .setDefaultMemberPermissions(0x10)
    .addStringOption(o => o.setName('giveaway_id').setDescription('Giveaway ID (shown in embed footer)').setRequired(true)),

  async execute(interaction) {
    const gaId = interaction.options.getString('giveaway_id');
    const ga   = await queryOne('SELECT * FROM giveaways WHERE id = $1', [gaId]);

    if (!ga) return interaction.reply({ content: '❌ Giveaway not found.', ephemeral: true });

    const participants = JSON.parse(ga.participants || '[]');
    if (!participants.length) return interaction.reply({ content: '❌ No participants to draw from.', ephemeral: true });

    const unique     = [...new Set(participants)];
    const winnerIds  = unique.sort(() => 0.5 - Math.random()).slice(0, ga.winners);

    await queryOne('UPDATE giveaways SET winner_ids = $1 WHERE id = $2', [JSON.stringify(winnerIds), gaId]);

    const winnerMentions = winnerIds.map(w => `<@${w}>`).join(' ');
const endedAt = Math.floor(Date.now() / 1000);

// NUOVO
const e = new EmbedBuilder()
  .setColor(PRIMARY)
  .setTitle(`<:Gift:1509855137156567130>  ${prize}`)
  .setDescription(`# <:info:1508767700329959545> ${description}`)
  .addFields(
    { name: '### <:vip:1508831641135612068>  Winners',  value: `**${winners}** winner${winners !== 1 ? 's' : ''}`, inline: true },
    { name: '### <:user:1508831475796148285>  Entries', value: '**0**',                                            inline: true },
    { name: '⏰  Ends',                             value: `<t:${endTs}:R>`,                                   inline: true },
  );

e.addFields({ name: '<:arrow:1509857611816763482> <:Boost:1508378809676861573>  Hosted by', value: `${interaction.user}` });

if (imageUrl) e.setImage(imageUrl);

await interaction.channel.send({
  content: `<a:giveaway:1506218898255773827> Congratulations ${winnerMentions}! You won **${ga.prize}**!`,
  embeds: [e],
  allowedMentions: { users: winnerIds },
});

    await interaction.reply({ content: '✅ Giveaway ended.', ephemeral: true });
  },
};

module.exports = [giveawayCmd, endGiveawayCmd];
