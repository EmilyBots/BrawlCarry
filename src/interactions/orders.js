const {
  ModalBuilder, TextInputBuilder, TextInputStyle,
  ActionRowBuilder, ButtonBuilder, ButtonStyle,
  StringSelectMenuBuilder, StringSelectMenuOptionBuilder,
  EmbedBuilder,
} = require('discord.js');
const { queryOne, queryAll, getConfig } = require('../db/index');
const { baseEmbed, formatDuration } = require('../utils/embeds');
const { calculateRankPrice, calculatePrestigePrice, validatePrestigeTrophies, rankEmoji, prestigeEmoji, buildOrderDetailsStr } = require('../utils/pricing');
const { getPaymentMethods, getPaymentEmoji, getBoosterStatus, updateTicketActivity } = require('../utils/permissions');
const { createTicketThread } = require('../utils/tickets');
const { fetchAndWatermark } = require('../utils/watermark');
const {
  PRIMARY, ACCENT, SUCCESS, GOLD, DANGER, FOOTER_BRAND,
  CURRENT_RANKS, DESIRED_RANKS, ALL_RANKS, RANK_EMOJI,
  PRESTIGE_OPTIONS, PRESTIGE_EMOJI, PRESTIGE_PRICES, PRESTIGE_BASE_TROPHIES,
  P11_OPTIONS, P11_EMOJI, HARDCODED_SUPPORT_ROLES,
} = require('../config/constants');
const { v4: uuidv4 } = require('uuid');

// ── In-memory state store for multi-step select views ─────────────────────────
// Keyed by userId — stores selections until final submit
const orderState = new Map();

function getState(userId) {
  if (!orderState.has(userId)) orderState.set(userId, {});
  return orderState.get(userId);
}

// ── Prestige level helpers ────────────────────────────────────────────────────
const PRESTIGE_LEVELS = ['Prestige 0', 'Prestige 1', 'Prestige 2', 'Prestige 3'];

const PREST_CURRENT_EMOJI = {
  'Prestige 0': '<:Prestige0:1508145555052957737>',
  'Prestige 1': '<:P1:1508147277577846856>',
  'Prestige 2': '<:P2:1508147330983923833>',
};
const PREST_DESIRED_EMOJI = {
  'Prestige 1': '<:P1:1508147277577846856>',
  'Prestige 2': '<:P2:1508147330983923833>',
  'Prestige 3': '<:P3:1508147370947252345>',
};

/** Opzioni desired filtrate: solo prestiges superiori a currentPrestige. */
function buildDesiredPrestigeOptions(currentPrestige) {
  const ci = PRESTIGE_LEVELS.indexOf(currentPrestige);
  return PRESTIGE_LEVELS.slice(ci + 1).map(p =>
    new StringSelectMenuOptionBuilder().setLabel(p).setValue(p).setEmoji(PREST_DESIRED_EMOJI[p] || undefined)
  );
}

/**
 * Somma i prezzi di ogni step tra currentPrestige e desiredPrestige.
 * Per il primo step usa trophyVal reale; per i successivi usa rangeStart (= prezzo pieno).
 * Il moltiplicatore carry viene applicato UNA VOLTA sul totale finale.
 */
function calculateMultiPrestigePrice(currentPrestige, desiredPrestige, trophyVal, serviceType) {
  const ci = PRESTIGE_LEVELS.indexOf(currentPrestige);
  const di = PRESTIGE_LEVELS.indexOf(desiredPrestige);
  let base = 0;
  for (let i = ci; i < di; i++) {
    const spec = `${PRESTIGE_LEVELS[i]} -> ${PRESTIGE_LEVELS[i + 1]}`;
    const tv   = (i === ci) ? trophyVal : PRESTIGE_BASE_TROPHIES[spec];
    base += calculatePrestigePrice(spec, tv, 'boost'); // 'boost' → nessun ×2 interno
  }
  const price = serviceType === 'carry' ? base * 2 : base;
  return Math.round(price * 100) / 100;
}

// ── Panel buttons ─────────────────────────────────────────────────────────────
async function handleRankedPanelBtn(interaction) {
  const guildId  = interaction.guildId;
  const methods  = await getPaymentMethods(guildId);

  const currentOptions = CURRENT_RANKS.map(r => new StringSelectMenuOptionBuilder().setLabel(r).setValue(r).setEmoji(rankEmoji(r) || undefined));
  const desiredOptions = DESIRED_RANKS.map(r => new StringSelectMenuOptionBuilder().setLabel(r).setValue(r).setEmoji(rankEmoji(r) || undefined));
  const p11Options     = P11_OPTIONS.map(p => new StringSelectMenuOptionBuilder().setLabel(p).setValue(p).setEmoji(P11_EMOJI));
  const payOptions     = methods.map(m => new StringSelectMenuOptionBuilder().setLabel(m.label).setValue(m.label).setEmoji(m.emoji || undefined));
  const svcOptions = [
    new StringSelectMenuOptionBuilder().setLabel('B00st').setValue('boost').setDescription('We play on your account - Standard service').setEmoji('<:Boost:1508378809676861573>'),
    new StringSelectMenuOptionBuilder().setLabel('Carry').setValue('carry').setDescription('We play with you (2× Price)').setEmoji('<:Carry:1501221214251651082>'),
  ];

  const e = baseEmbed('<:master:1491521740860428459> Ranked Order', PRIMARY);
  e.setDescription('>>> **Climb the Ranked leaderboard quickly and safely with our experienced boosters.**\n\n⚡ Fast • 🔒 Secure • ⭐ Trusted\n\n⚠️ Minimum desired rank is **Diamond I**. Desired rank must be higher than current rank.');

  const components = [
    new ActionRowBuilder().addComponents(new StringSelectMenuBuilder().setCustomId('ranked_current').setPlaceholder('Your current rank...').addOptions(currentOptions)),
    new ActionRowBuilder().addComponents(new StringSelectMenuBuilder().setCustomId('ranked_desired').setPlaceholder('Your desired rank (min Diamond I)...').addOptions(desiredOptions)),
    new ActionRowBuilder().addComponents(new StringSelectMenuBuilder().setCustomId('ranked_p11').setPlaceholder('Number of Power 11 brawlers...').addOptions(p11Options)),
    new ActionRowBuilder().addComponents(new StringSelectMenuBuilder().setCustomId('ranked_pay').setPlaceholder('Payment method...').addOptions(payOptions)),
    new ActionRowBuilder().addComponents(new StringSelectMenuBuilder().setCustomId('ranked_svc').setPlaceholder('Service Type...').addOptions(svcOptions)),
  ];

  await interaction.reply({ embeds: [e], components, ephemeral: true });
}

