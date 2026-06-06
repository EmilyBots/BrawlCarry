const {
  ModalBuilder, TextInputBuilder, TextInputStyle,
  ActionRowBuilder, ButtonBuilder, ButtonStyle,
  StringSelectMenuBuilder, StringSelectMenuOptionBuilder,
  EmbedBuilder,
  ContainerBuilder, TextDisplayBuilder, SeparatorBuilder, MediaGalleryBuilder, MessageFlags,
} = require('discord.js');
const { queryOne, queryAll, getConfig } = require('../db/index');
const { baseEmbed } = require('../utils/embeds');
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

// Desired ranks above Masters I → random queue forced by game, Carry impossible
const CARRY_RESTRICTED_DESIRED = new Set(['Masters II', 'Masters III', 'Pro']);

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

/** Build desired rank options, filtered to only ranks above currentRank. */
function buildDesiredRankOptions(currentRank) {
  const ci = ALL_RANKS.indexOf(currentRank);
  return DESIRED_RANKS
    .filter(r => r === 'Pro' || ALL_RANKS.indexOf(r) > ci)
    .map(r => new StringSelectMenuOptionBuilder().setLabel(r).setValue(r).setEmoji(rankEmoji(r) || undefined));
}

/** Build desired options, filtered to levels above currentPrestige. */
function buildDesiredPrestigeOptions(currentPrestige) {
  const ci = PRESTIGE_LEVELS.indexOf(currentPrestige);
  return PRESTIGE_LEVELS.slice(ci + 1).map(p =>
    new StringSelectMenuOptionBuilder().setLabel(p).setValue(p).setEmoji(PREST_DESIRED_EMOJI[p] || undefined)
  );
}


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


function buildRankedSvcOptions(desiredRank) {
  const boostOption = new StringSelectMenuOptionBuilder()
    .setLabel('B00st')
    .setValue('boost')
    .setDescription('We play on your account - Standard service')
    .setEmoji('<:Boost:1508378809676861573>');

  if (desiredRank && CARRY_RESTRICTED_DESIRED.has(desiredRank)) {
    return [
      boostOption,
      new StringSelectMenuOptionBuilder()
        .setLabel('Carry is unavailable')
        .setValue('carry_unavailable')
        .setDescription('Matches at this rank are random queue only')
        .setEmoji('<:sold:1507693147306852515>'),
    ];
  }

  return [
    boostOption,
    new StringSelectMenuOptionBuilder()
      .setLabel('Carry')
      .setValue('carry')
      .setDescription('We play with you (2× Price)')
      .setEmoji('<:Carry:1510590429052272660>'),
  ];
}

// ── Service Type selection embed (ComponentsV2) ───────────────────────────────
function buildSvcTypeEmbed(orderType, carryRestricted = false) {
  return new ContainerBuilder()
    .setAccentColor(PRIMARY)
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent(
        `## <:info:1508767700329959545> Choose Your Service Type\n` +
        `### Select your preferred service type:`
      )
    )
    .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent(
        `### <:Boost:1508378809676861573> **B00st**\n` +
        `> <:arrow:1509857611816763482> A b00ster will play on your account and reach your desired rank for you.\n` +
        `> <:arrow:1509857611816763482> __Fastest__ and most __affordable__ option`
      )
    )
    .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent(
        `### <:Carry:1510590429052272660> **Carry** __(2× Price)__\n` +
        `> <:arrow:1509857611816763482> A b00ster will play alongside you throughout the order.\n` +
        `> <:arrow:1509857611816763482> __No__ account access required.\n` +
        `> -# <:warning:1508835752430141482> Carry orders cost 2× more because they are harder to provide.`
      )
    )
    .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
    .addActionRowComponents(
      new ActionRowBuilder().addComponents(
        new ButtonBuilder()
          .setCustomId(`svc_boost_${orderType}`)
          .setLabel('Select B00st')
          .setStyle(ButtonStyle.Success)
          .setEmoji({ name: 'Boost', id: '1508378809676861573' }),
        new ButtonBuilder()
          .setCustomId(`svc_carry_${orderType}`)
          .setLabel(carryRestricted ? 'Carry Unavailable' : 'Select Carry')
          .setStyle(ButtonStyle.Secondary)
          .setEmoji({ name: 'Carry', id: '1510590429052272660' })
          .setDisabled(carryRestricted),
      )
    );
}

async function handleSvcProceedBtn(interaction) {
  const id         = interaction.customId;
  const state      = getState(interaction.user.id);
  const isPrestige = id.startsWith('prest_');

  if (!isPrestige) {
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

    return handleRankedSvcSubmit(interaction, state);
  } else {
    const missing = [];
    if (!state.currentPrestige) missing.push('Current Prestige');
    if (!state.desiredPrestige) missing.push('Desired Prestige');
    if (!state.payment)         missing.push('Payment Method');
    if (missing.length) return interaction.reply({ content: `❌ Please fill in: **${missing.join(', ')}**`, ephemeral: true });

    const ci = PRESTIGE_LEVELS.indexOf(state.currentPrestige);
    const di = PRESTIGE_LEVELS.indexOf(state.desiredPrestige);
    if (di <= ci) return interaction.reply({ content: '❌ Desired Prestige must be higher than Current Prestige.', ephemeral: true });

    return handlePrestigeSvcSubmit(interaction, state);
  }
}

