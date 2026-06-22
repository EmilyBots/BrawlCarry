const { SlashCommandBuilder, ModalBuilder, TextInputBuilder, TextInputStyle, ActionRowBuilder } = require('discord.js');
const { queryOne } = require('../../db/index');
const { baseEmbed } = require('../../utils/embeds');
const { addPaymentMethod, removePaymentMethod, getPaymentMethods } = require('../../utils/permissions');
const { PRIMARY, SUCCESS, DANGER, GOLD, ACCENT, PRESTIGE_PRICES } = require('../../config/constants');

const ADMIN_ROLE_ID = '1479079737052762205';
const guardAdmin = async (i) => {
  if (i.member.roles.cache.has(ADMIN_ROLE_ID)) return false;
  await i.reply({ content: '❌ You are not allowed to use this command.', ephemeral: true });
  return true;
};

// ── /add_payment_method ───────────────────────────────────────────────────────
const addPaymentMethodCmd = {
  data: new SlashCommandBuilder()
    .setName('add_payment_method')
    .setDescription('Add a payment method to the order forms')
    .setDefaultMemberPermissions(null)
    .addStringOption(o => o.setName('label').setDescription('Payment method name (e.g. LTC, Revolut)').setRequired(true))
    .addStringOption(o => o.setName('emoji').setDescription('Emoji to display next to it')),

  async execute(interaction) {
    if (await guardAdmin(interaction)) return;
    const label   = interaction.options.getString('label').trim();
    const emoji   = interaction.options.getString('emoji')?.trim() ?? '💳';
    const success = await addPaymentMethod(interaction.guildId, label, emoji);

    const e = success
      ? baseEmbed('✅ Payment Method Added', SUCCESS, `${emoji} **${label}** has been added to the payment options.`)
      : baseEmbed('⚠️ Already Exists', GOLD, `**${label}** is already a configured payment method.`);

    await interaction.reply({ embeds: [e], ephemeral: true });
  },
};

// ── /remove_payment_method ────────────────────────────────────────────────────
const removePaymentMethodCmd = {
  data: new SlashCommandBuilder()
    .setName('remove_payment_method')
    .setDescription('Remove a payment method from the order forms')
    .setDefaultMemberPermissions(null)
    .addStringOption(o => o.setName('label').setDescription('Exact name of the payment method to remove').setRequired(true)),

  async execute(interaction) {
    if (await guardAdmin(interaction)) return;
    const label   = interaction.options.getString('label').trim();
    const success = await removePaymentMethod(interaction.guildId, label);

    const e = success
      ? baseEmbed('✅ Payment Method Removed', SUCCESS, `**${label}** has been removed from the payment options.`)
      : baseEmbed('❌ Not Found', DANGER, `**${label}** was not found in the configured payment methods.`);

    await interaction.reply({ embeds: [e], ephemeral: true });
  },
};

// ── /list_payment_methods ─────────────────────────────────────────────────────
const listPaymentMethodsCmd = {
  data: new SlashCommandBuilder()
    .setName('list_payment_methods')
    .setDescription('View all configured payment methods')
    .setDefaultMemberPermissions(null),

  async execute(interaction) {
    if (await guardAdmin(interaction)) return;
    const methods = await getPaymentMethods(interaction.guildId);
    const e = baseEmbed('💳 Payment Methods', PRIMARY);
    e.setDescription(methods.length
      ? methods.map(m => `${m.emoji} **${m.label}**`).join('\n')
      : 'No payment methods configured.'
    );
    await interaction.reply({ embeds: [e], ephemeral: true });
  },
};