async function handlePrestigePanelBtn(interaction) {
  const guildId = interaction.guildId;
  const methods = await getPaymentMethods(guildId);

  const currentOptions = ['Prestige 0', 'Prestige 1', 'Prestige 2'].map(p =>
    new StringSelectMenuOptionBuilder().setLabel(p).setValue(p).setEmoji(PREST_CURRENT_EMOJI[p] || undefined)
  );
  const payOptions = methods.map(m =>
    new StringSelectMenuOptionBuilder().setLabel(m.label).setValue(m.label).setEmoji(m.emoji || undefined)
  );
  const svcOptions = [
    new StringSelectMenuOptionBuilder().setLabel('B00st').setValue('boost').setDescription('We play on your account - Standard service').setEmoji('<:Boost:1508378809676861573>'),
    new StringSelectMenuOptionBuilder().setLabel('Carry').setValue('carry').setDescription('We play with you (2× Price)').setEmoji('<:Carry:1501221214251651082>'),
  ];

  const e = baseEmbed('<:copyright:1485657838897467534> Prestige Order', ACCENT);
  e.setDescription('>>> **Reach your desired Prestige quickly and safely with our experienced boosters.**\n\n⚡ Fast • 🔒 Secure • ⭐ Trusted');

  const components = [
    new ActionRowBuilder().addComponents(
      new StringSelectMenuBuilder().setCustomId('prest_current').setPlaceholder('Current Prestige...').addOptions(currentOptions)
    ),
    new ActionRowBuilder().addComponents(
      new StringSelectMenuBuilder().setCustomId('prest_desired').setPlaceholder('Desired Prestige (select Current first)...').setDisabled(true)
        .addOptions(new StringSelectMenuOptionBuilder().setLabel('—').setValue('placeholder'))
    ),
    new ActionRowBuilder().addComponents(
      new StringSelectMenuBuilder().setCustomId('prest_pay').setPlaceholder('Payment method...').addOptions(payOptions)
    ),
    new ActionRowBuilder().addComponents(
      new StringSelectMenuBuilder().setCustomId('prest_svc').setPlaceholder('Service Type...').addOptions(svcOptions)
    ),
  ];

  await interaction.reply({ embeds: [e], components, ephemeral: true });
}

// ── Select handlers ───────────────────────────────────────────────────────────
async function handleSelect(interaction) {
  const id    = interaction.customId;
  const value = interaction.values[0];
  const state = getState(interaction.user.id);

  if (id === 'ranked_current') { state.currentRank = value; return interaction.deferUpdate(); }
  if (id === 'ranked_desired') { state.desiredRank = value; return interaction.deferUpdate(); }
  if (id === 'ranked_p11')     { state.p11 = value;         return interaction.deferUpdate(); }
  if (id === 'ranked_pay')     { state.payment = value;     return interaction.deferUpdate(); }

  if (id === 'prest_current') {
    state.currentPrestige = value;
    state.desiredPrestige = null; // reset se l'utente cambia current
    const methods = await getPaymentMethods(interaction.guildId);
    const currentOptions = ['Prestige 0', 'Prestige 1', 'Prestige 2'].map(p =>
      new StringSelectMenuOptionBuilder().setLabel(p).setValue(p).setEmoji(PREST_CURRENT_EMOJI[p] || undefined)
    );
    const desiredOptions = buildDesiredPrestigeOptions(value);
    const payOptions = methods.map(m =>
      new StringSelectMenuOptionBuilder().setLabel(m.label).setValue(m.label).setEmoji(m.emoji || undefined)
    );
    const svcOptions = [
    new StringSelectMenuOptionBuilder().setLabel('B00st').setValue('boost').setDescription('We play on your account - Standard service').setEmoji('<:Boost:1508378809676861573>'),
    new StringSelectMenuOptionBuilder().setLabel('Carry').setValue('carry').setDescription('We play with you (2× Price)').setEmoji('<:Carry:1501221214251651082>'),
  ];
    return interaction.update({ components: [
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder().setCustomId('prest_current').setPlaceholder('Current Prestige...').addOptions(currentOptions)
      ),
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder().setCustomId('prest_desired').setPlaceholder('Desired Prestige...').setDisabled(false).addOptions(desiredOptions)
      ),
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder().setCustomId('prest_pay').setPlaceholder('Payment method...').addOptions(payOptions)
      ),
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder().setCustomId('prest_svc').setPlaceholder('Service Type...').addOptions(svcOptions)
      ),
    ]});
  }
  if (id === 'prest_desired') { state.desiredPrestige = value; return interaction.deferUpdate(); }
  if (id === 'prest_pay')     { state.payment = value;         return interaction.deferUpdate(); }

  // Final selects trigger confirmation
  if (id === 'ranked_svc') {
    state.serviceType = value;
    return handleRankedSvcSubmit(interaction, state);
  }
  if (id === 'prest_svc') {
    state.serviceType = value;
    return handlePrestigeSvcSubmit(interaction, state);
  }
}