// ── Panel buttons ─────────────────────────────────────────────────────────────
async function handleRankedPanelBtn(interaction) {
  orderState.delete(interaction.user.id);
  await interaction.reply({
    components: [buildSvcTypeEmbed('ranked', false)],
    flags: MessageFlags.IsComponentsV2,
    ephemeral: true,
  });
}

async function handlePrestigePanelBtn(interaction) {
  orderState.delete(interaction.user.id);
  await interaction.reply({
    components: [buildSvcTypeEmbed('prestige', false)],
    flags: MessageFlags.IsComponentsV2,
    ephemeral: true,
  });
}
// ── Order config helpers — shown after service type is chosen ─────────────────
async function showRankedConfig(interaction) {
  const guildId = interaction.guildId;
  const methods = await getPaymentMethods(guildId);
  const currentOptions = CURRENT_RANKS.map(r =>
    new StringSelectMenuOptionBuilder().setLabel(r).setValue(r).setEmoji(rankEmoji(r) || undefined)
  );
  const p11Options = P11_OPTIONS.map(p =>
    new StringSelectMenuOptionBuilder().setLabel(p).setValue(p).setEmoji(P11_EMOJI)
  );
  const payOptions = methods.map(m =>
    new StringSelectMenuOptionBuilder().setLabel(m.label).setValue(m.label).setEmoji(m.emoji || undefined)
  );
  const e = baseEmbed('<:master:1491521740860428459> Ranked Order', PRIMARY);
  e.setDescription('>>> **Complete your ranked order by selecting the options below.**');
  return interaction.reply({
    embeds: [e],
    components: [
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder()
          .setCustomId('ranked_current')
          .setPlaceholder('Select Current Rank')
          .addOptions(currentOptions)
      ),
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder()
          .setCustomId('ranked_desired')
          .setPlaceholder('Select Current Rank First...')
          .setDisabled(true)
          .addOptions(new StringSelectMenuOptionBuilder().setLabel('—').setValue('placeholder'))
      ),
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder()
          .setCustomId('ranked_p11')
          .setPlaceholder('Power 11 brawlers...')
          .addOptions(p11Options)
      ),
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder()
          .setCustomId('ranked_pay')
          .setPlaceholder('Payment method...')
          .addOptions(payOptions)
      ),
    ],
    ephemeral: true,
  });
}

