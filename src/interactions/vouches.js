const {
  ModalBuilder, TextInputBuilder, TextInputStyle,
  ActionRowBuilder, ButtonBuilder, ButtonStyle,
  StringSelectMenuBuilder, StringSelectMenuOptionBuilder,
  EmbedBuilder,
} = require('discord.js');
const { queryOne } = require('../db/index');
const { getConfig } = require('../db/index');
const { baseEmbed } = require('../utils/embeds');
const { getPaymentMethods, getPaymentEmoji } = require('../utils/permissions');
const { fetchAndWatermark } = require('../utils/watermark');
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
  const imgUrl     = null;

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

  const customStar  = '<:star:1501524038344769546>';
  const starDisplay = customStar.repeat(stars);

  let kindLabel, svcIcon;
if (orderKind === 'prestige') {
  svcIcon   = prestigeEmoji('Prestige 0 -> Prestige 1');
  kindLabel = 'Prestige Boost';
} else {
  svcIcon   = '🔥';
  kindLabel = 'Ranked Boost';
}

  const e = new EmbedBuilder()
    .setColor(GOLD)
    .setTitle(`<:Customer:1501221119900778506> Customer Review from ${interaction.user.toString()}`)
    .setThumbnail(interaction.user.displayAvatarURL())
    .addFields(
      { name: '<:Info:1501221322183934002> Feedback',      value: `➜ ${feedback}`,             inline: false },
      { name: '<:Amount:1501221154650853450> Amount Paid', value: `➜ **€${amountVal.toFixed(2)}**`, inline: false },
      { name: `<:star:1501524038344769546> Rating (${stars}/5)`, value: `➜ ${starDisplay}`,   inline: false },
    )
    .setFooter({ text: FOOTER_BRAND });

  let wm = null;
  if (imgUrl) {
    wm = await fetchAndWatermark(imgUrl, true).catch(() => null);
    if (wm) e.setImage('attachment://proof.jpg');
  }

  await interaction.reply({ content: '✅ Your vouch has been submitted. Thank you!', ephemeral: true });

  const reviewView = new ActionRowBuilder().addComponents(
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
  );

  // Post to vouch channel
  const guild = interaction.guild;
  if (guild && vouchChId) {
    let ch = guild.channels.cache.get(vouchChId) ?? await guild.channels.fetch(vouchChId).catch(() => null);
    if (ch) {
      const sendArgs = { embeds: [e], components: [reviewView], ...(wm ? { files: [wm] } : {}) };
      await ch.send(sendArgs).catch(err => console.error('[VOUCH] send failed:', err));
    }
  }

  vouchState.delete(interaction.user.id);
}

// ── Review submit button (on vouch posts) ─────────────────────────────────────
async function handleReviewSubmit(interaction) {
  const member = interaction.guild?.members.cache.get(interaction.user.id) ?? interaction.member;
  if (member && !member.roles.cache.has(CUSTOMER_ROLE_ID)) {
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
