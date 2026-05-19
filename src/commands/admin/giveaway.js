const { SlashCommandBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder } = require('discord.js');
const { queryOne, queryAll } = require('../../db/index');
const { baseEmbed } = require('../../utils/embeds');
const { PRIMARY, SUCCESS, FOOTER_BRAND } = require('../../config/constants');
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
      .addStringOption(o => o.setName('description').setDescription('Giveaway description or rules').setRequired(true))
      .addStringOption(o => o.setName('ping').setDescription('Who to ping: @everyone, @here, a role mention, or none'))
      .addStringOption(o => o.setName('image_url').setDescription('Optional banner image URL'));

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
    const ping        = interaction.options.getString('ping') ?? '@everyone';
    const imageUrl    = interaction.options.getString('image_url');

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
        (id, prize, description, winners, hosted_by, participants, winner_ids, image_url, extra_entries, ping, ended_at, channel_id)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)`,
      [gaId, prize, description, winners, interaction.user.id, '[]', null, imageUrl,
       extraEntriesData.length ? JSON.stringify(extraEntriesData) : null,
       ping, endsAt, interaction.channelId]
    );

    const endTs = Math.floor(endsAt.getTime() / 1000);
    const statsLines = [
  `<:diamound:1491491246546616340> **${winners}** winner${winners !== 1 ? 's' : ''}`,
  `<:user:1491499694734708815> **0** entries`,
  `⏰ Ends <t:${endTs}:R>`,
];

if (extraEntriesData.length) {
  statsLines.push('');
  statsLines.push('<:rocket:1491490870979985438> **Bonus Roles**');
  extraEntriesData.forEach(ed => statsLines.push(`<@&${ed.role_id}> — **+${ed.count}** entries`));
}

statsLines.push(`\n↳ <:rocket:1491490870979985438> Hosted by ${interaction.user}`);

const e = new EmbedBuilder()
  .setColor(PRIMARY)
  .setTitle(`<:gift:1491499820379275366>  ${prize}`)
  .setDescription(`> **<:Info:1501221322183934002> ${description}**\n\n` + statsLines.join('\n'))
  .setFooter({ text: FOOTER_BRAND });

if (imageUrl) e.setImage(imageUrl);


const view = new ActionRowBuilder().addComponents(
  new ButtonBuilder().setCustomId(`ga_enter:${gaId}`).setLabel('Enter').setStyle(ButtonStyle.Success).setEmoji('🎉'),
  new ButtonBuilder().setCustomId(`ga_view:${gaId}`).setLabel('Participants').setStyle(ButtonStyle.Primary).setEmoji({ name: 'user', id: '1491499694734708815' }),
  new ButtonBuilder().setCustomId(`ga_roles:${gaId}`).setLabel('Bonus Roles').setStyle(ButtonStyle.Secondary).setEmoji({ name: 'gift', id: '1491499820379275366' }),
);

    const pingContent = ping?.toLowerCase() !== 'none'
  ? `<a:giveaway:1506218898255773827> ${ping} **NEW GIVEAWAY** <a:giveaway:1506218898255773827>`
  : `<a:giveaway:1506218898255773827> **NEW GIVEAWAY** <a:giveaway:1506218898255773827>`;

    await interaction.channel.send({
      content: pingContent,
      embeds: [e],
      components: [view],
      allowedMentions: { parse: ['everyone', 'roles'] },
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

const e = new EmbedBuilder()
  .setColor(PRIMARY)
  .setTitle(`<:gift:1491499820379275366>  ${prize}`)
  .setDescription(`<:Info:1501221322183934002>  ${description}`)
  .addFields(
    { name: '<:diamound:1491491246546616340>  Winners',  value: `**${winners}** winner${winners !== 1 ? 's' : ''}`, inline: true },
    { name: '<:user:1491499694734708815>  Entries',      value: '**0**',                                            inline: true },
    { name: '⏰  Ends',                                  value: `<t:${endTs}:R>`,                                   inline: true },
  );

if (extraEntriesData.length) {
  e.addFields({
    name: '<:rocket:1491490870979985438>  Bonus Roles',
    value: extraEntriesData.map(ed => `<@&${ed.role_id}> — **+${ed.count}** entries`).join('\n'),
  });
}

e.addFields({ name: '<:rocket:1491490870979985438>  Hosted by', value: `${interaction.user}` })
 .setFooter({ text: FOOTER_BRAND });

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
