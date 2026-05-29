const { ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder } = require('discord.js');
const { queryOne } = require('../db/index');
const { baseEmbed } = require('../utils/embeds');
const { PRIMARY, ACCENT } = require('../config/constants');

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
  const userId       = interaction.user.id;
  const endTs        = Math.floor(new Date(ga.ended_at).getTime() / 1000);

  // ── Funzione helper per rebuild embed ────────────────────────────────────
  const buildEmbed = (list) => {
    const uniqueCount = new Set(list).size;
    const lines = [
      `### <:vip:1508831641135612068> **${ga.winners}** ${ga.winners !== 1 ? 'Winners' : 'Winner'}`,
      `### <:user:1508831475796148285> **${uniqueCount}** ${uniqueCount !== 1 ? 'Participants' : 'Participant'}`,
      `### ⏰ Ends <t:${endTs}:R>`,
    ];
    lines.push(`\n### <:arrow:1509857611816763482> <:Boost:1508378809676861573> Hosted by <@${ga.hosted_by}>`);
    const embed = new EmbedBuilder()
      .setColor(PRIMARY)
      .setTitle(`<:Gift:1509855137156567130>  ${ga.prize}`)
      .setDescription(`# > <:info:1508767700329959545> ${ga.description}\n\n` + lines.join('\n'));
    return embed;
  };

  // ── LEAVE ─────────────────────────────────────────────────────────────────
  if (participants.includes(userId)) {
    const updated = participants.filter(id => id !== userId); // rimuove tutte le entries (incluse bonus)

    await queryOne('UPDATE giveaways SET participants = $1 WHERE id = $2', [JSON.stringify(updated), gaId]);
    await interaction.message.edit({ embeds: [buildEmbed(updated)] }).catch(() => {});

    return interaction.reply({
      content: `<:sold:1507693147306852515> Successfully left the giveaway.\n\n<:user:1508831475796148285> Your entries have been removed.`,
      ephemeral: true,
    });
  }

  // ── JOIN ──────────────────────────────────────────────────────────────────
  const extraEntriesData = JSON.parse(ga.extra_entries || '[]');
  const memberRoleIds    = new Set(interaction.member?.roles?.cache?.keys() ?? []);

  let totalEntries = 1;
  for (const entry of extraEntriesData) {
    if (memberRoleIds.has(entry.role_id)) totalEntries += entry.count;
  }

  for (let i = 0; i < totalEntries; i++) participants.push(userId);

  await queryOne('UPDATE giveaways SET participants = $1 WHERE id = $2', [JSON.stringify(participants), gaId]);
  await interaction.message.edit({ embeds: [buildEmbed(participants)] }).catch(() => {});

  const replyMsg = totalEntries > 1
    ? `<:Yes:1508365664778190878> Successfully entered the giveaway!\n\n<:vip:1508831641135612068> Total Entries: **${totalEntries}**\n\n<:Boost:1508378809676861573> Bonus role entries applied!`
    : `<:Yes:1508365664778190878> Successfully entered the giveaway!\n\n<:vip:1508831641135612068> Total Entries: **1**`;
  await interaction.reply({ content: replyMsg, ephemeral: true });
}
async function handleViewParticipants(interaction, gaId) {
  const ga = await queryOne('SELECT * FROM giveaways WHERE id = $1', [gaId]);
  if (!ga) return interaction.reply({ content: '❌ Giveaway not found.', ephemeral: true });

  const allEntries = JSON.parse(ga.participants || '[]');
  if (!allEntries.length) {
    const e = baseEmbed('<:user:1508831475796148285> Giveaway Participants', PRIMARY);
    e.setDescription('No one has entered yet.');
    return interaction.reply({ embeds: [e], ephemeral: true });
  }

  const tally = {};
  for (const uid of allEntries) tally[uid] = (tally[uid] ?? 0) + 1;

  const lines = Object.entries(tally)
    .sort(([, a], [, b]) => b - a)
    .map(([uid, count], i) =>
      `> ${String(i + 1).padStart(2, '0')}. <@${uid}> — **${count}** ${count !== 1 ? 'Entries' : 'Entry'}`
    );

  const PAGE_SIZE = 15;
  const pages = [];
  for (let i = 0; i < lines.length; i += PAGE_SIZE) pages.push(lines.slice(i, i + PAGE_SIZE).join('\n'));

  const totalUnique  = Object.keys(tally).length;
  const totalEntries = allEntries.length;
  const footer       = `${totalUnique} participant${totalUnique !== 1 ? 's' : ''} · ${totalEntries} total entr${totalEntries !== 1 ? 'ies' : 'y'}`;

  const embed = new EmbedBuilder()
    .setColor(PRIMARY)
    .setTitle('<:user:1508831475796148285> Giveaway Participants')
    .setDescription(`<:vip:1508831641135612068> Top Entries\n\n${pages[0]}`)
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

  const baseSection = `### <:user:1508831475796148285> Base Entries\n> Everyone receives 1 base entry`;

  let rolesSection = '';
  if (extraEntriesData.length) {
    rolesSection = `\n\n### <:Boost:1508378809676861573> Extra Role Bonuses\n` +
      extraEntriesData.map(ed => `<:arrow:1509857611816763482> <@&${ed.role_id}> +${ed.count} ${ed.count !== 1 ? 'Entries' : 'Entry'}`).join('\n');
  }

  const e = new EmbedBuilder()
    .setColor(PRIMARY)
    .setDescription(`# <:vip:1508831641135612068> Bonus Entry Roles\n\n${baseSection}${rolesSection}`);

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
      `> ${String(i + 1).padStart(2, '0')}. <@${uid}> — **${count}** ${count !== 1 ? 'Entries' : 'Entry'}`
    );

  const PAGE_SIZE = 15;
  const pages = [];
  for (let i = 0; i < lines.length; i += PAGE_SIZE) pages.push(lines.slice(i, i + PAGE_SIZE).join('\n'));

  const totalUnique  = Object.keys(tally).length;
  const totalEntries = allEntries.length;

  const embed = new EmbedBuilder()
    .setColor(PRIMARY)
    .setTitle('<:user:1508831475796148285> Giveaway Participants')
    .setDescription(`<:vip:1508831641135612068> Top Entries\n\n${pages[page]}`)
    .setFooter({ text: `Page ${page + 1}/${pages.length} · ${totalUnique} participant${totalUnique !== 1 ? 's' : ''} · ${totalEntries} total entr${totalEntries !== 1 ? 'ies' : 'y'}` });
  const row = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`ga_pg:${pgGaId}:${page - 1}`).setLabel('← Prev').setStyle(ButtonStyle.Secondary).setDisabled(page === 0),
    new ButtonBuilder().setCustomId(`ga_pg:${pgGaId}:${page + 1}`).setLabel('Next →').setStyle(ButtonStyle.Secondary).setDisabled(page === pages.length - 1),
  );
  return interaction.update({ embeds: [embed], components: [row] });
}

module.exports = { handleButton };