async function handleRankedSvcSubmit(interaction, state) {
  const missing = [];
  if (!state.currentRank) missing.push('Current Rank');
  if (!state.desiredRank) missing.push('Desired Rank');
  if (!state.p11)         missing.push('Power 11 Brawlers');
  if (!state.payment)     missing.push('Payment Method');
  if (missing.length) return interaction.reply({ content: `❌ Please fill in: **${missing.join(', ')}**`, ephemeral: true });

  const fi = ALL_RANKS.indexOf(state.currentRank);
  const ti = state.desiredRank === 'Pro' ? ALL_RANKS.length : ALL_RANKS.indexOf(state.desiredRank);
  if (state.desiredRank !== 'Pro' && ti <= fi) {
    return interaction.reply({ content: `❌ Your desired rank **${state.desiredRank}** must be **higher** than your current rank **${state.currentRank}**.`, ephemeral: true });
  }

  const est = await calculateRankPrice(state.currentRank, state.desiredRank, state.p11, state.serviceType, interaction.guildId);
  state.estimatedPrice = est;

  const fe      = rankEmoji(state.currentRank);
  const te      = rankEmoji(state.desiredRank);
  const svcEmoji = state.serviceType === 'carry' ? '<:Carry:1501221214251651082>' : '<:Boost:1508378809676861573>';
  const svcLabel = state.serviceType === 'carry' ? 'Ranked Carry' : 'Ranked B00st';
  const payEmoji = await getPaymentEmoji(state.payment, interaction.guildId);
  const e  = baseEmbed(`<:Info:1501221322183934002> Review Your ${svcLabel} Order`, PRIMARY);
  e.setDescription(
    `## Please double-check your ranked order details before creating your ticket.\n\n` +
    `**Order Type** ${svcEmoji}\n<:reply:1507680110843658260> **${svcLabel}**\n\n` +
    `**Current Rank** ${fe}\n<:reply:1507680110843658260> **${state.currentRank}**\n\n` +
    `**Desired Rank** ${te}\n<:reply:1507680110843658260> **${state.desiredRank}**\n\n` +
    `**Power 11** ${P11_EMOJI}\n<:reply:1507680110843658260> **${state.p11}**\n\n` +
    `**Estimated Price** <:Amount:1501221154650853450>\n<:reply:1507680110843658260> **${est.toFixed(2)}€**\n\n` +
    `**Payment Method** ${payEmoji}\n<:reply:1507680110843658260> **${state.payment}**`
  );

  const view = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('ranked_confirm').setLabel('Confirm & Continue').setStyle(ButtonStyle.Success).setEmoji('✅')
  );
  await interaction.reply({ embeds: [e], components: [view], ephemeral: true });
}

async function handlePrestigeSvcSubmit(interaction, state) {
  const missing = [];
  if (!state.currentPrestige) missing.push('Current Prestige');
  if (!state.desiredPrestige) missing.push('Desired Prestige');
  if (!state.payment)         missing.push('Payment Method');
  if (missing.length) return interaction.reply({ content: `❌ Please fill in: **${missing.join(', ')}**`, ephemeral: true });

  const ci = PRESTIGE_LEVELS.indexOf(state.currentPrestige);
  const di = PRESTIGE_LEVELS.indexOf(state.desiredPrestige);
  if (di <= ci) return interaction.reply({ content: '❌ Desired Prestige must be higher than Current Prestige.', ephemeral: true });

  // Open trophy + brawler name modal
  const modal = new ModalBuilder()
    .setCustomId('prestige_trophy_modal')
    .setTitle('Enter Trophy Count')
    .addComponents(
      new ActionRowBuilder().addComponents(
        new TextInputBuilder().setCustomId('trophy_input').setLabel('Current Trophies on the Brawler').setStyle(TextInputStyle.Short).setPlaceholder('e.g. 750 or 1200').setMaxLength(10).setRequired(true)
      ),
      new ActionRowBuilder().addComponents(
        new TextInputBuilder().setCustomId('brawler_name').setLabel('Brawler Name').setStyle(TextInputStyle.Short).setPlaceholder('e.g. Shelly, Bull, Crow...').setMaxLength(50).setRequired(true)
      ),
    );
  await interaction.showModal(modal);
}

// ── Confirm buttons ───────────────────────────────────────────────────────────
async function handleConfirm(interaction) {
  const id    = interaction.customId;
  const state = getState(interaction.user.id);

  if (id === 'ranked_confirm') {
    const modal = new ModalBuilder()
      .setCustomId('ranked_order_modal')
      .setTitle('Ranked Boost Order')
      .addComponents(
        new ActionRowBuilder().addComponents(
          new TextInputBuilder().setCustomId('notes').setLabel('Additional Notes (Optional)').setStyle(TextInputStyle.Paragraph).setMaxLength(500).setRequired(false).setPlaceholder('Any special requests...')
        )
      );
    await interaction.showModal(modal);
  }
}

// ── Prestige trophy modal ─────────────────────────────────────────────────────
async function handlePrestigeTrophyModal(interaction) {
  const state    = getState(interaction.user.id);
  const trophyRaw = interaction.fields.getTextInputValue('trophy_input').trim();
  const brawler   = interaction.fields.getTextInputValue('brawler_name').trim();

  let trophyVal;
  try { trophyVal = parseInt(trophyRaw.replace(/[,. ]/g, '')); }
  catch (_) { return interaction.reply({ content: '❌ Please enter a valid number like `750`.', ephemeral: true }); }

  // Valida solo il primo step (current -> current+1), che è l'unico con trofei reali
  const ci = PRESTIGE_LEVELS.indexOf(state.currentPrestige);
  const firstStepSpec = `${state.currentPrestige} -> ${PRESTIGE_LEVELS[ci + 1]}`;
  const trophyError = validatePrestigeTrophies(firstStepSpec, trophyVal);
  if (trophyError) return interaction.reply({ content: trophyError, ephemeral: true });

  let trophyRange;
  if      (trophyVal <= 500)  trophyRange = '0 - 500';
  else if (trophyVal <= 1000) trophyRange = '501 - 1000';
  else if (trophyVal <= 1500) trophyRange = '1001 - 1500';
  else if (trophyVal <= 2000) trophyRange = '1501 - 2000';
  else if (trophyVal <= 2500) trophyRange = '2001 - 2500';
  else if (trophyVal <= 3000) trophyRange = '2501 - 3000';
  else                        trophyRange = '3001+';

  state.trophyVal   = trophyVal;
  state.trophyRange = trophyRange;
  state.brawlerName = brawler;

  const est = calculateMultiPrestigePrice(state.currentPrestige, state.desiredPrestige, trophyVal, state.serviceType);
  state.estimatedPrice = est;

  const specLabel = `${state.currentPrestige} → ${state.desiredPrestige}`;
  const pe = PREST_CURRENT_EMOJI[state.currentPrestige] ?? '✨';
  const e  = baseEmbed('📋 Order Summary', ACCENT);
  e.setDescription(
    `**Please confirm your order:**\n\n` +
    `${pe} **Prestige:** ${specLabel}\n` +
    `🎮 **Brawler:** ${brawler}\n` +
    `🏆 **Current Trophies:** ${trophyVal.toLocaleString()}\n` +
    `🛠 **Service:** ${state.serviceType === 'carry' ? 'Carry 🔴 (2x price)' : 'Boost 🟢'}\n` +
    `💰 **Payment:** ${state.payment}\n\n` +
    `💶 **Estimated Price:** ~${est.toFixed(2)}€\n\n` +
    'Click **Confirm & Continue** to open your ticket.'
  );

  const view = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('prestige_confirm').setLabel('Confirm & Continue').setStyle(ButtonStyle.Success).setEmoji('✅')
  );
  await interaction.reply({ embeds: [e], components: [view], ephemeral: true });
}

