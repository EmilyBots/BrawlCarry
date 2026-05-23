const { ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder } = require('discord.js');
const { queryOne } = require('../db/index');
const { getConfig } = require('../db/index');
const { baseEmbed } = require('../utils/embeds');
const { createTicketThread } = require('../utils/tickets');
const { GOLD, SUCCESS, FOOTER_BRAND, HARDCODED_SUPPORT_ROLES } = require('../config/constants');

const ACCOUNT_SALE_TICKET_CHANNEL_ID = '1491765596403273869'; // hardcoded fallback

// ── Account sale modal (staff posts a listing) ────────────────────────────────
async function handleModal(interaction) {
  const rankedInfo  = interaction.fields.getTextInputValue('game').trim();
  const description = interaction.fields.getTextInputValue('description').trim();
  const priceRaw    = interaction.fields.getTextInputValue('price').replace('€', '').trim();
  const statsRaw    = interaction.fields.getTextInputValue('contact').trim();
  const imageUrl    = interaction.fields.getTextInputValue('image_url')?.trim() || null;

  const price = parseFloat(priceRaw);
  if (isNaN(price)) return interaction.reply({ content: '❌ Invalid price. Enter a number like `25.00`.', ephemeral: true });

  const cfg          = await getConfig(interaction.guildId);
  const saleCh       = cfg?.account_sale_channel_id
    ? interaction.guild.channels.cache.get(String(cfg.account_sale_channel_id))
    : interaction.channel;

  const result = await queryOne(
    'INSERT INTO account_listings (guild_id, seller_id, game, description, price, contact, image_url, status) VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id',
    [interaction.guildId, interaction.user.id, rankedInfo, description, price, statsRaw, imageUrl, 'available']
  );
  const listingId = result?.id;

  const featureLines = description
    .split('\n')
    .map(l => l.trim())
    .filter(Boolean)
    .map(l => `<:reply:1507680110843658260> ${l}`)
    .join('\n');

  const [trophies = '—', p11 = '—', hyper = '—'] = statsRaw.split('|').map(s => s.trim());

  const e = new EmbedBuilder()
    .setColor(GOLD)
    .setDescription(
      `## <:rocket:1491490870979985438> | New 4ccount For $4le !\n` +
      `\u200b\n` +
      featureLines + `\n\n` +
      `<:Amount:1501221154650853450> **Price :** **€${price.toFixed(2)}**\n` +
      `<:copyright:1485658086156013598> **Trophies :** **${trophies}**\n` +
      `<:p11:1507678268650688593> **P11 :** **${p11}**\n` +
      `<:copyright:1489942466995163237> **Hypercharge :** **${hyper}**\n` +
      `<:ranked:1507679109495652402> **Ranked :** **${rankedInfo}**`
    )
    .setFooter({ text: `${FOOTER_BRAND}` });
  if (imageUrl) e.setImage(imageUrl);
  const buyView = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`account_buy:${listingId}`).setLabel('Buy Account').setStyle(ButtonStyle.Success).setEmoji('🛒')
  );

  if (saleCh) await saleCh.send({ embeds: [e], components: [buyView] });
  await interaction.reply({ content: '✅ Account listing posted.', ephemeral: true });
}

// ── Buy button ────────────────────────────────────────────────────────────────
async function handleButton(interaction) {
  const id        = interaction.customId;
  const listingId = id.split(':')[1];
  if (!listingId) return;

  await interaction.deferReply({ ephemeral: true });

  const guild   = interaction.guild;
  const member  = interaction.member;
  const cfg     = await getConfig(interaction.guildId);

  const listing = await queryOne('SELECT * FROM account_listings WHERE id = $1', [listingId]);
  if (!listing || listing.status !== 'available') {
    return interaction.followUp({ content: '❌ This account is no longer available.', ephemeral: true });
  }

  const e = baseEmbed(`🛒 Account Purchase — ${listing.game}`, GOLD);
  e.setDescription(
    `Welcome, ${member}!\n\nYou're interested in purchasing this account:\n\n` +
    `🎮 **Game:** ${listing.game}\n` +
    `💰 **Price:** **€${parseFloat(listing.price).toFixed(2)}**\n` +
    `📋 **Description:** ${listing.description}\n` +
    `🆔 **Listing #:** ${listing.id}\n\n` +
    'Staff will be with you shortly to finalize the purchase.\nPlease have your payment ready!'
  );
  e.setAuthor({ name: member.displayName, iconURL: member.displayAvatarURL() });

  const closeView = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('ticket_close_v2').setLabel('Close Ticket').setStyle(ButtonStyle.Danger).setEmoji('🔒')
  );

  try {
    const overrideCh = cfg?.account_sale_ticket_channel_id
      ? String(cfg.account_sale_ticket_channel_id)
      : ACCOUNT_SALE_TICKET_CHANNEL_ID;

    const thread = await createTicketThread(
      guild, member,
      `purchase-${listing.game.slice(0, 20).toLowerCase().replace(/\s+/g, '-')}-${member.user.username.slice(0, 10).toLowerCase()}`,
      e, closeView, cfg, overrideCh
    );
    await interaction.followUp({ content: `✅ Purchase thread created: ${thread.toString()}`, ephemeral: true });
  } catch (err) {
    await interaction.followUp({ content: `❌ Could not create purchase thread: \`${err.message}\``, ephemeral: true });
  }
}

module.exports = { handleModal, handleButton };
