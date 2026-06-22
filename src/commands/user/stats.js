const { SlashCommandBuilder } = require('discord.js');
const { queryOne, queryAll } = require('../../db/index');
const { baseEmbed, formatDuration } = require('../../utils/embeds');
const { rankEmoji } = require('../../utils/pricing');
const { PRIMARY, ACCENT, GOLD, P11_EMOJI, ALL_RANKS, DESIRED_RANKS } = require('../../config/constants');

// ── /stats ────────────────────────────────────────────────────────────────────
const statsCmd = {
  data: new SlashCommandBuilder()
    .setName('stats')
    .setDescription('View carry statistics for a user')
    .addUserOption(o => o.setName('user').setDescription('User to look up (defaults to you)')),

  async execute(interaction) {
    if (!interaction.member.roles.cache.has('1479079737052762205')) {
      return interaction.reply({ content: '❌ You do not have the required role to use this command.', ephemeral: true });
    }
    const target = interaction.options.getUser('user') ?? interaction.user;
    const row    = await queryOne('SELECT COUNT(*) AS count, SUM(price) AS total FROM orders WHERE user_id = $1', [target.id]);
    const vc     = await queryOne('SELECT COUNT(*) AS vc FROM vouchers WHERE used_by = $1', [target.id]);

    const e = baseEmbed(`📊 ${target.displayName ?? target.username}'s Stats`, PRIMARY);
    e.setThumbnail(target.displayAvatarURL());
    e.addFields(
      { name: '🎮 Total Orders', value: `**${row?.count ?? 0}**`,                                          inline: true },
      { name: '💰 Total Spent',  value: row?.total ? `**€${parseFloat(row.total).toFixed(2)}**` : '**€0.00**', inline: true },
      { name: '⭐ Vouches',      value: `**${vc?.vc ?? 0}**`,                                              inline: true },
    );
    await interaction.reply({ embeds: [e], ephemeral: true });
  },
};

// ── /booster_stats ────────────────────────────────────────────────────────────
const boosterStatsCmd = {
  data: new SlashCommandBuilder()
    .setName('booster_stats')
    .setDescription('View booster statistics for a user')
    .addUserOption(o => o.setName('user').setDescription('Booster to look up (defaults to you)')),

  async execute(interaction) {
    if (!interaction.member.roles.cache.has('1479079737052762205') && !interaction.member.roles.cache.has('1485296409795235910')) {
      return interaction.reply({ content: '❌ You do not have the required role to use this command.', ephemeral: true });
    }
    const target    = interaction.options.getUser('user') ?? interaction.user;
    const row       = await queryOne(
      'SELECT COUNT(*) AS completed, SUM(booster_earnings) AS total_earnings FROM orders WHERE booster_id = $1 AND status = $2',
      [target.id, 'completed']
    );
    const activeRow = await queryOne('SELECT COUNT(*) AS active FROM orders WHERE booster_id = $1 AND status = $2', [target.id, 'claimed']);
    const timeRow   = await queryOne(
      'SELECT AVG(completion_time_seconds) AS avg_time FROM orders WHERE booster_id = $1 AND status = $2 AND completion_time_seconds IS NOT NULL',
      [target.id, 'completed']
    );

    const e = baseEmbed(`📊 Booster Stats — ${target.displayName ?? target.username}`, ACCENT);
    e.setThumbnail(target.displayAvatarURL());
    e.addFields(
      { name: '✅ Completed Orders', value: `**${row?.completed ?? 0}**`,                                           inline: true },
      { name: '💰 Total Earnings',   value: `**€${parseFloat(row?.total_earnings ?? 0).toFixed(2)}**`,             inline: true },
      { name: '🔄 Active Orders',    value: `**${activeRow?.active ?? 0}**`,                                        inline: true },
      { name: '⏱ Avg Order Time',   value: timeRow?.avg_time ? formatDuration(Math.floor(timeRow.avg_time)) : 'N/A', inline: true },
    );
    await interaction.reply({ embeds: [e], ephemeral: true });
  },
};

