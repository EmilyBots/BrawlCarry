const { queryOne } = require('../db/index');
const { baseEmbed } = require('../utils/embeds');
const { PRIMARY, ACCENT } = require('../config/constants');

async function handleButton(interaction) {
  const id    = interaction.customId;
  const gaId  = id.split(':')[1];

  if (id.startsWith('ga_enter:'))  return handleEnter(interaction, gaId);
  if (id.startsWith('ga_view:'))   return handleViewParticipants(interaction, gaId);
  if (id.startsWith('ga_roles:'))  return handleViewRoles(interaction, gaId);
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
}

async function handleViewParticipants(interaction, gaId) {
  const ga  = await queryOne('SELECT participants FROM giveaways WHERE id = $1', [gaId]);
  const raw = JSON.parse(ga?.participants || '[]');
  const cnt = new Set(raw).size;
  const e   = baseEmbed('👥 Giveaway Participants', PRIMARY);
  e.setDescription(`**${cnt.toLocaleString()}** participant${cnt !== 1 ? 's' : ''} have entered.`);
  await interaction.reply({ embeds: [e], ephemeral: true });
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

module.exports = { handleButton };