async function showPrestigeConfig(interaction) {
  const guildId = interaction.guildId;
  const methods = await getPaymentMethods(guildId);
  const currentOptions = ['Prestige 0', 'Prestige 1', 'Prestige 2'].map(p =>
    new StringSelectMenuOptionBuilder().setLabel(p).setValue(p).setEmoji(PREST_CURRENT_EMOJI[p] || undefined)
  );
  const payOptions = methods.map(m =>
    new StringSelectMenuOptionBuilder().setLabel(m.label).setValue(m.label).setEmoji(m.emoji || undefined)
  );
  const e = baseEmbed('<:P3:1508147370947252345> Prestige Order', ACCENT);
  e.setDescription('>>> **Complete your prestige order by selecting the options below.**');
  return interaction.reply({
    embeds: [e],
    components: [
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder()
          .setCustomId('prest_current')
          .setPlaceholder('Current Prestige...')
          .addOptions(currentOptions)
      ),
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder()
          .setCustomId('prest_desired')
          .setPlaceholder('Desired Prestige (select Current first)...')
          .setDisabled(true)
          .addOptions(new StringSelectMenuOptionBuilder().setLabel('—').setValue('placeholder'))
      ),
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder()
          .setCustomId('prest_pay')
          .setPlaceholder('Payment method...')
          .addOptions(payOptions)
      ),
    ],
    ephemeral: true,
  });
}
// ── Select handlers ───────────────────────────────────────────────────────────
async function handleSelect(interaction) {
  const id    = interaction.customId;
  const value = interaction.values[0];
  const state = getState(interaction.user.id);

  // ── RANKED ────────────────────────────────────────────────────────────────
  if (id === 'ranked_current') {
    state.currentRank = value;
    state.desiredRank = null;
    state.rankedProgressed = false; // reset flag se l'utente cambia current
    const methods = await getPaymentMethods(interaction.guildId);
    const currentOptions = CURRENT_RANKS.map(r => new StringSelectMenuOptionBuilder().setLabel(r).setValue(r).setEmoji(rankEmoji(r) || undefined).setDefault(r === value));
    const desiredOptions = buildDesiredRankOptions(value);
    const p11Options     = P11_OPTIONS.map(p => new StringSelectMenuOptionBuilder().setLabel(p).setValue(p).setEmoji(P11_EMOJI));
    const payOptions     = methods.map(m => new StringSelectMenuOptionBuilder().setLabel(m.label).setValue(m.label).setEmoji(m.emoji || undefined));
    await interaction.update({ components: [
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder().setCustomId('ranked_current').setPlaceholder('Select Current Rank').addOptions(currentOptions)
      ),
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder().setCustomId('ranked_desired').setPlaceholder('Select Desired Rank').setDisabled(false).addOptions(desiredOptions)
      ),
      new ActionRowBuilder().addComponents(new StringSelectMenuBuilder().setCustomId('ranked_p11').setPlaceholder('Number of Power 11 brawlers...').addOptions(p11Options)),
      new ActionRowBuilder().addComponents(new StringSelectMenuBuilder().setCustomId('ranked_pay').setPlaceholder('Payment method...').addOptions(payOptions)),
    ]});
    return;
  }

  if (id === 'ranked_desired') {
    state.desiredRank = value;
    // Se tutti i campi sono già completi, vai direttamente alla submit SENZA update prima
    if (!state.rankedProgressed && state.currentRank && state.p11 && state.payment) {
      state.rankedProgressed = true;
      return handleRankedSvcSubmit(interaction, state);
    }
    // Altrimenti aggiorna solo la UI
    const methods = await getPaymentMethods(interaction.guildId);
    const currentOptions = CURRENT_RANKS.map(r =>
      new StringSelectMenuOptionBuilder().setLabel(r).setValue(r).setEmoji(rankEmoji(r) || undefined).setDefault(r === state.currentRank)
    );
    const desiredOptions = DESIRED_RANKS
      .filter(r => r === 'Pro' || ALL_RANKS.indexOf(r) > ALL_RANKS.indexOf(state.currentRank))
      .map(r => new StringSelectMenuOptionBuilder().setLabel(r).setValue(r).setEmoji(rankEmoji(r) || undefined).setDefault(r === value));
    const p11Options = P11_OPTIONS.map(p => new StringSelectMenuOptionBuilder().setLabel(p).setValue(p).setEmoji(P11_EMOJI));
    const payOptions = methods.map(m => new StringSelectMenuOptionBuilder().setLabel(m.label).setValue(m.label).setEmoji(m.emoji || undefined));
    await interaction.update({ components: [
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder().setCustomId('ranked_current').setPlaceholder('Select Current Rank').addOptions(currentOptions)
      ),
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder().setCustomId('ranked_desired').setPlaceholder('Select Desired Rank').setDisabled(false).addOptions(desiredOptions)
      ),
      new ActionRowBuilder().addComponents(new StringSelectMenuBuilder().setCustomId('ranked_p11').setPlaceholder('Number of Power 11 brawlers...').addOptions(p11Options)),
      new ActionRowBuilder().addComponents(new StringSelectMenuBuilder().setCustomId('ranked_pay').setPlaceholder('Payment method...').addOptions(payOptions)),
    ]});
    return;
  }

  if (id === 'ranked_p11') {
    state.p11 = value;
    if (!state.rankedProgressed && state.currentRank && state.desiredRank && state.payment) {
      state.rankedProgressed = true;      
      return handleRankedSvcSubmit(interaction, state);
    }
    return interaction.deferUpdate();
  }

  if (id === 'ranked_pay') {
    state.payment = value;
    if (!state.rankedProgressed && state.currentRank && state.desiredRank && state.p11) {
      state.rankedProgressed = true;      
      return handleRankedSvcSubmit(interaction, state);
    }
    return interaction.deferUpdate();
  }

  // ── PRESTIGE ──────────────────────────────────────────────────────────────
  if (id === 'prest_current') {
    state.currentPrestige = value;
    state.desiredPrestige = null;
    state.prestigeProgressed = false; // reset flag se l'utente cambia current
    const methods = await getPaymentMethods(interaction.guildId);
    const currentOptions = ['Prestige 0', 'Prestige 1', 'Prestige 2'].map(p =>
      new StringSelectMenuOptionBuilder().setLabel(p).setValue(p).setEmoji(PREST_CURRENT_EMOJI[p] || undefined).setDefault(p === value)
    );
    const desiredOptions = buildDesiredPrestigeOptions(value);
    const payOptions = methods.map(m =>
      new StringSelectMenuOptionBuilder().setLabel(m.label).setValue(m.label).setEmoji(m.emoji || undefined)
    );
    await interaction.update({ components: [
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder().setCustomId('prest_current').setPlaceholder('Current Prestige...').addOptions(currentOptions)
      ),
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder().setCustomId('prest_desired').setPlaceholder('Desired Prestige...').setDisabled(false).addOptions(desiredOptions)
      ),
      new ActionRowBuilder().addComponents(
        new StringSelectMenuBuilder().setCustomId('prest_pay').setPlaceholder('Payment method...').addOptions(payOptions)
      ),
    ]});
    return;
  }

  if (id === 'prest_desired') {
    state.desiredPrestige = value;
    if (!state.prestigeProgressed && state.currentPrestige && state.payment) {
      state.prestigeProgressed = true;
     return handlePrestigeSvcSubmit(interaction, state);
    }
    return interaction.deferUpdate();
  }

  if (id === 'prest_pay') {
    state.payment = value;
    if (!state.prestigeProgressed && state.currentPrestige && state.desiredPrestige) {
      state.prestigeProgressed = true;
      return handlePrestigeSvcSubmit(interaction, state);
    }
    return interaction.deferUpdate();
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
  const svcEmoji = state.serviceType === 'carry' ? '<:Carry:1510590429052272660>' : '<:Boost:1508378809676861573>';
  const svcLabel = state.serviceType === 'carry' ? 'Ranked Carry' : 'Ranked B00st';
  const payEmoji = await getPaymentEmoji(state.payment, interaction.guildId);
  const e  = baseEmbed(`<:info:1508767700329959545> Review Your ${svcLabel} Order`, PRIMARY);
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
    new ButtonBuilder().setCustomId('ranked_confirm').setLabel('Confirm & Continue').setStyle(ButtonStyle.Success).setEmoji('<:Yes:1508365664778190878>'),
    new ButtonBuilder().setCustomId('ranked_edit').setLabel('Edit Order').setStyle(ButtonStyle.Secondary).setEmoji('<:Change:1508511751698645002>'),
    new ButtonBuilder().setCustomId('ranked_close').setLabel('Close Order').setStyle(ButtonStyle.Danger).setEmoji('<:sold:1507693147306852515>'),
  );
  await interaction.update({ embeds: [e], components: [view] });
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
    return handleRankedModal(interaction);
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

  const svcEmoji  = state.serviceType === 'carry' ? '<:Carry:1510590429052272660>' : '<:Boost:1508378809676861573>';
  const svcLabel  = state.serviceType === 'carry' ? 'Prestige Carry' : 'Prestige B00st';
  const pe        = PREST_CURRENT_EMOJI[state.currentPrestige] ?? '✨';
  const de        = PREST_DESIRED_EMOJI[state.desiredPrestige]  ?? '✨';
  const payEmoji  = await getPaymentEmoji(state.payment, interaction.guildId);
  const e  = baseEmbed(`<:info:1508767700329959545> Review Your ${svcLabel} Order`, ACCENT);
  e.setDescription(
    `## Please double-check your prestige order details before creating your ticket.\n\n` +
    `**Order Type** ${svcEmoji}\n<:reply:1507680110843658260> **${svcLabel}**\n\n` +
    `**Current Prestige** ${pe}\n<:reply:1507680110843658260> **${state.currentPrestige}**\n\n` +
    `**Desired Prestige** ${de}\n<:reply:1507680110843658260> **${state.desiredPrestige}**\n\n` +
    `**Current Trophies** <:Trophies:1485658086156013598>\n<:reply:1507680110843658260> **${trophyVal.toLocaleString()}**\n\n` +
    `**Selected Brawler** <:user:1491499694734708815>\n<:reply:1507680110843658260> **${brawler}**\n\n` +
    `**Estimated Price** <:Amount:1501221154650853450>\n<:reply:1507680110843658260> **${est.toFixed(2)}€**\n\n` +
    `**Payment Method** ${payEmoji}\n<:reply:1507680110843658260> **${state.payment}**`
  );

  const view = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('prestige_confirm').setLabel('Confirm & Continue').setStyle(ButtonStyle.Success).setEmoji('<:Yes:1508365664778190878>'),
    new ButtonBuilder().setCustomId('prestige_edit').setLabel('Edit Order').setStyle(ButtonStyle.Secondary).setEmoji('<:Change:1508511751698645002>'),
    new ButtonBuilder().setCustomId('prestige_close').setLabel('Close Order').setStyle(ButtonStyle.Danger).setEmoji('<:sold:1507693147306852515>'),
  );
  await interaction.reply({ embeds: [e], components: [view], ephemeral: true });
}