// ── /set_rank_price ───────────────────────────────────────────────────────────
const setRankPriceCmd = {
  data: new SlashCommandBuilder()
    .setName('set_rank_price')
    .setDescription('Set a custom price for a specific rank boost route')
    .setDefaultMemberPermissions(null)
    .addStringOption(o => o.setName('from_rank').setDescription('Starting rank').setRequired(true))
    .addStringOption(o => o.setName('to_rank').setDescription('Desired rank').setRequired(true))
    .addNumberOption(o => o.setName('price').setDescription('Base price in EUR').setRequired(true).setMinValue(0)),

  async execute(interaction) {
    if (await guardAdmin(interaction)) return;
    const fromRank = interaction.options.getString('from_rank');
    const toRank   = interaction.options.getString('to_rank');
    const price    = interaction.options.getNumber('price');

    await queryOne(
      `INSERT INTO rank_prices (guild_id, from_rank, to_rank, base_price)
       VALUES ($1, $2, $3, $4)
       ON CONFLICT (guild_id, from_rank, to_rank) DO UPDATE SET base_price = EXCLUDED.base_price`,
      [interaction.guildId, fromRank, toRank, price]
    );

    const e = baseEmbed('✅ Rank Price Set', SUCCESS, `**${fromRank}** → **${toRank}** base price set to **€${price.toFixed(2)}**.`);
    await interaction.reply({ embeds: [e], ephemeral: true });
  },
};

// ── /set_prestige_price ───────────────────────────────────────────────────────
const setPrestigePriceCmd = {
  data: new SlashCommandBuilder()
    .setName('set_prestige_price')
    .setDescription('Update a prestige boost price')
    .setDefaultMemberPermissions(null)
    .addStringOption(o => o.setName('spec').setDescription('e.g. Prestige 0 -> Prestige 1').setRequired(true))
    .addStringOption(o => o.setName('price').setDescription('New price in EUR (e.g. 15)').setRequired(true)),

  async execute(interaction) {
    if (await guardAdmin(interaction)) return;
    const spec  = interaction.options.getString('spec');
    const price = interaction.options.getString('price');

    const matched = Object.keys(PRESTIGE_PRICES).find(
      k => k.toLowerCase().replace(/\s/g, '') === spec.toLowerCase().replace(/\s/g, '')
    );

    if (!matched) {
      const opts = Object.keys(PRESTIGE_PRICES).map(k => `\`${k}\``).join('\n');
      return interaction.reply({ content: `❌ Unknown spec. Valid options:\n${opts}`, ephemeral: true });
    }

    PRESTIGE_PRICES[matched] = price;

    const e = baseEmbed('✅ Prestige Price Updated', SUCCESS, `**${matched}** is now **€${price}**\n\n⚠️ Re-post \`/prestige_panel\` to show the new price.`);
    await interaction.reply({ embeds: [e], ephemeral: true });
  },
};

// ── /post_account ─────────────────────────────────────────────────────────────
const postAccountCmd = {
  data: new SlashCommandBuilder()
    .setName('post_account')
    .setDescription('Post an account for sale in the account-selling channel')
    .setDefaultMemberPermissions(null),

  async execute(interaction) {
    if (await guardAdmin(interaction)) return;
    const modal = new ModalBuilder()
      .setCustomId('account_sale_modal')
      .setTitle('Post Account for Sale');

    modal.addComponents(
      new ActionRowBuilder().addComponents(
        new TextInputBuilder().setCustomId('description').setLabel('Features (one per line)').setStyle(TextInputStyle.Paragraph).setRequired(true).setPlaceholder('380+ skins\nMasters 2\nHalf price shop')
      ),
      new ActionRowBuilder().addComponents(
        new TextInputBuilder().setCustomId('price').setLabel('Price (EUR)').setStyle(TextInputStyle.Short).setRequired(true)
      ),
      new ActionRowBuilder().addComponents(
        new TextInputBuilder().setCustomId('contact').setLabel('Trophies | P11 | Hyper  (separated by |)').setStyle(TextInputStyle.Short).setRequired(true).setPlaceholder('67714 | 85 | 76')
      ),
      new ActionRowBuilder().addComponents(
        new TextInputBuilder().setCustomId('game').setLabel('Ranked History').setStyle(TextInputStyle.Short).setRequired(true).setPlaceholder('1x Masters 2025, Masters 2 Peak')
      ),
      new ActionRowBuilder().addComponents(
        new TextInputBuilder().setCustomId('image_url').setLabel('Image URL (optional)').setStyle(TextInputStyle.Short).setRequired(false)
      ),
    );

    await interaction.showModal(modal);
  },
};


module.exports = [addPaymentMethodCmd, removePaymentMethodCmd, listPaymentMethodsCmd, setRankPriceCmd, setPrestigePriceCmd, postAccountCmd];
