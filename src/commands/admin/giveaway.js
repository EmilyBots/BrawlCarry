const { SlashCommandBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder } = require('discord.js');
const { queryOne, queryAll } = require('../../db/index');
const { baseEmbed } = require('../../utils/embeds');
const { PRIMARY, SUCCESS, GOLD, DANGER, FOOTER_BRAND } = require('../../config/constants');
const { v4: uuidv4 } = require('uuid');

// ── Cleanup helper ────────────────────────────────────────────────────────────
// Grace period: giveaway deve essere scaduto da almeno 2 ore per essere
// considerato candidato alla pulizia. Evita di toccare giveaway appena finiti.
const CLEANUP_GRACE_HOURS = 2;

async function runGiveawayCleanup(client) {
  const { resolveChannel } = require('../../events/giveaway_end');

  const cutoff = new Date(Date.now() - CLEANUP_GRACE_HOURS * 3600_000).toISOString();

  // Tutti i giveaway candidati alla pulizia:
  // 1. Già terminati (hanno winner_ids valorizzato, incluso NO_WINNER)
  // 2. Scaduti da più di CLEANUP_GRACE_HOURS senza winner_ids (loop non li ha ancora processati ma il canale non esiste)
  const rows = await require('../../db/index').queryAll(
    `SELECT * FROM giveaways
     WHERE
       (winner_ids IS NOT NULL AND winner_ids != '' AND winner_ids != '[]')
       OR
       (ended_at IS NOT NULL AND ended_at < $1)`,
    [cutoff]
  );

  let removedExpired  = 0;
  let removedOrphan   = 0;
  let removedInvalid  = 0;

  const { queryOne: qOne } = require('../../db/index');

  for (const ga of rows) {
    const gaId = ga.id;

    // ── Invalidi/corrotti: prize o ended_at mancanti ──────────────────────
    if (!ga.prize || !ga.ended_at) {
      await qOne('DELETE FROM giveaways WHERE id = $1', [gaId]);
      removedInvalid++;
      continue;
    }

    // ── Già terminati con winner valido: elimina dal DB ───────────────────
    const hasValidWinner = ga.winner_ids &&
      ga.winner_ids !== '' &&
      ga.winner_ids !== '[]';

    if (hasValidWinner) {
      await qOne('DELETE FROM giveaways WHERE id = $1', [gaId]);
      removedExpired++;
      continue;
    }

    // ── Scaduti senza winner: verifica se canale esiste ancora ────────────
    // (solo questi richiedono la verifica canale, non tutti)
    const ch = ga.channel_id
      ? (() => {
          for (const guild of client.guilds.cache.values()) {
            const found = guild.channels.cache.get(String(ga.channel_id));
            if (found) return found;
          }
          return null;
        })()
      : null;

    if (!ch) {
      // Canale non trovato → giveaway orfano
      await qOne('DELETE FROM giveaways WHERE id = $1', [gaId]);
      removedOrphan++;
      continue;
    }

    // Canale esiste ma il giveaway è scaduto e non ha winner:
    // il loop di giveaway_end lo processerà normalmente, non tocchiamo nulla.
  }

  return { removedExpired, removedOrphan, removedInvalid };
}
function getGiveawayEnd() {
  return require('../../events/giveaway_end');
}

const GIVEAWAY_ROLE = '1479079737052762205';
function hasGiveawayRole(interaction) {
  return interaction.member?.roles?.cache?.has(GIVEAWAY_ROLE) ?? false;
}
const DENIED = { content: '❌ You do not have permission to use this command.', ephemeral: true };

async function autocompleteActive(interaction) {
  try {
    const focused = interaction.options.getFocused().toLowerCase();
    const rows = await queryAll(
      `SELECT id, prize FROM giveaways
       WHERE (winner_ids IS NULL OR winner_ids = '' OR winner_ids = '[]')
         AND ended_at > NOW()
       ORDER BY ended_at ASC LIMIT 25`
    );
    const choices = rows
      .filter(r => r.id.toLowerCase().includes(focused) || r.prize.toLowerCase().includes(focused))
      .map(r => ({ name: `${r.id} — ${r.prize}`.slice(0, 100), value: r.id }));
    await interaction.respond(choices);
  } catch (_) { await interaction.respond([]).catch(() => {}); }
}