// This also needs its modal — open from prestige_confirm button
// We handle it in interactions/loader.js which routes prestige_confirm to handleConfirmPrestige:
async function handleConfirmPrestige(interaction) {
  const modal = new ModalBuilder()
    .setCustomId('prestige_order_modal')
    .setTitle('Prestige Boost Order')
    .addComponents(
      new ActionRowBuilder().addComponents(
        new TextInputBuilder().setCustomId('notes').setLabel('Additional Notes (Optional)').setStyle(TextInputStyle.Paragraph).setMaxLength(500).setRequired(false).setPlaceholder('Any special requests...')
      )
    );
  await interaction.showModal(modal);
}

// ── Ranked order modal submit ─────────────────────────────────────────────────
async function handleRankedModal(interaction) {
  const state   = getState(interaction.user.id);
  const guild   = interaction.guild;
  const member  = interaction.member;
  const cfg     = await getConfig(interaction.guildId);

  const orderId = `RANKED-${uuidv4().replace(/-/g, '').slice(0, 6).toUpperCase()}`;
  await queryOne(
    'INSERT INTO orders (id, user_id, from_tier, to_tier, price, method, order_type, service_type, p11_count) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)',
    [orderId, interaction.user.id, state.currentRank, state.desiredRank, 0.0, state.payment, 'ranked', state.serviceType, state.p11]
  );

  const fe       = rankEmoji(state.currentRank);
  const te       = rankEmoji(state.desiredRank);
  const payEmoji = await getPaymentEmoji(state.payment, interaction.guildId);
  const modeClean = state.serviceType === 'carry' ? 'Carry' : 'Boost';
  const modeEmoji = state.serviceType === 'carry' ? '<:Carry:1501221214251651082>' : '<:rocket:1491490870979985438>';

  const activatedE = baseEmbed('<:rocket:1491490870979985438> Order Ticket', PRIMARY);
  activatedE.setDescription('## Your Ranked request has been successfully created.\n\nOur team will review and begin processing it shortly.\n\nYou can manage your ticket using the options below.');

  const closeView = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('ticket_close_v2').setLabel('Close Ticket').setStyle(ButtonStyle.Danger).setEmoji('🔒')
  );

  let ticket;
  try {
    ticket = await createTicketThread(guild, member, `ranked-${member.user.username.slice(0, 12).toLowerCase()}`, activatedE, closeView, cfg, cfg?.ranked_ticket_channel_id ?? null);
    const staffPings = HARDCODED_SUPPORT_ROLES.map(r => `<@&${r}>`).join(' ');
    await ticket.send({ content: staffPings, allowedMentions: { parse: ['roles'] } });
  } catch (err) {
    return interaction.reply({ content: `❌ Failed to create ticket: \`${err.message}\`\n\nAsk an admin to check \`/setup\` channel permissions.`, ephemeral: true });
  }

  await queryOne('UPDATE orders SET ticket_channel_id = $1 WHERE id = $2', [ticket.id, orderId]);

  const orderE = baseEmbed('<:Info:1501221322183934002> Order Details', PRIMARY);
  orderE.setDescription(`## Your Ranked ${modeClean} Order`);
  orderE.addFields(
    { name: `Current Rank ${fe}`,       value: `→ ${state.currentRank}`,  inline: false },
    { name: `Desired Rank ${te}`,       value: `→ ${state.desiredRank}`,  inline: false },
    { name: 'Power Level <:copyright:1489943698203480214>', value: `→ ${state.p11} Power 11`, inline: false },
    { name: `Order Type ${modeEmoji}`,  value: `→ ${modeClean}`,          inline: false },
    { name: `Payment Method ${payEmoji}`, value: `→ ${state.payment}`,    inline: false },
    { name: '<:Amount:1501221154650853450> Estimated Price', value: `** ╔══ 💰  €${(state.estimatedPrice ?? 0).toFixed(2)}  ══╗**`, inline: false },
  );

  const publishView = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`send_boosters_${orderId}`).setLabel('Send to Boosters').setStyle(ButtonStyle.Primary).setEmoji('<:rocket:1491490870979985438>')
  );
  await ticket.send({ embeds: [orderE], components: [publishView] });
  await interaction.reply({ content: `✅ Your Ranked Boost order has been placed!\n📩 Ticket opened: ${ticket.toString()}`, ephemeral: true });

  orderState.delete(interaction.user.id);
}

