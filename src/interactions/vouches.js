const {
  ModalBuilder, TextInputBuilder, TextInputStyle,
  ActionRowBuilder, ButtonBuilder, ButtonStyle,
  StringSelectMenuBuilder, StringSelectMenuOptionBuilder,
  EmbedBuilder,
  ContainerBuilder, TextDisplayBuilder, SeparatorBuilder, MessageFlags,
} = require('discord.js');
const { queryOne } = require('../db/index');
const { getConfig } = require('../db/index');
const { baseEmbed } = require('../utils/embeds');
const { prestigeEmoji } = require('../utils/pricing');
const { GOLD, FOOTER_BRAND } = require('../config/constants');
const { v4: uuidv4 } = require('uuid');

const CUSTOMER_ROLE_ID = '1484297795094581373';
const FALLBACK_VOUCH_CHANNEL_ID = '1477344147508822258';

// Per-user vouch selection state
const vouchState = new Map();

function getVouchState(userId) {
  if (!vouchState.has(userId)) vouchState.set(userId, {});
  return vouchState.get(userId);
}

// ── /vouch_btn button ─────────────────────────────────────────────────────────
async function handleButton(interaction) {
  const id        = interaction.customId;
  const orderKind = id.includes(':') ? id.split(':')[1] : 'ranked';
  const guildId   = interaction.guildId ?? '0';

  const member = interaction.guild?.members.cache.get(interaction.user.id) ?? interaction.member;
  if (!member?.roles.cache.has(CUSTOMER_ROLE_ID)) {
    return interaction.reply({ content: '❌ Only verified customers can submit a review.', ephemeral: true });
  }

  vouchState.set(interaction.user.id, { orderKind, guildId });
  const e = baseEmbed('⭐ Submit Your Vouch', GOLD);
  e.setDescription('Select your **rating**, then click **Continue** to fill in your feedback.\n\nThank you for taking the time to vouch!');

  const ratingOptions = [5, 4, 3, 2, 1].map(n =>
    new StringSelectMenuOptionBuilder().setLabel(`${'⭐'.repeat(n)} (${n}/5)`).setValue(String(n))
  );


  const components = [
    new ActionRowBuilder().addComponents(new StringSelectMenuBuilder().setCustomId('vouch_rating_select').setPlaceholder('Select your rating...').addOptions(ratingOptions)),
    new ActionRowBuilder().addComponents(new ButtonBuilder().setCustomId('vouch_continue').setLabel('Continue').setStyle(ButtonStyle.Success).setEmoji('✅')),
  ];

  await interaction.reply({ embeds: [e], components, ephemeral: true });
}

// ── Vouch selects ─────────────────────────────────────────────────────────────
async function handleSelect(interaction) {
  const id    = interaction.customId;
  const value = interaction.values[0];
  const state = getVouchState(interaction.user.id);

  if (id === 'vouch_rating_select') { state.rating = parseInt(value);  return interaction.deferUpdate(); }


  // vouch_continue button is routed here too if the id check misses — handled in loader as button
}

// ── Continue button — open modal ──────────────────────────────────────────────
async function handleContinueBtn(interaction) {
  const state = getVouchState(interaction.user.id);
  const missing = [];
  if (!state.rating)      missing.push('Rating');
  if (missing.length) return interaction.reply({ content: `❌ Please select: **${missing.join(', ')}**`, ephemeral: true });

  const modal = new ModalBuilder()
    .setCustomId('vouch_detail_modal')
    .setTitle('Submit Your Vouch')
    .addComponents(
      new ActionRowBuilder().addComponents(
        new TextInputBuilder().setCustomId('amount').setLabel('Order Amount (EUR)').setStyle(TextInputStyle.Short).setPlaceholder('44.99').setRequired(true)
      ),
      new ActionRowBuilder().addComponents(
        new TextInputBuilder().setCustomId('feedback').setLabel('Your Feedback').setStyle(TextInputStyle.Paragraph).setMaxLength(500).setPlaceholder('Fast service, very professional...').setRequired(true)
      ),
    );
  await interaction.showModal(modal);
}