async function handleConfirmPrestige(interaction) {
  return handlePrestigeModal(interaction);
}
// ── Edit Order — reopens the order config select menus ────────────────────────
async function handleEditOrder(interaction) {
  const id      = interaction.customId; // 'ranked_edit' or 'prestige_edit'
  const userId  = interaction.user.id;
  const state   = getState(userId);     // preserve existing state
  state.rankedProgressed   = false;
  state.prestigeProgressed = false;
  const guildId = interaction.guildId;
  const methods = await getPaymentMethods(guildId);

  if (id === 'ranked_edit') {
    const currentOptions = CURRENT_RANKS.map(r =>
      new StringSelectMenuOptionBuilder().setLabel(r).setValue(r).setEmoji(rankEmoji(r) || undefined)
        .setDefault(r === state.currentRank)
    );
    const desiredOptions = state.currentRank
      ? buildDesiredRankOptions(state.currentRank).map(o => {
          const isDefault = o.data?.value === state.desiredRank || o.toJSON?.()?.value === state.desiredRank;
          return isDefault ? o.setDefault(true) : o;
        })
      : [new StringSelectMenuOptionBuilder().setLabel('—').setValue('placeholder')];
    const p11Options = P11_OPTIONS.map(p =>
      new StringSelectMenuOptionBuilder().setLabel(p).setValue(p).setEmoji(P11_EMOJI).setDefault(p === state.p11)
    );
    const payOptions = methods.map(m =>
      new StringSelectMenuOptionBuilder().setLabel(m.label).setValue(m.label).setEmoji(m.emoji || undefined).setDefault(m.label === state.payment)
    );
    const e = baseEmbed('<:master:1491521740860428459> Ranked Order', PRIMARY);
    e.setDescription('>>> **Complete your ranked order by selecting the options below.**');

    return interaction.update({
      embeds: [e],
      components: [
        new ActionRowBuilder().addComponents(
          new StringSelectMenuBuilder().setCustomId('ranked_current').setPlaceholder('Select Current Rank').addOptions(currentOptions)
        ),
        new ActionRowBuilder().addComponents(
          new StringSelectMenuBuilder().setCustomId('ranked_desired')
            .setPlaceholder('Select Desired Rank')
            .setDisabled(!state.currentRank)
            .addOptions(state.currentRank ? desiredOptions : [new StringSelectMenuOptionBuilder().setLabel('—').setValue('placeholder')])
        ),
        new ActionRowBuilder().addComponents(
          new StringSelectMenuBuilder().setCustomId('ranked_p11').setPlaceholder('Number of Power 11 brawlers...').addOptions(p11Options)
        ),
        new ActionRowBuilder().addComponents(
          new StringSelectMenuBuilder().setCustomId('ranked_pay').setPlaceholder('Payment method...').addOptions(payOptions)
        ),
      ],
    });
  }

  if (id === 'prestige_edit') {
    const currentOptions = ['Prestige 0', 'Prestige 1', 'Prestige 2'].map(p =>
      new StringSelectMenuOptionBuilder().setLabel(p).setValue(p).setEmoji(PREST_CURRENT_EMOJI[p] || undefined).setDefault(p === state.currentPrestige)
    );
    const desiredOptions = state.currentPrestige
      ? buildDesiredPrestigeOptions(state.currentPrestige).map(o => {
          const isDefault = o.data?.value === state.desiredPrestige || o.toJSON?.()?.value === state.desiredPrestige;
          return isDefault ? o.setDefault(true) : o;
        })
      : [new StringSelectMenuOptionBuilder().setLabel('—').setValue('placeholder')];
    const payOptions = methods.map(m =>
      new StringSelectMenuOptionBuilder().setLabel(m.label).setValue(m.label).setEmoji(m.emoji || undefined).setDefault(m.label === state.payment)
    );
    const e = baseEmbed('<:P3:1508147370947252345> Prestige Order', ACCENT);
    e.setDescription('>>> **Complete your prestige order by selecting the options below.**');

    return interaction.update({
      embeds: [e],
      components: [
        new ActionRowBuilder().addComponents(
          new StringSelectMenuBuilder().setCustomId('prest_current').setPlaceholder('Current Prestige...').addOptions(currentOptions)
        ),
        new ActionRowBuilder().addComponents(
          new StringSelectMenuBuilder().setCustomId('prest_desired')
            .setPlaceholder('Desired Prestige...')
            .setDisabled(!state.currentPrestige)
            .addOptions(state.currentPrestige ? desiredOptions : [new StringSelectMenuOptionBuilder().setLabel('—').setValue('placeholder')])
        ),
        new ActionRowBuilder().addComponents(
          new StringSelectMenuBuilder().setCustomId('prest_pay').setPlaceholder('Payment method...').addOptions(payOptions)
        ),
      ],
    });
  }
}