// ── Prestige order modal submit ───────────────────────────────────────────────
async function handlePrestigeModal(interaction) {
  // ✅ Acknowledge immediately — MUST be first, before any await
  await interaction.deferReply({ ephemeral: true });

  const state  = getState(interaction.user.id);
  const guild  = interaction.guild;
  const member = interaction.member;

  // ✅ Guard against expired/missing state
  if (!state.currentPrestige || !state.desiredPrestige || !state.payment || !state.serviceType) {
    return interaction.editReply({ content: '❌ Session expired. Please start your order again.' });
  }

  const cfg    = await getConfig(interaction.guildId);

  const orderId = `PREST-${uuidv4().replace(/-/g, '').slice(0, 6).toUpperCase()}`;
  const fromP = state.currentPrestige;
  const toP   = state.desiredPrestige;

  await queryOne(
    'INSERT INTO orders (id, user_id, from_tier, to_tier, price, method, order_type, service_type, brawler_name, trophy_val) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)',
    [orderId, interaction.user.id, fromP, toP, 0.0, state.payment, 'prestige', state.serviceType, state.brawlerName, state.trophyVal]
  );

  const specLabel = `${state.currentPrestige} → ${state.desiredPrestige}`;
  const pe        = PREST_CURRENT_EMOJI[state.currentPrestige] ?? '✨';
  const payEmoji = await getPaymentEmoji(state.payment, interaction.guildId);
  const modeClean = state.serviceType === 'carry' ? 'Carry' : 'Boost';

  const activatedE = baseEmbed('<:rocket:1491490870979985438> Order Ticket', ACCENT);
  activatedE.setDescription('## Your Prestige request has been successfully created.\n\nOur team will review and begin processing it shortly.\n\nYou can manage your ticket using the options below.');

  const closeView = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('ticket_close_v2').setLabel('Close Ticket').setStyle(ButtonStyle.Danger).setEmoji('🔒')
  );

  let ticket;
  try {
    ticket = await createTicketThread(guild, member, `prestige-${member.user.username.slice(0, 12).toLowerCase()}`, activatedE, closeView, cfg, cfg?.prestige_ticket_channel_id ?? null);
    const staffPings = HARDCODED_SUPPORT_ROLES.map(r => `<@&${r}>`).join(' ');
    await ticket.send({ content: staffPings, allowedMentions: { parse: ['roles'] } });
  } catch (err) {
    return interaction.editReply({ content: `❌ Failed to create ticket: \`${err.message}\`` });
  }

  await queryOne('UPDATE orders SET ticket_channel_id = $1 WHERE id = $2', [ticket.id, orderId]);

  const orderE = baseEmbed('<:Info:1501221322183934002> Order Details', ACCENT);
  orderE.setDescription(`## Your Prestige ${modeClean} Order`);
  orderE.addFields(
    { name: `Prestige ${pe}`,                          value: `→ ${specLabel}`,                                                                    inline: false },                                                           
    { name: '<:user:1491499694734708815> Brawler',      value: `→ **${state.brawlerName}**`,                                                        inline: false },
    { name: '<:copyright:1485658086156013598> Trophies', value: `→ **${state.trophyVal?.toLocaleString() ?? '—'}**`,                                inline: false },
    { name: `${state.serviceType === 'carry' ? '<:Carry:1501221214251651082>' : '<:rocket:1491490870979985438>'} Order Type`, value: `→ **${modeClean}**`, inline: false },
    { name: `${payEmoji} Payment Method`,               value: `→ **${state.payment}**`,                                                            inline: false },
    { name: '<:Amount:1501221154650853450> Estimated Price', value: `**╔══ 💰 €${(state.estimatedPrice ?? 0).toFixed(2)} ══╗**`,                    inline: false },
  );

  const publishView = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`send_boosters_${orderId}`).setLabel('Send to Boosters').setStyle(ButtonStyle.Primary).setEmoji('<:rocket:1491490870979985438>')
  );
  await ticket.send({ embeds: [orderE], components: [publishView] });
    // ✅ editReply instead of reply (interaction is already deferred)
  await interaction.editReply({ content: `✅ Your Prestige order has been placed!\n📩 Ticket opened: ${ticket.toString()}` });
  orderState.delete(interaction.user.id);
}

// ── Send to boosters button ───────────────────────────────────────────────────
async function handleButton(interaction, client) {
  const id = interaction.customId;

  if (id.startsWith('send_boosters_') || id === 'order_publish_btn_v1') {
    if (!interaction.memberPermissions?.has('ManageChannels')) {
      return interaction.reply({ content: '❌ Only staff can publish orders to boosters.', ephemeral: true });
    }
    const orderId = id.startsWith('send_boosters_') ? id.replace('send_boosters_', '') : null;
    if (!orderId) return;

    const existing = await queryOne('SELECT booster_earnings FROM orders WHERE id = $1', [orderId]);
    if (existing?.booster_earnings !== null && existing?.booster_earnings !== undefined) {
      return interaction.reply({ content: '❌ This order has already been sent to boosters.', ephemeral: true });
    }

    const order = await queryOne('SELECT * FROM orders WHERE id = $1', [orderId]);
    if (!order) return interaction.reply({ content: '❌ Order not found.', ephemeral: true });

    const modal = new ModalBuilder()
      .setCustomId('publish_boosters_modal')
      .setTitle('Publish Order to Boosters')
      .addComponents(
        new ActionRowBuilder().addComponents(
          new TextInputBuilder().setCustomId('booster_earnings').setLabel('Booster Earnings (EUR)').setStyle(TextInputStyle.Short).setPlaceholder('e.g. 12.00').setRequired(true)
        )
      );

    // Store order_id on the interaction for the modal submit
    publishPending.set(interaction.user.id, { orderId, ticketChannelId: order.ticket_channel_id, orderType: order.order_type ?? 'ranked' });
    await interaction.showModal(modal);
    return;
  }

  if (id.startsWith('booster_claim:')) {
    const orderId = id.split(':')[1];
    return handleClaim(interaction, orderId, client);
  }
  if (id.startsWith('booster_unclaim:')) {
    const orderId = id.split(':')[1];
    return handleUnclaim(interaction, orderId);
  }
}

const publishPending = new Map();

