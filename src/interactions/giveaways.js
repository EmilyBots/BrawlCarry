const { ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder } = require('discord.js');
const { queryOne } = require('../db/index');
const { baseEmbed } = require('../utils/embeds');
const { PRIMARY, ACCENT, FOOTER_BRAND } = require('../config/constants');

async function handleButton(interaction) {
  const id    = interaction.customId;
  const gaId  = id.split(':')[1];

  if (id.startsWith('ga_enter:'))  return handleEnter(interaction, gaId);
  if (id.startsWith('ga_view:'))   return handleViewParticipants(interaction, gaId);
  if (id.startsWith('ga_roles:'))  return handleViewRoles(interaction, gaId);
  if (id.startsWith('ga_pg:'))     return handlePagination(interaction);
}

async function handleEnter(interaction, gaId) {
  const ga = await queryOne('SELECT * FROM giveaways WHERE id = $1', [gaId]);
  if (!ga) return interaction.reply({ content: '❌ Giveaway not found.', ephemeral: true });

  const participants = JSON.parse(ga.participants || '[]');
  if (participants.includes(interaction.user.id)) {
    return interaction.reply({ content: '❌ You have already entered this giveaway.', ephemeral: true });
  }

  const extraEntriesData = JSON.parse(ga.extra_entries || '[]');
  const memberRoleIds    = new Set(interaction.member?.roles?.cache?.keys() ?? []);

  let totalEntries = 1;
  for (const entry of extraEntriesData) {
    if (memberRoleIds.has(entry.role_id)) totalEntries += entry.count;
  }

  for (let i = 0; i < totalEntries; i++) participants.push(interaction.user.id);

  await queryOne('UPDATE giveaways SET participants = $1 WHERE id = $2', [JSON.stringify(participants), gaId]);

  const bonusMsg = totalEntries > 1 ? ` You qualified for bonus roles and got **${totalEntries} entries** total! 🎉` : '';
  await interaction.reply({ content: `✅ You've entered! Good luck 🍀${bonusMsg}`, ephemeral: true });

async function handleViewParticipants(interaction, gaId) {
  const ga = await queryOne('SELECT * FROM giveaways WHERE id = $1', [gaId]);
  if (!ga) return interaction.reply({ content: '❌ Giveaway not found.', ephemeral: true });

  const allEntries = JSON.parse(ga.participants || '[]');
  if (!allEntries.length) {
    const e = baseEmbed('👥 Giveaway Participants', PRIMARY);
    e.setDescription('No one has entered yet.').setFooter({ text: FOOTER_BRAND });
    return interaction.reply({ embeds: [e], ephemeral: true });
  }

  const tally = {};
  for (const uid of allEntries) tally[uid] = (tally[uid] ?? 0) + 1;

  const lines = Object.entries(tally)
    .sort(([, a], [, b]) => b - a)
    .map(([uid, count], i) =>
      `\`${String(i + 1).padStart(2, '0')}.\` <@${uid}> — **${count}** entr${count !== 1 ? 'ies' : 'y'}`
    );

  const PAGE_SIZE = 15;
  const pages = [];
  for (let i = 0; i < lines.length; i += PAGE_SIZE) pages.push(lines.slice(i, i + PAGE_SIZE).join('\n'));

  const totalUnique  = Object.keys(tally).length;
  const totalEntries = allEntries.length;
  const footer       = `${totalUnique} participant${totalUnique !== 1 ? 's' : ''} · ${totalEntries} total entr${totalEntries !== 1 ? 'ies' : 'y'} · ${FOOTER_BRAND}`;

  const embed = new EmbedBuilder()
    .setColor(PRIMARY)
    .setTitle('👥 Giveaway Participants')
    .setDescription(pages[0])
    .setFooter({ text: pages.length > 1 ? `Page 1/${pages.length} · ${footer}` : footer });

  if (pages.length === 1) return interaction.reply({ embeds: [embed], ephemeral: true });

  const row = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`ga_pg:${gaId}:0`).setLabel('← Prev').setStyle(ButtonStyle.Secondary).setDisabled(true),
    new ButtonBuilder().setCustomId(`ga_pg:${gaId}:1`).setLabel('Next →').setStyle(ButtonStyle.Secondary),
  );
  return interaction.reply({ embeds: [embed], components: [row], ephemeral: true });
}

async function handleViewRoles(interaction, gaId) {
  const ga               = await queryOne('SELECT extra_entries FROM giveaways WHERE id = $1', [gaId]);
  const extraEntriesData = JSON.parse(ga?.extra_entries || '[]');
  const e                = baseEmbed('🎁 Bonus Entry Roles', ACCENT);

  if (!extraEntriesData.length) {
    e.setDescription('No bonus roles configured for this giveaway.\nEveryone gets **1 entry**.');
  } else {
    const lines = ['**Base:** 1 entry (everyone)\n', ...extraEntriesData.map(ed => `<@&${ed.role_id}> → **+${ed.count} extra entries**`), '\n*Bonuses stack! Having multiple roles gives you all their extra entries combined.*'];
    e.setDescription(lines.join('\n'));
  }

  await interaction.reply({ embeds: [e], ephemeral: true });
}

async function handlePagination(interaction) {
  const [, pgGaId, rawPage] = interaction.customId.split(':');
  const page = Number(rawPage);

  const ga         = await queryOne('SELECT * FROM giveaways WHERE id = $1', [pgGaId]);
  const allEntries = JSON.parse(ga.participants || '[]');
  const tally      = {};
  for (const uid of allEntries) tally[uid] = (tally[uid] ?? 0) + 1;

  const lines = Object.entries(tally)
    .sort(([, a], [, b]) => b - a)
    .map(([uid, count], i) =>
      `\`${String(i + 1).padStart(2, '0')}.\` <@${uid}> — **${count}** entr${count !== 1 ? 'ies' : 'y'}`
    );

  const PAGE_SIZE = 15;
  const pages = [];
  for (let i = 0; i < lines.length; i += PAGE_SIZE) pages.push(lines.slice(i, i + PAGE_SIZE).join('\n'));

  const totalUnique  = Object.keys(tally).length;
  const totalEntries = allEntries.length;

  const embed = new EmbedBuilder()
    .setColor(PRIMARY)
    .setTitle('👥 Giveaway Participants')
    .setDescription(pages[page])
    .setFooter({ text: `Page ${page + 1}/${pages.length} · ${totalUnique} participant${totalUnique !== 1 ? 's' : ''} · ${totalEntries} total entr${totalEntries !== 1 ? 'ies' : 'y'} · ${FOOTER_BRAND}` });

  const row = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`ga_pg:${pgGaId}:${page - 1}`).setLabel('← Prev').setStyle(ButtonStyle.Secondary).setDisabled(page === 0),
    new ButtonBuilder().setCustomId(`ga_pg:${pgGaId}:${page + 1}`).setLabel('Next →').setStyle(ButtonStyle.Secondary).setDisabled(page === pages.length - 1),
  );
  return interaction.update({ embeds: [embed], components: [row] });
}

module.exports = { handleButton };