// ── Close Order — cancels the order flow and clears session ───────────────────
async function handleCloseOrder(interaction) {
  orderState.delete(interaction.user.id);

  const e = baseEmbed('<:sold:1507693147306852515> Order Cancelled', DANGER);
  e.setDescription('Your order has been cancelled.\n\nAll selections have been cleared. You can start a new order at any time.');

  return interaction.update({ embeds: [e], components: [] });
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
  const modeEmoji = state.serviceType === 'carry' ? '<:Carry:1510590429052272660>' : '<:Boost:1508378809676861573>';

  const activatedE = baseEmbed('<:Boost:1508378809676861573> Order Ticket', PRIMARY);
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
    return interaction.followUp({ content: `❌ Failed to create ticket: \`${err.message}\`\n\nAsk an admin to check \`/setup\` channel permissions.`, ephemeral: true });
  }

  await queryOne('UPDATE orders SET ticket_channel_id = $1 WHERE id = $2', [ticket.id, orderId]);

  const orderE = baseEmbed('<:info:1508767700329959545> Order Details', PRIMARY);
  orderE.setDescription(`## Your Ranked ${modeClean} Order`);
  orderE.addFields(
    { name: `Current Rank ${fe}`,       value: `→ ${state.currentRank}`,  inline: false },
    { name: `Desired Rank ${te}`,       value: `→ ${state.desiredRank}`,  inline: false },
    { name: 'Power Level <:copyright:1489943698203480214>', value: `→ ${state.p11} Power 11`, inline: false },
    { name: `Order Type ${modeEmoji}`,  value: `→ ${modeClean}`,          inline: false },
    { name: `Payment Method ${payEmoji}`, value: `→ ${state.payment}`,    inline: false },
    { name: '<:Amount:1501221154650853450> Estimated Price', value: `** ╔══ €${(state.estimatedPrice ?? 0).toFixed(2)}  ══╗**` inline: false },
  );

  const publishView = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`send_boosters_${orderId}`).setLabel('Send to Boosters').setStyle(ButtonStyle.Primary).setEmoji('<:Boost:1508378809676861573>')
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

  const activatedE = baseEmbed('<:Boost:1508378809676861573> Order Ticket', ACCENT);
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

  const orderE = baseEmbed('<:info:1508767700329959545> Order Details', ACCENT);
  orderE.setDescription(`## Your Prestige ${modeClean} Order`);
  orderE.addFields(
    { name: `Prestige ${pe}`,                          value: `→ ${specLabel}`,                                                                    inline: false },                                                           
    { name: '<:user:1491499694734708815> Brawler',      value: `→ **${state.brawlerName}**`,                                                        inline: false },
    { name: '<:copyright:1485658086156013598> Trophies', value: `→ **${state.trophyVal?.toLocaleString() ?? '—'}**`,                                inline: false },
    { name: `${state.serviceType === 'carry' ? '<:Carry:1510590429052272660>' : '<:Boost:1508378809676861573>'} Order Type`, value: `→ **${modeClean}**`, inline: false },
    { name: `${payEmoji} Payment Method`,               value: `→ **${state.payment}**`,                                                            inline: false },
    { name: '<:Amount:1501221154650853450> Estimated Price', value: `**╔══ €${(state.estimatedPrice ?? 0).toFixed(2)} ══╗**`                    inline: false },
  );

  const publishView = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`send_boosters_${orderId}`).setLabel('Send to Boosters').setStyle(ButtonStyle.Primary).setEmoji('<:Boost:1508378809676861573>')
  );
  await ticket.send({ embeds: [orderE], components: [publishView] });
    // ✅ editReply instead of reply (interaction is already deferred)
  await interaction.editReply({ content: `✅ Your Prestige order has been placed!\n📩 Ticket opened: ${ticket.toString()}` });
  orderState.delete(interaction.user.id);
}