// ── /leaderboard ──────────────────────────────────────────────────────────────
const leaderboardCmd = {
  data: new SlashCommandBuilder()
    .setName('leaderboard')
    .setDescription('View the booster leaderboard')
    .addStringOption(o => o.setName('sort_by').setDescription('Sort by: orders or earnings').addChoices(
      { name: 'earnings', value: 'earnings' },
      { name: 'orders',   value: 'orders' },
    )),

  async execute(interaction) {
    if (!interaction.member.roles.cache.has('1479079737052762205') && !interaction.member.roles.cache.has('1485296409795235910')) {
      return interaction.reply({ content: '❌ You do not have the required role to use this command.', ephemeral: true });
    }
    const sortBy = interaction.options.getString('sort_by') ?? 'earnings';
    const orderByMap = { orders: 'completed DESC', earnings: 'total_earnings DESC' };

    const rows = await queryAll(`
      SELECT booster_id, COUNT(*) AS completed, SUM(booster_earnings) AS total_earnings
      FROM orders
      WHERE status = 'completed' AND booster_id IS NOT NULL
      GROUP BY booster_id
      ORDER BY ${orderByMap[sortBy]}
      LIMIT 10
    `);

    const medals = ['🥇', '🥈', '🥉'];
    const lines  = [];
    for (let i = 0; i < rows.length; i++) {
      const row    = rows[i];
      const medal  = i < 3 ? medals[i] : `**#${i + 1}**`;
      const member = interaction.guild.members.cache.get(String(row.booster_id));
      const name   = member?.displayName ?? `User ${row.booster_id}`;
      const earn   = parseFloat(row.total_earnings ?? 0).toFixed(2);
      lines.push(`${medal} **${name}** — ${row.completed} orders — €${earn}`);
    }

    const e = baseEmbed('🏆 Booster Leaderboard', GOLD);
    e.setDescription(lines.join('\n') || 'No completed orders yet.');
    e.setFooter({ text: `Sorted by ${sortBy}` });
    await interaction.reply({ embeds: [e] });
  },
};

// ── /my_orders ────────────────────────────────────────────────────────────────
const myOrdersCmd = {
  data: new SlashCommandBuilder()
    .setName('my_orders')
    .setDescription('View your order history as a booster')
    .addStringOption(o => o.setName('filter_by').setDescription('all, active, or completed').addChoices(
      { name: 'all',       value: 'all' },
      { name: 'active',    value: 'active' },
      { name: 'completed', value: 'completed' },
    )),

  async execute(interaction) {
    if (!interaction.member.roles.cache.has('1479079737052762205')) {
      return interaction.reply({ content: '❌ You do not have the required role to use this command.', ephemeral: true });
    }
    const filter = interaction.options.getString('filter_by') ?? 'all';
    let orders;
    if (filter === 'active') {
      orders = await queryAll('SELECT * FROM orders WHERE booster_id = $1 AND status = $2 ORDER BY claimed_at DESC', [interaction.user.id, 'claimed']);
    } else if (filter === 'completed') {
      orders = await queryAll('SELECT * FROM orders WHERE booster_id = $1 AND status = $2 ORDER BY completed_at DESC LIMIT 20', [interaction.user.id, 'completed']);
    } else {
      orders = await queryAll('SELECT * FROM orders WHERE booster_id = $1 ORDER BY created_at DESC LIMIT 20', [interaction.user.id]);
    }

    const totalRow = await queryOne('SELECT SUM(booster_earnings) AS total FROM orders WHERE booster_id = $1 AND status = $2', [interaction.user.id, 'completed']);
    const totalEarned = parseFloat(totalRow?.total ?? 0).toFixed(2);

    const e = baseEmbed(`📋 My Orders — ${interaction.member?.displayName ?? interaction.user.username}`, ACCENT);
    if (!orders.length) {
      e.setDescription('No orders found.');
    } else {
      const icons = { pending: '🕐', claimed: '🟡', completed: '✅' };
      const lines = orders.map(o => {
        const icon    = icons[o.status] ?? '❓';
        const earn    = o.booster_earnings ? ` | €${parseFloat(o.booster_earnings).toFixed(2)}` : '';
        const timeStr = o.completion_time_seconds ? ` | ⏱ ${formatDuration(o.completion_time_seconds)}` : '';
        return `${icon} \`${o.id}\` — \`${o.from_tier}\` → \`${o.to_tier}\`${earn}${timeStr}`;
      });
      e.setDescription(lines.join('\n'));
    }
    e.addFields(
      { name: '💰 Total Earned', value: `**€${totalEarned}**`,    inline: true },
      { name: '📊 Shown',        value: `**${orders.length}** orders`, inline: true },
    );
    await interaction.reply({ embeds: [e], ephemeral: true });
  },
};



module.exports = [statsCmd, boosterStatsCmd, leaderboardCmd, myOrdersCmd];
