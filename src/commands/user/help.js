const { SlashCommandBuilder } = require('discord.js');
const { baseEmbed } = require('../../utils/embeds');
const { PRIMARY, RANK_EMOJI, PRESTIGE_EMOJI } = require('../../config/constants');

module.exports = {
  data: new SlashCommandBuilder()
    .setName('help')
    .setDescription('View all available bot commands'),

  async execute(interaction) {
    const rankIcons    = Object.values(RANK_EMOJI).join(' ');
    const presIcons    = Object.values(PRESTIGE_EMOJI).join(' ');

    const e = baseEmbed('📋 BrawlCarry Bot — Commands', PRIMARY);
    e.setDescription(
      `**Rank Icons:** ${rankIcons}\n` +
      `**Prestige Icons:** ${presIcons}\n\n` +
      '**⚙️ Admin Commands**\n' +
      '`/setup` — Configure all channels, ticket categories, booster role & owner\n' +
      '`/configure_ticket_panel` — Customise support ticket panel text\n' +
      '`/ranked_panel` — Post the Ranked Boost intake panel 🔥\n' +
      '`/prestige_panel` — Post the Prestige Boost intake panel ✨\n' +
      '`/ticket_panel` — Post the General Support ticket panel\n' +
      '`/backup_panel` — Post the backup access panel\n' +
      '`/restore_backup` — Trigger backup server restore\n' +
      '`/giveaway` — Start a giveaway\n' +
      '`/end_giveaway` — End a giveaway and draw winners\n' +
      '`/backup_link` — DM all members the backup server link\n\n' +
      '**✅ Staff Commands**\n' +
      '`/order_complete` — Mark an order as completed\n' +
      '`/vouch_panel` — Send vouch panel to user or channel\n' +
      '`/post_account` — Post an account for sale\n' +
      '`/add_payment_method` — Add a payment method to order forms\n' +
      '`/remove_payment_method` — Remove a payment method from order forms\n' +
      '`/list_payment_methods` — View all configured payment methods\n' +
      '`/set_prestige_price` — Update a prestige boost price\n' +
      '`/set_rank_price` — Set a custom price for a rank boost route\n' +
      '`/assign_role` — Assign or remove a role from a member\n\n' +
      '**👤 User & Booster Commands**\n' +
      '`/stats` — View your order statistics\n' +
      '`/booster_stats` — View booster completed orders, earnings & rating\n' +
      '`/leaderboard` — View the booster leaderboard (sort by orders/earnings/rating)\n' +
      '`/availability` — Set your booster availability (Available / Busy / Offline)\n' +
      '`/my_orders` — View your order history as a booster\n' +
      '`/price_estimate` — Get a price estimate for a ranked boost\n' +
      '`/help` — Show this menu\n\n' +
      '**📦 Order Flow**\n' +
      '1. Customer clicks **Ranked/Prestige Boost** → sees **price estimate** → confirms → ticket opens\n' +
      '2. Staff click **📢 Publish to Boosters** → enter booster earnings → claiming card posted\n' +
      '3. Booster sets status to **Available** then clicks **🟠 Claim This Boost** → added to ticket\n' +
      '4. Staff mark complete → customer receives **rating request** for booster\n\n' +
      '**💡 Price Estimation Rules**\n' +
      '> 40-50 P11 = baseline price\n' +
      '> <40 P11 = slightly higher price (harder boost)\n' +
      '> >50 P11 = slightly lower price (easier boost)\n' +
      '> Carry = 2x the boost price\n' +
      '> Minimum desired rank: **Diamond I**\n\n' +
      '**🛠 Service Types**\n' +
      '> 🟢 **Boost** — staff play on customer\'s account (standard price)\n' +
      '> 🔴 **Carry** — staff play alongside customer (2x price)'
    );

    await interaction.reply({ embeds: [e], ephemeral: true });
  },
};