// ── Send to boosters button ───────────────────────────────────────────────────
async function handleButton(interaction, client) {
  const id = interaction.customId;

  

  if (id.startsWith('svc_boost_') || id.startsWith('svc_carry_')) {
    const parts     = id.split('_');     // ['svc', 'boost'|'carry', 'ranked'|'prestige']
    const svcType   = parts[1];          // 'boost' or 'carry'
    const orderType = parts[2];          // 'ranked' or 'prestige'
    const state     = getState(interaction.user.id);
    state.serviceType = svcType;
    if (orderType === 'ranked')   return showRankedConfig(interaction);
    if (orderType === 'prestige') return showPrestigeConfig(interaction);
  }

  if (id.startsWith('send_boosters_') || id === 'order_publish_btn_v1') {
    if (!interaction.member?.roles?.cache?.has('1479079737052762205')) {
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
  const svcEmoji = svcType === 'carry' ? '<:Carry:1510590429052272660>' : '<:Boost:1508378809676861573>';
  const details    = buildOrderDetailsStr(orderType, fromTier, toTier, svcType);

  // Build dynamic detail line for claim embed
  let detailLine;
  if (orderType === 'prestige') {
    const fromEmoji = PREST_CURRENT_EMOJI[fromTier] ?? '';
    const toEmoji   = PREST_DESIRED_EMOJI[toTier]   ?? '';
    detailLine = `${fromEmoji} \`${fromTier}\` <:arrow:1508833071137554572> ${toEmoji} \`${toTier}\``;
  } else {
    const fromEmoji = rankEmoji(fromTier) ?? '';
    const toEmoji   = rankEmoji(toTier)   ?? '';
    detailLine = `${fromEmoji} \`${fromTier}\` <:arrow:1508833071137554572> ${toEmoji} \`${toTier}\``;
  }

  const powerLine = order.p11_count ? `\`${order.p11_count}\`` : null;
  const svcText   = svcType === 'carry' ? 'Carry' : 'B00st';
  const svcEmojiClaim = svcType === 'carry' ? '<:Carry:1510590429052272660>' : '<:Boost:1508378809676861573>';

  const thumbnailId = svcType === 'carry' ? '1510590429052272660' : '1508378809676861573';

  const claimE = new EmbedBuilder()
    .setColor(color)
    .setThumbnail(`https://cdn.discordapp.com/emojis/${thumbnailId}.png`)
    .setDescription(
      `## <:ticket:1508838977602457723> New ${label} Order\n` +
      `### You Earn <:Amount:1501221154650853450>\n` +
      `<:arrow:1509857611816763482> **€${earnings.toFixed(2)}**\n` +
      `### Order Type ${svcEmojiClaim}\n` +
      `<:arrow:1509857611816763482> ${label} **\`${svcText}\`**\n` +
      (powerLine ? `### Power <:P11:1512113473289720070>\n<:arrow:1509857611816763482> **${order.p11_count}**\n` : '') +
      (orderType === 'prestige' && order.trophy_val ? `### Trophies <:Trophies:1485658086156013598>\n<:arrow:1509857611816763482> **\`${parseInt(order.trophy_val).toLocaleString()}\`**\n` : '') +
      `### Order Details <:info:1508767700329959545>\n` +
      `<:arrow:1509857611816763482> ${detailLine}\n` +
      `### Claimed By <:verified:1508838509883162786>\n` +
      `<:arrow:1509857611816763482> **\`Nobody\`**`
    );

  const claimView = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`booster_claim:${ctx.orderId}`).setLabel('Claim Order').setStyle(ButtonStyle.Success).setEmoji('<:claim:1512088775759626260>'),
    new ButtonBuilder().setCustomId(`booster_unclaim:${ctx.orderId}`).setLabel('Unclaim Order').setStyle(ButtonStyle.Danger).setEmoji('<:Unclaim:1512089273380110418>').setDisabled(true),
  );

  await panelCh.send({ content: '<@&1485296409795235910>', allowedMentions: { roles: ['1485296409795235910'] }, embeds: [claimE], components: [claimView] });
  await interaction.followUp({ content: `✅ Order \`${ctx.orderId}\` published to ${panelCh} with **€${earnings.toFixed(2)}** booster earnings.`, ephemeral: true });
}