async function autocompleteEnded(interaction) {
  try {
    const focused = interaction.options.getFocused().toLowerCase();
    const rows = await queryAll(
      `SELECT id, prize FROM giveaways
       WHERE winner_ids IS NOT NULL AND winner_ids != '' AND winner_ids != '[]'
       ORDER BY ended_at DESC LIMIT 25`
    );
    const choices = rows
      .filter(r => r.id.toLowerCase().includes(focused) || r.prize.toLowerCase().includes(focused))
      .map(r => ({ name: `${r.id} — ${r.prize}`.slice(0, 100), value: r.id }));
    await interaction.respond(choices);
  } catch (_) { await interaction.respond([]).catch(() => {}); }
}

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
      content: '**<a:giveaway:1506218898255773827> @everyone NEW GIVEAWAY <a:giveaway:1506218898255773827>**',
      embeds: [e],
      components: [view],
      allowedMentions: { parse: ['everyone'] },
    });
    await interaction.reply({ content: `✅ Giveaway started! ID: \`${gaId}\``, ephemeral: true });
  },
};

// ── /end-giveaway ─────────────────────────────────────────────────────────────
const endGiveawayCmd = {
  data: new SlashCommandBuilder()
    .setName('end-giveaway')
    .setDescription('Termina immediatamente un giveaway attivo e sceglie i vincitori')
    .addStringOption(o =>
      o.setName('giveaway_id').setDescription('ID o nome del giveaway').setRequired(true).setAutocomplete(true)
    ),

  async autocomplete(interaction) { await autocompleteActive(interaction); },

  async execute(interaction) {
    if (!hasGiveawayRole(interaction)) return interaction.reply(DENIED);
    await interaction.deferReply({ ephemeral: true });

    const { finishGiveaway } = getGiveawayEnd();
    const gaId = interaction.options.getString('giveaway_id');
    const ga   = await queryOne('SELECT * FROM giveaways WHERE id = $1', [gaId]);
    if (!ga) return interaction.editReply({ content: `❌ Giveaway \`${gaId}\` non trovato.` });

    const alreadyEnded = ga.winner_ids && ga.winner_ids !== '' && ga.winner_ids !== '[]';
    if (alreadyEnded) return interaction.editReply({ content: `❌ Il giveaway \`${gaId}\` è già terminato.` });

    await finishGiveaway(interaction.client, ga);
    await interaction.editReply({ content: `✅ Giveaway \`${gaId}\` terminato e vincitori annunciati.` });
  },
};

// ── /reroll-giveaway ──────────────────────────────────────────────────────────
const rerollGiveawayCmd = {
  data: new SlashCommandBuilder()
    .setName('reroll-giveaway')
    .setDescription('Sceglie un nuovo vincitore per un giveaway già concluso')
    .addStringOption(o =>
      o.setName('giveaway_id').setDescription('ID o nome del giveaway').setRequired(true).setAutocomplete(true)
    )
    .addIntegerOption(o =>
      o.setName('count').setDescription('Quanti nuovi vincitori (default: stesso numero originale)').setMinValue(1)
    ),

  async autocomplete(interaction) { await autocompleteEnded(interaction); },

  async execute(interaction) {
    if (!hasGiveawayRole(interaction)) return interaction.reply(DENIED);
    await interaction.deferReply({ ephemeral: true });

    const { resolveChannel } = getGiveawayEnd();
    const gaId          = interaction.options.getString('giveaway_id');
    const countOverride = interaction.options.getInteger('count') ?? null;
    const ga            = await queryOne('SELECT * FROM giveaways WHERE id = $1', [gaId]);

    if (!ga) return interaction.editReply({ content: `❌ Giveaway \`${gaId}\` non trovato.` });

    const notEnded = !ga.winner_ids || ga.winner_ids === '' || ga.winner_ids === '[]';
    if (notEnded) return interaction.editReply({ content: `❌ Il giveaway \`${gaId}\` non è ancora terminato. Usa prima \`/end-giveaway\`.` });

    const participants = JSON.parse(ga.participants || '[]');
    const unique       = [...new Set(participants)];
    if (!unique.length) return interaction.editReply({ content: `❌ Nessun partecipante — impossibile rerollare.` });

    let prevWinners = [];
    try {
      const parsed = JSON.parse(ga.winner_ids);
      if (Array.isArray(parsed)) prevWinners = parsed.filter(w => w !== 'NO_WINNER');
    } catch (_) {}

    const pool     = unique.filter(u => !prevWinners.includes(u));
    const drawFrom = pool.length > 0 ? pool : unique;
    const count    = Math.min(countOverride ?? ga.winners, drawFrom.length);
    const newWinners = drawFrom.sort(() => 0.5 - Math.random()).slice(0, count);

    const ch = await resolveChannel(interaction.client, ga.channel_id, gaId);
    let validWinners = newWinners;
    if (ch?.guild) {
      const membersMap = await ch.guild.members.fetch({ user: newWinners }).catch(() => new Map());
      validWinners = newWinners.filter(uid => membersMap.has(uid));
    }

    if (!validWinners.length) return interaction.editReply({ content: `❌ Nessuno dei partecipanti selezionati risulta ancora nel server.` });

    const validMentions = validWinners.map(w => `<@${w}>`).join(' ');
    const e = baseEmbed(`🎁 ${ga.prize} — Reroll`, GOLD);
    e.addFields(
      { name: '🏆 New Winner(s)',       value: validMentions,                         inline: false },
      { name: '👥 Total Participants', value: `**${unique.length.toLocaleString()}**`, inline: true  },
      { name: '🆔 Giveaway ID',        value: `\`${gaId}\``,                          inline: true  },
    )
    .setFooter({ text: `${FOOTER_BRAND} | ID: ${gaId}` })
    .setTimestamp();

    if (ch) {
      await ch.send({
        content: `🎉 New winner${validWinners.length !== 1 ? 's' : ''}: ${validMentions}! You won **${ga.prize}**!`,
        embeds: [e],
        allowedMentions: { users: validWinners },
      }).catch(() => {});
    }

    await interaction.editReply({ content: `✅ Reroll completato. Nuovo/i vincitore/i: ${validMentions}` });
  },
};