// ── Publish modal submit ──────────────────────────────────────────────────────
async function handlePublishModal(interaction, client) {
  await interaction.deferReply({ ephemeral: true });

  const ctx = publishPending.get(interaction.user.id);
  if (!ctx) return interaction.followUp({ content: '❌ Session expired. Try again.', ephemeral: true });
  publishPending.delete(interaction.user.id);

  const earningsStr = interaction.fields.getTextInputValue('booster_earnings').replace('€', '').trim();
  const earnings    = parseFloat(earningsStr);
  if (isNaN(earnings)) return interaction.followUp({ content: '❌ Invalid earnings amount. Please enter a number like `12.00`.', ephemeral: true });

  const order = await queryOne('SELECT * FROM orders WHERE id = $1', [ctx.orderId]);
  if (!order) return interaction.followUp({ content: '❌ Order not found.', ephemeral: true });

  await queryOne('UPDATE orders SET booster_earnings = $1 WHERE id = $2', [earnings, ctx.orderId]);

  const guild      = interaction.guild;
  const cfg        = await getConfig(guild.id);
  const orderType  = ctx.orderType;
  const panelChId  = orderType === 'ranked' ? cfg?.ranked_panel_channel_id : cfg?.prestige_panel_channel_id;
  const panelCh    = panelChId ? guild.channels.cache.get(String(panelChId)) ?? await guild.channels.fetch(String(panelChId)).catch(() => null) : null;

  if (!panelCh) return interaction.followUp({ content: `❌ Panel channel not found. Configure via \`/setup\`.`, ephemeral: true });

  const svcType    = order.service_type ?? 'boost';
  const fromTier   = order.from_tier ?? '?';
  const toTier     = order.to_tier ?? '?';
  const color      = orderType === 'ranked' ? PRIMARY : ACCENT;
  const label      = orderType === 'ranked' ? 'Ranked' : 'Prestige';
  const svcLabel   = svcType === 'carry' ? `${label} **Carry**` : `${label} **Boost**`;
  const svcEmoji   = svcType === 'carry' ? '<:Carry:1501221214251651082>' : '<:rocket:1491490870979985438>';
  const details    = buildOrderDetailsStr(orderType, fromTier, toTier, svcType);

  const claimE = new EmbedBuilder()
    .setColor(color)
    .setTitle(`<:diamound:1491491246546616340> New ${label} Order!`)
    .addFields(
      { name: '<:Amount:1501221154650853450> You Make', value: `↳ **€${earnings.toFixed(2)}**`, inline: false },
      { name: `${svcEmoji} Order Type`,                value: `↳ ${svcLabel}`,                  inline: false },
    );
  if (order.p11_count) claimE.addFields({ name: `${P11_EMOJI} P11`, value: `↳ ${order.p11_count}`, inline: false });
  claimE.addFields({ name: '<:Info:1501221322183934002> Order Details', value: `↳ ${details}`, inline: false });
  if (order.trophy_val) claimE.addFields({ name: '<:copyright:1485658086156013598> Trophies', value: `↳ **${parseInt(order.trophy_val).toLocaleString()}**`, inline: false });
  claimE.addFields({ name: '<:user:1491499694734708815> Claimed By', value: '↳ Nobody', inline: false });
  claimE.setFooter({ text: `${FOOTER_BRAND} | Click below to claim this order` });

  const claimView = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`booster_claim:${ctx.orderId}`).setLabel('Claim Order').setStyle(ButtonStyle.Success).setEmoji('<:user:1491499694734708815>'),
    new ButtonBuilder().setCustomId(`booster_unclaim:${ctx.orderId}`).setLabel('Unclaim Order').setStyle(ButtonStyle.Danger).setEmoji('✖️'),
  );

  await panelCh.send({ embeds: [claimE], components: [claimView] });
  await interaction.followUp({ content: `✅ Order \`${ctx.orderId}\` published to ${panelCh} with **€${earnings.toFixed(2)}** booster earnings.`, ephemeral: true });
}