// ── Claim ─────────────────────────────────────────────────────────────────────
async function handleClaim(interaction, orderId, client) {
  const booster = interaction.member;
  const guild   = interaction.guild;

  if (!booster.roles.cache.has('1485296409795235910')) {
    return interaction.reply({ content: '<:sold:1507693147306852515> Only B00ster can claim orders!', ephemeral: true });
  }

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
      const oldDesc = origEmbed.description ?? '';
      const newDesc = oldDesc.replace(
        /(<:arrow:1509857611816763482> \*\*`Nobody`\*\*)/,
        `<:arrow:1509857611816763482> ${booster.toString()}`
      );
      const updated = EmbedBuilder.from(origEmbed).setColor(SUCCESS).setDescription(newDesc);
      const updatedView = ActionRowBuilder.from(interaction.message.components[0]);
      updatedView.components[1].setDisabled(false); // abilita Unclaim
      updatedView.components[0].setDisabled(true);  // disabilita Claim
      await interaction.message.edit({ embeds: [updated], components: [updatedView] });
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

        // Grant booster temporary ViewChannel on the workspace parent channel
        if (workspace.parent) {
          try {
            await workspace.parent.permissionOverwrites.edit(booster.id, { ViewChannel: true }, { reason: 'Temporary booster access for claimed order' });
          } catch (_) {}
        }

        const staffPings = HARDCODED_SUPPORT_ROLES.map(r => `<@&${r}>`).join(' ');
        await workspace.send({ content: staffPings, allowedMentions: { parse: ['roles'] } });

        const details      = buildOrderDetailsStr(order.order_type ?? 'ranked', order.from_tier ?? '?', order.to_tier ?? '?', order.service_type ?? 'boost');
        const orderLabel   = (order.order_type ?? 'ranked').charAt(0).toUpperCase() + (order.order_type ?? 'ranked').slice(1);
        const svcLabel     = (order.service_type ?? 'boost').charAt(0).toUpperCase() + (order.service_type ?? 'boost').slice(1);
        const svcEmoji = order.service_type === 'carry' ? '<:Carry:1510590429052272660>' : '<:Boost:1508378809676861573>';
        const custMention  = customer?.toString() ?? `<@${order.user_id}>`;

        const orderEmbed = baseEmbed(`<:diamound:1491491246546616340> Active ${orderLabel} ${svcLabel} Order`, SUCCESS);
        orderEmbed.addFields(
          { name: '<:Customer:1501221119900778506> Customer', value: `↳ ${custMention}`,      inline: false },
          { name: '<:user:1491499694734708815> B00ster',      value: `↳ ${booster.toString()}`, inline: false },
          { name: `${svcEmoji} Order Type`,                   value: `↳ **${svcLabel}**`,      inline: false },
          { name: '<:info:1508767700329959545> Order Details', value: `↳ ${details}`,           inline: false },
        );
        await workspace.send({ embeds: [orderEmbed] });

        const safetyEmbed = baseEmbed('⚠️ Reminder', GOLD);
        safetyEmbed.setDescription('**Never DM the booster directly.**\n\nAlways use this thread for communication.\n\nThis helps prevent scams and keeps everything tracked safely.\n\n**Any attempt to bypass this rule by either the customer or the booster may result in consequences.**');
        const closeView = new ActionRowBuilder().addComponents(
          new ButtonBuilder().setCustomId('ticket_close_v2').setLabel('Close Ticket').setStyle(ButtonStyle.Danger).setEmoji('🔒')
        );
        await workspace.send({ embeds: [safetyEmbed], components: [closeView] });

        // Notify original ticket
        const notifyE = baseEmbed('<:Boost:1508378809676861573> B00ster Assigned', SUCCESS);
        notifyE.setDescription(`${booster.toString()} has successfully claimed your order.\n\nA private thread has been created.\n\nPlease continue all communication inside the private thread.`);
        await ticketCh.send({ embeds: [notifyE] }).catch(() => {});
        await updateTicketActivity(ticketChId, guild.id);

        // DM booster
        try {
          const dmE = baseEmbed('<:Boost:1508378809676861573> Order Claimed!', SUCCESS);
          dmE.setDescription(`You've successfully claimed order ${workspace.toString()}!\n\nHead to the ticket to begin.`);
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
      const oldDesc = origEmbed.description ?? '';
      const newDesc = oldDesc.replace(
        /(<:arrow:1509857611816763482> )<@!?\d+>/,
        `$1**\`Nobody\``+ '**'
      );
      const updated = EmbedBuilder.from(origEmbed).setColor(PRIMARY).setDescription(newDesc);
      const restoredView = ActionRowBuilder.from(interaction.message.components[0]);
      restoredView.components[0].setDisabled(false); // riabilita Claim
      restoredView.components[1].setDisabled(true);  // disabilita Unclaim
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
  const applyWm  = interaction.fields.getTextInputValue('apply_watermark').trim().toLowerCase() === 'yes';

  const order = await queryOne('SELECT * FROM orders WHERE id = $1', [orderId]);
  if (!order) return interaction.followUp({ content: `❌ Order \`${orderId}\` not found.`, ephemeral: true });
  if (order.status === 'completed') return interaction.followUp({ content: `❌ Order \`${orderId}\` is already completed.`, ephemeral: true });

  const priceVal       = parseFloat(priceStr) || order.price || 0;
  const claimedAt      = order.claimed_at ? new Date(order.claimed_at) : null;
  const now            = new Date();
  const completionSecs = claimedAt ? Math.floor((now - claimedAt) / 1000) : null;

  await queryOne(
    "UPDATE orders SET status = 'completed', price = $1, completed_at = $2, completion_time_seconds = $3 WHERE id = $4",
    [priceVal, now, completionSecs, orderId]
  );

  const guild          = interaction.guild;
  const cfg            = await getConfig(guild.id);
  const completedChId  = cfg?.completed_channel_id ? String(cfg.completed_channel_id) : null;
  const completedCh    = completedChId ? guild.channels.cache.get(completedChId) : null;
  const customer       = order.user_id ? guild.members.cache.get(String(order.user_id)) : null;

  const svcType        = order.service_type ?? 'boost';
  const ordType        = order.order_type   ?? 'ranked';
  const details        = buildOrderDetailsStr(ordType, order.from_tier ?? '', order.to_tier ?? '', svcType);
  const payEmoji       = await getPaymentEmoji(order.method, interaction.guildId);
  const custMention    = customer?.toString() ?? `<@${order.user_id}>`;
  const baseType       = ordType === 'prestige' ? 'Prestige' : ordType === 'account' ? 'Account' : 'Ranked';
  const modeEmoji      = svcType === 'carry' ? '<:Carry:1510590429052272660>' : '<:Boost:1508378809676861573>';
  const orderTitle     = ordType === 'account' ? '4CCOUNT ORDER' : `${baseType.toUpperCase()} ORDER`;

  let wm = null;
  if (imgUrl && applyWm) {
    try {
      wm = await fetchAndWatermark(imgUrl);
    } catch (err) {
      return interaction.followUp({ content: `❌ Watermark failed: \`${err?.message ?? err}\`\n\nUsa un link Imgur diretto (https://i.imgur.com/xxx.jpg).`, ephemeral: true });
    }
  }

  const container = new ContainerBuilder()
    .setAccentColor(SUCCESS)
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent(`## <:crown:1508833236464439356> ${orderTitle}`)
    )
    .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent(`### Customer <:client:1508831518858940607>\n<:arrow:1509857611816763482> ${custMention} ${payEmoji}`)
    )
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent(`### Order Amount <:Amount:1501221154650853450>\n<:arrow:1509857611816763482> **\`€${priceVal.toFixed(2)}\`**`)
    )
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent(`### Order Type ${modeEmoji}\n<:arrow:1509857611816763482> ${ordType === 'account' ? '4ccount' : `${baseType} ${svcType === 'carry' ? 'Carry' : 'B0ost'}`}`)
    );

  if (ordType !== 'account') {
    let detailsLine;
    if (ordType === 'prestige') {
      const fromEmoji = PREST_CURRENT_EMOJI[order.from_tier ?? ''] ?? '';
      const toEmoji   = PREST_DESIRED_EMOJI[order.to_tier   ?? ''] ?? '';
      detailsLine = `${fromEmoji} \`${order.from_tier}\` <:arrow:1508833071137554572> ${toEmoji} \`${order.to_tier}\``;
    } else {
      detailsLine = details.split('\n')[0].replace('→', '<:arrow:1508833071137554572>');
    }
    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(`### Order Details <:info:1508767700329959545>\n<:arrow:1509857611816763482> ${detailsLine}`)
    );
  }

  container.addSeparatorComponents(new SeparatorBuilder().setDivider(true));

  if (wm) {
    container
      .addMediaGalleryComponents(new MediaGalleryBuilder().addItems([{ media: { url: 'attachment://proof.jpg' } }]))
      .addSeparatorComponents(new SeparatorBuilder().setDivider(true));
  } else if (imgUrl && !applyWm) {
    container
      .addMediaGalleryComponents(new MediaGalleryBuilder().addItems([{ media: { url: imgUrl } }]))
      .addSeparatorComponents(new SeparatorBuilder().setDivider(true));
  }

  container.addActionRowComponents(
    new ActionRowBuilder().addComponents(
      new ButtonBuilder()
        .setLabel('Create Order')
        .setStyle(ButtonStyle.Link)
        .setEmoji({ name: 'Boost', id: '1508378809676861573' })
        .setURL(ordType === 'prestige'
          ? 'https://discord.com/channels/1355262062095372429/1355262063437414564'
          : 'https://discord.com/channels/1355262062095372429/1477338397570760784'
        )
    )
  );

  const sendArgs = { components: [container], flags: MessageFlags.IsComponentsV2, ...(wm ? { files: [wm] } : {}) };
  if (completedCh) await completedCh.send(sendArgs).catch(err => console.error('[WM] send fallito:', err?.message ?? err));
  else await interaction.channel.send(sendArgs).catch(err => console.error('[WM] send fallito:', err?.message ?? err));

  if (customer) {
    try {
      let fromEmoji = '', toEmoji = '';
      if (ordType === 'prestige') {
        fromEmoji = PREST_CURRENT_EMOJI[order.from_tier ?? ''] ?? '';
        toEmoji   = PREST_DESIRED_EMOJI[order.to_tier   ?? ''] ?? '';
      } else if (ordType !== 'account') {
        fromEmoji = rankEmoji(order.from_tier ?? '') ?? '';
        toEmoji   = rankEmoji(order.to_tier   ?? '') ?? '';
      }

      const dmE = baseEmbed('\u200b', SUCCESS);
      dmE.setTitle(null);
      dmE.setDescription(
        `# <:vip:1508831641135612068> Order Complete\n\n` +
        `### Your order has been completed <:Boost:1508378809676861573>\n\n` +
        `### <:info:1508767700329959545> Order Details\n` +
        `<:arrow:1509857611816763482> ${fromEmoji} \`${order.from_tier ?? ''}\` <:arrow:1508833071137554572> ${toEmoji} \`${order.to_tier ?? ''}\`\n\n` +
        `### <:Amount:1501221154650853450> Order Amount\n` +
        `<:arrow:1509857611816763482> **€${priceVal.toFixed(2)}**\n\n` +
        `-# Please leave a review in the button below<:verified:1508838509883162786>`
      );

      const reviewView = new ActionRowBuilder().addComponents(
        new ButtonBuilder()
          .setLabel('Leave Review')
          .setStyle(ButtonStyle.Link)
          .setEmoji({ name: 'ratingstar', id: '1511306314486386799', animated: true })
          .setURL(`https://discord.com/channels/${guild.id}/1477344147508822258`)
      );

      await customer.send({ embeds: [dmE], components: [reviewView] });
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
  handleEditOrder,
  handleCloseOrder,
  handlePrestigeTrophyModal,
  handleRankedModal,
  handlePrestigeModal,
  handleButton,
  handlePublishModal,
  handleOrderCompleteModal,
};
