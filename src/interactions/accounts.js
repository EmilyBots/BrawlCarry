const { ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder } = require('discord.js');
const { queryOne } = require('../db/index');
const { getConfig } = require('../db/index');
const { baseEmbed } = require('../utils/embeds');
const { createTicketThread } = require('../utils/tickets');
const { GOLD, SUCCESS, FOOTER_BRAND, HARDCODED_SUPPORT_ROLES } = require('../config/constants');
const { v4: uuidv4 } = require('uuid');

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
    new ButtonBuilder().setCustomId(`account_buy:${listingId}`).setLabel('Buy Account').setStyle(ButtonStyle.Success).setEmoji('🛒'),
    new ButtonBuilder().setCustomId(`account_sold:${listingId}`).setLabel('Mark as Sold').setStyle(ButtonStyle.Danger).setEmoji('<:sold:1507693147306852515>')
  );

  if (saleCh) await saleCh.send({ embeds: [e], components: [buyView] });
  await interaction.reply({ content: '✅ Account listing posted.', ephemeral: true });
}

// ── Buy button ────────────────────────────────────────────────────────────────
async function handleButton(interaction) {
  const id = interaction.customId;
  if (id.startsWith('account_sold:')) return handleSoldButton(interaction);
  const listingId = id.split(':')[1];
  if (!listingId) return;

  await interaction.deferReply({ ephemeral: true });

  const guild   = interaction.guild;
  const member  = interaction.member;
  const cfg     = await getConfig(interaction.guildId);

  const listing = await queryOne('SELECT * FROM account_listings WHERE id = $1', [listingId]);
  if (!listing || listing.status !== 'available') {
    return interaction.followUp({ content: '❌ This 4ccount has already been sold.', ephemeral: true });
  }

  const e = baseEmbed(`<:rocket:1491490870979985438> 4ccount Ticket`, GOLD);
  e.setDescription(
    `## Your 4ccount request has been successfully created.\n\n` +
    `Our team will review and begin processing it shortly.\n\n` +
    `You can manage your ticket using the options below.`
  );
  e.setFooter({ text: FOOTER_BRAND });

  const closeView = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('ticket_close_v2').setLabel('Close Ticket').setStyle(ButtonStyle.Danger).setEmoji('🔒')
  );

  const featureLinesTicket = listing.description
    .split('\n')
    .map(l => l.trim())
    .filter(Boolean)
    .map(l => `<:reply:1507680110843658260> ${l}`)
    .join('\n');

  const orderEmbed = new EmbedBuilder()
    .setColor(GOLD)
    .setTitle(`<:Info:1501221322183934002> Order Details`)
    .setDescription(
      `<:rocket:1491490870979985438> **4ccount**\n${featureLinesTicket}\n\n` +
      `<:Amount:1501221154650853450> **Price**\n→ **€${parseFloat(listing.price).toFixed(2)}**`
    );
  if (listing.image_url) orderEmbed.setImage(listing.image_url);

  const orderId = `ACCT-${uuidv4().replace(/-/g, '').slice(0, 6).toUpperCase()}`;
  await queryOne(
    'INSERT INTO orders (id, user_id, from_tier, to_tier, price, method, order_type, service_type) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)',
    [orderId, interaction.user.id, listing.description.slice(0, 100), String(listing.id), parseFloat(listing.price), null, 'account', 'account']
  );

  try {
    const overrideCh = cfg?.account_sale_ticket_channel_id
      ? String(cfg.account_sale_ticket_channel_id)
      : ACCOUNT_SALE_TICKET_CHANNEL_ID;

    const thread = await createTicketThread(
      guild, member,
      `4ccount-${member.user.id}`,
      e, closeView, cfg, overrideCh
    );

    await queryOne('UPDATE orders SET ticket_channel_id = $1 WHERE id = $2', [thread.id, orderId]);

    await thread.send({ embeds: [orderEmbed] });
    await thread.send({ content: `<@&1491447093078921267> <@&1355262062124859600> <@&1479079737052762205>` });

    await interaction.followUp({ content: `✅ Purchase thread created: ${thread.toString()}`, ephemeral: true });
  } catch (err) {
    await interaction.followUp({ content: `❌ Could not create purchase thread: \`${err.message}\``, ephemeral: true });
  }
}

// ── Mark as Sold ──────────────────────────────────────────────────────────────
const SOLD_ROLE_ID = '1479079737052762205';

async function handleSoldButton(interaction) {
  if (!interaction.member.roles.cache.has(SOLD_ROLE_ID)) {
    return interaction.reply({ content: '❌ You are not allowed to use this button.', ephemeral: true });
  }

  const listingId = interaction.customId.split(':')[1];
  await queryOne("UPDATE account_listings SET status = 'sold' WHERE id = $1", [listingId]);

  const original = interaction.message.embeds[0];
  const soldDesc = `## <:rocket:1491490870979985438> | ~~Sold!~~\n` +
    original.description.split('\n').slice(1).join('\n');

  const updated = EmbedBuilder.from(original)
    .setColor(0xFF0000)
    .setDescription(soldDesc);

  const disabledRow = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`account_buy:${listingId}`).setLabel('Buy Account').setStyle(ButtonStyle.Success).setEmoji('🛒').setDisabled(true),
    new ButtonBuilder().setCustomId(`account_sold:${listingId}`).setLabel('Mark as Sold').setStyle(ButtonStyle.Danger).setEmoji('<:sold:1507693147306852515>').setDisabled(true)
  );

  await interaction.update({ embeds: [updated], components: [disabledRow] });
}

module.exports = { handleModal, handleButton };