// ── Vouch detail modal submit ─────────────────────────────────────────────────
async function handleModal(interaction) {
  const state      = getVouchState(interaction.user.id);
  const amountRaw  = interaction.fields.getTextInputValue('amount').replace('€', '').trim();
  const feedback   = interaction.fields.getTextInputValue('feedback');
  const amountVal = parseFloat(amountRaw) || 0;
  const stars     = state.rating ?? 5;
  const orderKind = state.orderKind ?? 'ranked';
  const payment   = 'Unknown';
const svcType   = 'boost';
  const guildId   = state.guildId ?? interaction.guildId ?? '0';

  const vouchId = `VOUCH-${uuidv4().replace(/-/g, '').slice(0, 6).toUpperCase()}`;

  const countRow = await queryOne('SELECT COUNT(*) AS cnt FROM vouchers');
  const vouchNum = parseInt(countRow?.cnt ?? 0) + 1;

await queryOne(
  'INSERT INTO vouchers (id, code, amount, used_by, rating, feedback, order_kind) VALUES ($1,$2,$3,$4,$5,$6,$7)',
  [vouchId, vouchId, amountVal, interaction.user.id, stars, feedback, orderKind]
);

  const cfg       = interaction.guild ? await getConfig(interaction.guildId) : null;
  const vouchChId = cfg?.vouch_channel_id ? String(cfg.vouch_channel_id) : FALLBACK_VOUCH_CHANNEL_ID;

  const customStar  = '<a:ratingstar:1511306314486386799>';
  const starDisplay = customStar.repeat(stars);

  let kindLabel, svcIcon;
if (orderKind === 'prestige') {
  svcIcon   = prestigeEmoji('Prestige 0 -> Prestige 1');
  kindLabel = 'Prestige Boost';
} else {
  svcIcon   = '🔥';
  kindLabel = 'Ranked Boost';
}

  // ── Diagnostica: verifica disponibilità builder ──────────────────────────
  console.log('[VOUCH] STEP 0 — SectionBuilder:', typeof SectionBuilder, '| ThumbnailBuilder:', typeof ThumbnailBuilder);

  const avatarURL = interaction.user.displayAvatarURL({ size: 128 });
  const useSectionLayout = typeof SectionBuilder === 'function' && typeof ThumbnailBuilder === 'function';
  console.log('[VOUCH] STEP 1 — useSectionLayout:', useSectionLayout, '| avatarURL:', avatarURL);

  let container;
  try {
    console.log('[VOUCH] STEP 2 — inizio ContainerBuilder');
    const cb = new ContainerBuilder().setAccentColor(GOLD);
    console.log('[VOUCH] STEP 3 — ContainerBuilder creato');

    if (useSectionLayout) {
      console.log('[VOUCH] STEP 4a — percorso SectionBuilder');
      let thumb;
      try {
        thumb = new ThumbnailBuilder().setMedia({ url: avatarURL });
        console.log('[VOUCH] STEP 5a — ThumbnailBuilder.setMedia OK');
      } catch (thumbErr) {
        console.error('[VOUCH] STEP 5a FAIL — setMedia con oggetto fallito, provo stringa:', thumbErr.message);
        thumb = new ThumbnailBuilder().setMedia(avatarURL);
        console.log('[VOUCH] STEP 5b — ThumbnailBuilder.setMedia(stringa) OK');
      }

      const section = new SectionBuilder()
        .addTextDisplayComponents(
          new TextDisplayBuilder().setContent(
            `### <:client:1508831518858940607> Customer Review from ${interaction.user.toString()}\n` +
            `### <a:ratingstar:1511306314486386799> Rating (${stars}/5)\n` +
            `<:arrow:1509857611816763482> ${starDisplay}`
          )
        )
        .setAccessory(thumb);
      console.log('[VOUCH] STEP 6a — SectionBuilder costruito');

      cb.addSectionComponents(section);
      console.log('[VOUCH] STEP 7a — addSectionComponents OK');
    } else {
      // Fallback: SectionBuilder/ThumbnailBuilder non disponibili nel runtime
      console.warn('[VOUCH] STEP 4b — fallback: SectionBuilder non disponibile, uso TextDisplay puro');
      cb.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(
          `### <:client:1508831518858940607> Customer Review from ${interaction.user.toString()}\n` +
          `### <a:ratingstar:1511306314486386799> Rating (${stars}/5)\n` +
          `<:arrow:1509857611816763482> ${starDisplay}`
        )
      );
      console.log('[VOUCH] STEP 5b — TextDisplay fallback OK');
    }

    console.log('[VOUCH] STEP 8 — aggiungo Separator + TextDisplay body');
let container;
  try {
    container = new ContainerBuilder()
      .setAccentColor(GOLD)
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent(
          `### <:client:1508831518858940607> Customer Review from ${interaction.user.toString()}\n` +
          `### <a:ratingstar:1511306314486386799> Rating (${stars}/5)\n` +
          `<:arrow:1509857611816763482> ${starDisplay}`
        )
      )
      .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent(
          `### <:info:1508767700329959545> Feedback\n` +
          `<:arrow:1509857611816763482> ${feedback}\n` +
          `### <:Amount:1501221154650853450> Order Amount\n` +
          `<:arrow:1509857611816763482> **\`€${amountVal.toFixed(2)}\`**`
        )
      )
      .addSeparatorComponents(new SeparatorBuilder().setDivider(true))
      .addActionRowComponents(
        new ActionRowBuilder().addComponents(
          new ButtonBuilder()
            .setLabel('Order Now')
            .setStyle(ButtonStyle.Link)
            .setEmoji('<:rocket:1491490870979985438>')
            .setURL(`https://discord.com/channels/${guildId}/1355262063089291463`),
          new ButtonBuilder()
            .setCustomId('vouch_btn:ranked')
            .setLabel('Submit Review')
            .setStyle(ButtonStyle.Success)
            .setEmoji('⭐'),
        )
      );
  } catch (err) {
    console.error('[VOUCH] ContainerBuilder failed:', err);
    await interaction.reply({ content: '❌ Internal error building review. Please try again.', ephemeral: true });
    return;
  }

  await interaction.reply({ content: '✅ Your vouch has been submitted. Thank you!', ephemeral: true });

  // Post to vouch channel
  const guild = interaction.guild;
  if (guild && vouchChId) {
    let ch = guild.channels.cache.get(vouchChId) ?? await guild.channels.fetch(vouchChId).catch(() => null);
    if (ch) {
      try {
        const sendArgs = { components: [container], flags: MessageFlags.IsComponentsV2 };
        await ch.send(sendArgs);
      } catch (err) {
        console.error('[VOUCH] ch.send failed:', err);
      }
    }
  }

  vouchState.delete(interaction.user.id);
}