// ── /giveaway-reminder ────────────────────────────────────────────────────────
const giveawayReminderCmd = {
  data: new SlashCommandBuilder()
    .setName('giveaway-reminder')
    .setDescription('Invia manualmente il reminder per un giveaway attivo')
    .addStringOption(o =>
      o.setName('giveaway_id').setDescription('ID o nome del giveaway').setRequired(true).setAutocomplete(true)
    ),

  async autocomplete(interaction) { await autocompleteActive(interaction); },

  async execute(interaction) {
    if (!hasGiveawayRole(interaction)) return interaction.reply(DENIED);
    await interaction.deferReply({ ephemeral: true });

    const { sendGiveawayReminder } = getGiveawayEnd();
    const gaId = interaction.options.getString('giveaway_id');
    const ga   = await queryOne('SELECT * FROM giveaways WHERE id = $1', [gaId]);
    if (!ga) return interaction.editReply({ content: `❌ Giveaway \`${gaId}\` non trovato.` });

    const alreadyEnded = ga.winner_ids && ga.winner_ids !== '' && ga.winner_ids !== '[]';
    if (alreadyEnded) return interaction.editReply({ content: `❌ Il giveaway \`${gaId}\` è già terminato.` });

    const sent = await sendGiveawayReminder(interaction.client, ga);
    if (!sent) return interaction.editReply({ content: `❌ Impossibile trovare il canale per il giveaway \`${gaId}\`.` });

    await interaction.editReply({ content: `✅ Reminder inviato per il giveaway \`${gaId}\`.` });
  },
};

// ── /clear-giveaways ──────────────────────────────────────────────────────────
const clearGiveawaysCmd = {
  data: new SlashCommandBuilder()
    .setName('clear-giveaways')
    .setDescription('Rimuove dal DB giveaway scaduti, orfani o corrotti'),

  async execute(interaction) {
    if (!hasGiveawayRole(interaction)) return interaction.reply(DENIED);
    await interaction.deferReply({ ephemeral: true });

    let result;
    try {
      result = await runGiveawayCleanup(interaction.client);
    } catch (err) {
      console.error('[ERROR] clear-giveaways:', err);
      return interaction.editReply({ content: `❌ Errore durante il cleanup: \`${err.message}\`` });
    }

    const { removedExpired, removedOrphan, removedInvalid } = result;
    const total = removedExpired + removedOrphan + removedInvalid;

    if (total === 0) {
      return interaction.editReply({ content: '✅ Nessun giveaway da pulire — il DB è già pulito.' });
    }

    const lines = [
      '✅ **Giveaway cleanup completed**\n',
      '**Removed:**',
      removedExpired  > 0 ? `• \`${removedExpired}\`  expired giveaways (già terminati con vincitori)`  : null,
      removedOrphan   > 0 ? `• \`${removedOrphan}\`  orphan giveaways (canale non più esistente)`       : null,
      removedInvalid  > 0 ? `• \`${removedInvalid}\`  invalid/corrupted giveaways (dati mancanti)`       : null,
    ].filter(Boolean).join('\n');

    await interaction.editReply({ content: lines });
  },
};

module.exports = [giveawayCmd, endGiveawayCmd, rerollGiveawayCmd, giveawayReminderCmd, clearGiveawaysCmd];