// ── Claim ─────────────────────────────────────────────────────────────────────
async function handleClaim(interaction, orderId, client) {
  const booster = interaction.member;
  const guild   = interaction.guild;

  const status = await getBoosterStatus(booster.id);
  if (status !== 'available') {
    return interaction.reply({ content: `❌ Your availability is set to **${status}**. Set it to \`available\` with \`/availability\` before claiming.`, ephemeral: true });
  }

  // Atomic claim — only succeeds if status is still 'pending'
  const result = await queryOne(
    "UPDATE orders SET booster_id = $1, status = 'claimed', claimed_at = NOW() WHERE id = $2 AND status = 'pending' RETURNING *",
    [booster.id, orderId]
  );

  if (!result) {
    const check = await queryOne('SELECT status, booster_id FROM orders WHERE id = $1', [orderId]);
    const msg   = !check ? '❌ Order not found.' : '❌ This order has already been claimed by another booster.';
    return interaction.reply({ content: msg, ephemeral: true });
  }

  const activeCount = await queryOne("SELECT COUNT(*) AS cnt FROM orders WHERE booster_id = $1 AND status = 'claimed'", [booster.id]);
  if (parseInt(activeCount.cnt) > 3) {
    await queryOne("UPDATE orders SET booster_id = NULL, status = 'pending', claimed_at = NULL WHERE id = $1", [orderId]);
    return interaction.reply({ content: '❌ You already have **2 active orders**. Please complete one before claiming another.', ephemeral: true });
  }

  const order = result;

  // Update claim embed
  try {
    const origEmbed = interaction.message.embeds[0];
    if (origEmbed) {
      const updated = EmbedBuilder.from(origEmbed).setColor(SUCCESS);
      const fields  = origEmbed.fields.map(f =>
        f.name.includes('Claimed By')
          ? { name: f.name, value: `↳ ${booster.toString()}`, inline: f.inline }
          : { name: f.name, value: f.value, inline: f.inline }
      );
      updated.setFields(fields);
      const disabledView = ActionRowBuilder.from(interaction.message.components[0]);
      disabledView.components[0].setDisabled(true);
      await interaction.message.edit({ embeds: [updated], components: [disabledView] });
    }
  } catch (_) {}

  // Create workspace thread
  const ticketChId = order.ticket_channel_id ? String(order.ticket_channel_id) : null;
  if (ticketChId && guild) {
    let ticketCh = guild.channels.cache.get(ticketChId)
      ?? await guild.channels.fetch(ticketChId).catch(() => null);

    if (!ticketCh) {
      try {
        const threads = await guild.channels.fetchActiveThreads();
        ticketCh = threads.threads.get(ticketChId) ?? null;
      } catch (_) {}
    }

    if (ticketCh) {
      const parentCh = ticketCh.isThread() ? ticketCh.parent : ticketCh;
      let workspace  = null;

      if (parentCh?.isTextBased() && parentCh.type === 0) {
        try {
          workspace = await parentCh.threads.create({
            name:   `active-${(order.order_type ?? 'ranked').toLowerCase()}-${(order.service_type ?? 'boost').toLowerCase()}`,
            type:   12, // PrivateThread
            reason: `Booster workspace for order ${orderId}`,
          });
        } catch (_) {
          try { workspace = await parentCh.threads.create({ name: `active-${orderId}`, type: 11 }); } catch (__) {}
        }
      }

      if (workspace) {
        await queryOne('UPDATE orders SET workspace_channel_id = $1 WHERE id = $2', [workspace.id, orderId]).catch(() => {});
        await workspace.members.add(booster.id).catch(() => {});
        const customer = guild.members.cache.get(String(order.user_id));
        if (customer) await workspace.members.add(customer.id).catch(() => {});

        const staffPings = HARDCODED_SUPPORT_ROLES.map(r => `<@&${r}>`).join(' ');
        await workspace.send({ content: staffPings, allowedMentions: { parse: ['roles'] } });

        const details      = buildOrderDetailsStr(order.order_type ?? 'ranked', order.from_tier ?? '?', order.to_tier ?? '?', order.service_type ?? 'boost');
        const orderLabel   = (order.order_type ?? 'ranked').charAt(0).toUpperCase() + (order.order_type ?? 'ranked').slice(1);
        const svcLabel     = (order.service_type ?? 'boost').charAt(0).toUpperCase() + (order.service_type ?? 'boost').slice(1);
        const svcEmoji     = order.service_type === 'carry' ? '<:Carry:1501221214251651082>' : '<:rocket:1491490870979985438>';
        const custMention  = customer?.toString() ?? `<@${order.user_id}>`;

        const orderEmbed = baseEmbed(`<:diamound:1491491246546616340> Active ${orderLabel} ${svcLabel} Order`, SUCCESS);
        orderEmbed.addFields(
          { name: '<:Customer:1501221119900778506> Customer', value: `↳ ${custMention}`,      inline: false },
          { name: '<:user:1491499694734708815> Booster',      value: `↳ ${booster.toString()}`, inline: false },
          { name: `${svcEmoji} Order Type`,                   value: `↳ **${svcLabel}**`,      inline: false },
          { name: '<:Info:1501221322183934002> Order Details', value: `↳ ${details}`,           inline: false },
        );
        await workspace.send({ embeds: [orderEmbed] });

        const safetyEmbed = baseEmbed('⚠️ Reminder', GOLD);
        safetyEmbed.setDescription('**Never DM the booster directly.**\n\nAlways use this thread for communication.\n\nThis helps prevent scams and keeps everything tracked safely.\n\n**Any attempt to bypass this rule by either the customer or the booster may result in consequences.**');
        const closeView = new ActionRowBuilder().addComponents(
          new ButtonBuilder().setCustomId('ticket_close_v2').setLabel('Close Ticket').setStyle(ButtonStyle.Danger).setEmoji('🔒')
        );
        await workspace.send({ embeds: [safetyEmbed], components: [closeView] });

        // Notify original ticket
        const notifyE = baseEmbed('<:rocket:1491490870979985438> Booster Assigned', SUCCESS);
        notifyE.setDescription(`${booster.toString()} has successfully claimed your order.\n\nA private thread has been created for both the customer and booster to safely manage communication and progress updates.\n\nPlease continue all communication inside the private thread.`);
        await ticketCh.send({ embeds: [notifyE] }).catch(() => {});
        await updateTicketActivity(ticketChId, guild.id);

        // DM booster
        try {
          const dmE = baseEmbed('<:rocket:1491490870979985438> Boost Claimed!', SUCCESS);
          dmE.setDescription(`You've successfully claimed order ${workspace.toString()}!\n\nHead to the workspace thread to begin.`);
          await booster.send({ embeds: [dmE] });
        } catch (_) {}
      }
    }
  }

  await interaction.reply({ content: `✅ You've claimed order \`${orderId}\`! Check the workspace thread.`, ephemeral: true });
}

// ── Unclaim ───────────────────────────────────────────────────────────────────
async function handleUnclaim(interaction, orderId) {
  const result = await queryOne(
    "UPDATE orders SET booster_id = NULL, status = 'pending', claimed_at = NULL WHERE id = $1 AND booster_id = $2 RETURNING id",
    [orderId, interaction.user.id]
  );

  if (!result) return interaction.reply({ content: '❌ You have not claimed this order.', ephemeral: true });

  // Restore embed
  try {
    const origEmbed = interaction.message.embeds[0];
    if (origEmbed) {
      const updated = EmbedBuilder.from(origEmbed).setColor(PRIMARY);
      const fields  = origEmbed.fields.map(f =>
        f.name.includes('Claimed By')
          ? { name: f.name, value: '↳ Nobody', inline: f.inline }
          : { name: f.name, value: f.value, inline: f.inline }
      );
      updated.setFields(fields);
      const restoredView = ActionRowBuilder.from(interaction.message.components[0]);
      restoredView.components[0].setDisabled(false);
      await interaction.message.edit({ embeds: [updated], components: [restoredView] });
    }
  } catch (_) {}

  await interaction.reply({ content: `↩️ You've unclaimed order \`${orderId}\`. It is now available for others.`, ephemeral: true });
}