// ── Review submit button (on vouch posts) ─────────────────────────────────────
async function handleReviewSubmit(interaction) {
  const member = interaction.guild?.members.cache.get(interaction.user.id) ?? interaction.member;
  if (!member?.roles.cache.has(CUSTOMER_ROLE_ID)) {
    return interaction.reply({ content: '❌ Only customers can submit a review.', ephemeral: true });
  }

  const guildId = interaction.guildId ?? '0';
  vouchState.set(interaction.user.id, { orderKind: 'ranked', guildId });

  const e = baseEmbed('⭐ Submit Your Vouch', GOLD);
  e.setDescription('Select your **rating**, then click **Continue** to fill in your feedback.\n\nThank you for taking the time to vouch!');

  const ratingOptions = [5, 4, 3, 2, 1].map(n =>
    new StringSelectMenuOptionBuilder().setLabel(`${'⭐'.repeat(n)} (${n}/5)`).setValue(String(n))
  );

  const components = [
    new ActionRowBuilder().addComponents(new StringSelectMenuBuilder().setCustomId('vouch_rating_select').setPlaceholder('Select your rating...').addOptions(ratingOptions)),
    new ActionRowBuilder().addComponents(new ButtonBuilder().setCustomId('vouch_continue').setLabel('Continue').setStyle(ButtonStyle.Success).setEmoji('✅')),
  ];

  await interaction.reply({ embeds: [e], components, ephemeral: true });
}

module.exports = { handleButton, handleSelect, handleContinueBtn, handleModal, handleReviewSubmit };