// ── Order complete modal ──────────────────────────────────────────────────────
async function handleOrderCompleteModal(interaction, client) {
  await interaction.deferReply({ ephemeral: true });

  const orderId  = interaction.fields.getTextInputValue('order_id').trim();
  const priceStr = interaction.fields.getTextInputValue('final_price').replace('€', '').trim();
  const imgUrl   = interaction.fields.getTextInputValue('proof_image').trim();

  const order = await queryOne('SELECT * FROM orders WHERE id = $1', [orderId]);
  if (!order) return interaction.followUp({ content: `❌ Order \`${orderId}\` not found.`, ephemeral: true });
  if (order.status === 'completed') return interaction.followUp({ content: `❌ Order \`${orderId}\` is already completed.`, ephemeral: true });

  const priceVal = parseFloat(priceStr) || order.price || 0;
  const claimedAt = order.claimed_at ? new Date(order.claimed_at) : null;
  const now       = new Date();
  const completionSecs = claimedAt ? Math.floor((now - claimedAt) / 1000) : null;

  await queryOne(
    "UPDATE orders SET status = 'completed', price = $1, completed_at = $2, completion_time_seconds = $3 WHERE id = $4",
    [priceVal, now, completionSecs, orderId]
  );

  const guild        = interaction.guild;
  const cfg          = await getConfig(guild.id);
  const completedChId = cfg?.completed_channel_id ? String(cfg.completed_channel_id) : null;
  const completedCh   = completedChId ? guild.channels.cache.get(completedChId) : null;
  const customer      = order.user_id ? guild.members.cache.get(String(order.user_id)) : null;

  const svcType    = order.service_type ?? 'boost';
  const ordType    = order.order_type   ?? 'ranked';
  const details    = buildOrderDetailsStr(ordType, order.from_tier ?? '', order.to_tier ?? '', svcType);
  const payEmoji   = await getPaymentEmoji(order.method, interaction.guildId);
  const custMention = customer?.toString() ?? `<@${order.user_id}>`;
  const boosterMention = order.booster_id ? `<@${order.booster_id}>` : 'Unassigned';
  const mode       = svcType === 'carry' ? 'Carry' : 'Boost';
  const baseType   = ordType === 'prestige' ? 'Prestige' : ordType === 'account' ? 'Account' : 'Ranked';
  const modeEmoji  = svcType === 'carry' ? '<:Carry:1501221214251651082>' : '<:rocket:1491490870979985438>';

  const e = baseEmbed(ordType === 'account' ? '4CCOUNT ORDER ✦' : `${baseType.toUpperCase()} ORDER ✦`, SUCCESS);
  if (guild.icon) e.setAuthor({ name: 'BrawlCarry', iconURL: guild.iconURL() });
  e.addFields(
    { name: 'Customer <:Customer:1501221119900778506>', value: `${custMention}  ·  ${payEmoji} **${order.method ?? '—'}**`, inline: false },
    { name: 'Order Amount <:Amount:1501221154650853450>', value: `➜ **€${priceVal.toFixed(2)}**`, inline: false },
    { name: `Order Type ${modeEmoji}`, value: `➜ ${ordType === 'account' ? '4ccount' : `${baseType} **${mode}**`}`, inline: false },
    ...(ordType !== 'account' ? [{ name: 'Order Details <:Info:1501221322183934002>', value: `➜ ${details.split('\n')[0]}`, inline: false }] : []),
  );

  let wm = null;
  if (imgUrl) {
    wm = await fetchAndWatermark(imgUrl).catch(() => null);
    if (wm) e.setImage('attachment://proof.jpg');
  }

  const ctaView = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setLabel('Order now').setStyle(ButtonStyle.Link).setEmoji('<:rocket:1491490870979985438>')
      .setURL(ordType === 'prestige'
        ? 'https://discord.com/channels/1355262062095372429/1355262063437414564'
        : 'https://discord.com/channels/1355262062095372429/1477338397570760784'
      )
  );

  const sendArgs = { embeds: [e], components: [ctaView], ...(wm ? { files: [wm] } : {}) };
  if (completedCh) await completedCh.send(sendArgs).catch(() => {});
  else await interaction.channel.send(sendArgs).catch(() => {});

  // DM customer
  if (customer) {
    const orderKind = ordType === 'prestige' ? 'prestige' : ordType === 'account' ? 'account' : 'ranked';
    try {
      if (order.booster_id) {
        const dmE = baseEmbed('✅ Your Order is Complete!', SUCCESS);
        dmE.setDescription(
          `Great news! Your order **\`${orderId}\`** has been completed.\n\n` +
          `📦 **Result:** ${details}\n💰 **Amount:** €${priceVal.toFixed(2)}\n` +
          `${payEmoji} **Payment:** ${order.method ?? '—'}\n` +
          `⏱ **Time taken:** ${completionSecs ? formatDuration(completionSecs) : 'N/A'}\n\nPlease rate your booster below! ⭐`
        );
        const ratingView = new ActionRowBuilder().addComponents(
          new StringSelectMenuBuilder()
            .setCustomId(`booster_rate:${orderId}`)
            .setPlaceholder('Rate your booster...')
            .addOptions([5,4,3,2,1].map(n =>
              new StringSelectMenuOptionBuilder().setLabel(`${n} Star${n !== 1 ? 's' : ''}`).setValue(String(n)).setEmoji('⭐')
            ))
        );
        await customer.send({ embeds: [dmE], components: [ratingView] });
      } else {
        const dmE = baseEmbed('✅ Your Order is Complete!', SUCCESS);
        dmE.setDescription(`Great news! Your order **\`${orderId}\`** has been completed.\n\n📦 **Result:** ${details}\n💰 **Amount:** €${priceVal.toFixed(2)}\n\nThank you for choosing BrawlCarry! Consider leaving a vouch ⭐`);
        await customer.send({ embeds: [dmE] });
      }
    } catch (_) {}
  }

  await interaction.followUp({ content: '✅ Order marked as completed!', ephemeral: true });
}

module.exports = {
  handleRankedPanelBtn,
  handlePrestigePanelBtn,
  handleSelect,
  handleConfirm,
  handleConfirmPrestige,
  handlePrestigeTrophyModal,
  handleRankedModal,
  handlePrestigeModal,
  handleButton,
  handlePublishModal,
  handleOrderCompleteModal,
};
