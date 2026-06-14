const { SlashCommandBuilder, ChannelType } = require('discord.js');
const { setConfig } = require('../../db/index');
const { baseEmbed } = require('../../utils/embeds');
const { SUCCESS } = require('../../config/constants');

module.exports = {
  data: new SlashCommandBuilder()
    .setName('setup')
    .setDescription('Configure bot settings for this server')
    .setDefaultMemberPermissions(0x8) // Administrator
    .addChannelOption(o => o.setName('vouch_channel').setDescription('Channel where vouch posts will be sent'))
    .addChannelOption(o => o.setName('ticket_channel').setDescription('Fallback text channel for ticket threads'))
    .addChannelOption(o => o.setName('ticket_category').setDescription('Fallback category for ticket text-channels').addChannelTypes(ChannelType.GuildCategory))
    .addChannelOption(o => o.setName('completed_channel').setDescription('Channel where completed orders will be posted'))
    .addChannelOption(o => o.setName('ranked_ticket_channel').setDescription('Text channel where Ranked Boost ticket threads are created'))
    .addChannelOption(o => o.setName('prestige_ticket_channel').setDescription('Text channel where Prestige Boost ticket threads are created'))
    .addChannelOption(o => o.setName('winstreak_ticket_channel').setDescription('Text channel where Winstreak ticket threads are created'))
    .addChannelOption(o => o.setName('ranked_panel_channel').setDescription('Channel where booster claiming cards for Ranked orders are posted'))
    .addChannelOption(o => o.setName('prestige_panel_channel').setDescription('Channel where booster claiming cards for Prestige orders are posted'))
    .addUserOption(o => o.setName('owner').setDescription('The server owner/admin who manages the bot'))
    .addChannelOption(o => o.setName('ticket_log_channel').setDescription('Channel where closed ticket logs and transcripts will be sent'))
    .addChannelOption(o => o.setName('application_channel').setDescription('Channel where application panels are posted'))
    .addChannelOption(o => o.setName('application_review_channel').setDescription('Channel where staff review submitted applications'))
    .addChannelOption(o => o.setName('account_sale_channel').setDescription('Channel where account sale posts are published'))
    .addChannelOption(o => o.setName('account_sale_ticket_channel').setDescription('Channel where account purchase ticket threads are created'))
    .addRoleOption(o => o.setName('booster_role').setDescription('Role given to boosters'))
    .addChannelOption(o => o.setName('proof_channel').setDescription('Channel where proof screenshots are posted'))
    .addIntegerOption(o => o.setName('inactive_ticket_hours').setDescription('Hours of inactivity before ticket warning (default: 24)').setMinValue(1))
    .addChannelOption(o => o.setName('application_ticket_channel').setDescription('Channel where application ticket threads are created'))
    .addRoleOption(o => o.setName('carrier_role').setDescription('Role given to carriers'))
    .addStringOption(o => o.setName('ticket_support_roles').setDescription('Up to 6 support role IDs, comma-separated'))
    .addStringOption(o => o.setName('reviewer_roles').setDescription('Roles allowed to review applications, comma-separated')),

  async execute(interaction) {
    if (!interaction.member.roles.cache.has('1479079737052762205')) {
      return interaction.reply({ content: '❌ You do not have the required role to use this command.', ephemeral: true });
    }
    const g = n => interaction.options.getChannel(n);
    const r = n => interaction.options.getRole(n);
    const u = n => interaction.options.getUser(n);
    const i = n => interaction.options.getInteger(n);
    const s = n => interaction.options.getString(n);

    const vouchCh            = g('vouch_channel');
    const ticketCh           = g('ticket_channel');
    const ticketCat          = g('ticket_category');
    const completedCh        = g('completed_channel');
    const rankedTicketCh     = g('ranked_ticket_channel');
    const prestigeTicketCh   = g('prestige_ticket_channel');
    const winstreakTicketCh  = g('winstreak_ticket_channel');
    const rankedPanelCh      = g('ranked_panel_channel');
    const prestigePanelCh    = g('prestige_panel_channel');
    const owner              = u('owner');
    const logCh              = g('ticket_log_channel');
    const appCh              = g('application_channel');
    const appReviewCh        = g('application_review_channel');
    const accountSaleCh      = g('account_sale_channel');
    const accountSaleTicketCh = g('account_sale_ticket_channel');
    const boosterRole        = r('booster_role');
    const proofCh            = g('proof_channel');
    const inactiveHours      = i('inactive_ticket_hours');
    const appTicketCh        = g('application_ticket_channel');
    const carrierRole        = r('carrier_role');
    const supportRolesStr    = s('ticket_support_roles');
    const reviewerRolesStr   = s('reviewer_roles');

    if (supportRolesStr) {
      const parts = supportRolesStr.split(',').map(x => x.trim()).filter(Boolean);
      if (parts.length > 6) {
        return interaction.reply({ content: '❌ You can only set up to 6 ticket support roles.', ephemeral: true });
      }
    }

    const updates = {};
    if (vouchCh)            updates.vouch_channel_id              = vouchCh.id;
    if (ticketCh)           updates.ticket_channel_id             = ticketCh.id;
    if (ticketCat)          updates.ticket_category_id            = ticketCat.id;
    if (completedCh)        updates.completed_channel_id          = completedCh.id;
    if (rankedTicketCh)     updates.ranked_ticket_channel_id      = rankedTicketCh.id;
    if (prestigeTicketCh)   updates.prestige_ticket_channel_id    = prestigeTicketCh.id;
    if (winstreakTicketCh)  updates.winstreak_ticket_channel_id   = winstreakTicketCh.id;
    if (rankedPanelCh)      updates.ranked_panel_channel_id       = rankedPanelCh.id;
    if (prestigePanelCh)    updates.prestige_panel_channel_id     = prestigePanelCh.id;
    if (owner)              updates.owner_id                      = owner.id;
    if (logCh)              updates.ticket_log_channel_id         = logCh.id;
    if (appCh)              updates.application_channel_id        = appCh.id;
    if (appReviewCh)        updates.application_review_channel_id = appReviewCh.id;
    if (accountSaleCh)      updates.account_sale_channel_id       = accountSaleCh.id;
    if (accountSaleTicketCh) updates.account_sale_ticket_channel_id = accountSaleTicketCh.id;
    if (boosterRole)        updates.booster_role_id               = boosterRole.id;
    if (proofCh)            updates.proof_channel_id              = proofCh.id;
    if (inactiveHours)      updates.inactive_ticket_hours         = inactiveHours;
    if (appTicketCh)        updates.application_ticket_channel_id = appTicketCh.id;
    if (carrierRole)        updates.carrier_role_id               = carrierRole.id;
    if (supportRolesStr)    updates.ticket_support_roles          = supportRolesStr;
    if (reviewerRolesStr)   updates.reviewer_roles                = reviewerRolesStr;

    if (Object.keys(updates).length) await setConfig(interaction.guildId, updates);

    const e = baseEmbed('⚙️ Server Configuration', SUCCESS, 'Bot settings updated successfully.');
    if (vouchCh)            e.addFields({ name: '⭐ Vouch Channel',               value: vouchCh.toString(),             inline: true });
    if (ticketCh)           e.addFields({ name: '🎫 Fallback Ticket Channel',     value: ticketCh.toString(),            inline: true });
    if (ticketCat)          e.addFields({ name: '📂 Ticket Category',             value: ticketCat.toString(),           inline: true });
    if (completedCh)        e.addFields({ name: '✅ Completed Channel',           value: completedCh.toString(),         inline: true });
    if (rankedTicketCh)     e.addFields({ name: '🔥 Ranked Ticket Channel',       value: rankedTicketCh.toString(),      inline: true });
    if (prestigeTicketCh)   e.addFields({ name: '✨ Prestige Ticket Channel',     value: prestigeTicketCh.toString(),    inline: true });
    if (winstreakTicketCh)  e.addFields({ name: '⚡ Winstreak Ticket Channel',    value: winstreakTicketCh.toString(),   inline: true });
    if (rankedPanelCh)      e.addFields({ name: '📢 Ranked Claiming Channel',     value: rankedPanelCh.toString(),       inline: true });
    if (prestigePanelCh)    e.addFields({ name: '📢 Prestige Claiming Channel',   value: prestigePanelCh.toString(),     inline: true });
    if (owner)              e.addFields({ name: '👑 Owner',                       value: `<@${owner.id}>`,               inline: true });
    if (logCh)              e.addFields({ name: '📋 Ticket Log Channel',          value: logCh.toString(),               inline: true });
    if (appCh)              e.addFields({ name: '📝 Application Channel',         value: appCh.toString(),               inline: true });
    if (appReviewCh)        e.addFields({ name: '🔍 App Review Channel',          value: appReviewCh.toString(),         inline: true });
    if (accountSaleCh)      e.addFields({ name: '🛒 Account Sale Channel',        value: accountSaleCh.toString(),       inline: true });
    if (accountSaleTicketCh) e.addFields({ name: '🛒 Account Ticket Channel',     value: accountSaleTicketCh.toString(), inline: true });
    if (boosterRole)        e.addFields({ name: '🟠 Booster Role',               value: boosterRole.toString(),         inline: true });
    if (proofCh)            e.addFields({ name: '📸 Proof Channel',              value: proofCh.toString(),             inline: true });
    if (inactiveHours)      e.addFields({ name: '⏰ Inactive Ticket Hours',       value: String(inactiveHours),          inline: true });
    if (appTicketCh)        e.addFields({ name: '📝 App Ticket Channel',          value: appTicketCh.toString(),         inline: true });
    if (carrierRole)        e.addFields({ name: '🚗 Carrier Role',               value: carrierRole.toString(),         inline: true });
    if (supportRolesStr)    e.addFields({ name: '🎫 Ticket Support Roles',       value: supportRolesStr,                inline: true });
    if (reviewerRolesStr)   e.addFields({ name: '🔍 Reviewer Roles',             value: reviewerRolesStr,               inline: true });

    e.addFields({
      name: 'ℹ️ Order Flow',
      value: (
        '1️⃣ Customer clicks **Ranked/Prestige Boost** → price estimate → ticket opens\n' +
        '2️⃣ Staff click **📢 Publish to Boosters** → set earnings → card in claiming channel\n' +
        '3️⃣ Booster clicks **🟠 Claim This Boost** → added to ticket\n' +
        '4️⃣ On completion, customer receives DM to rate the booster'
      ),
      inline: false,
    });

    await interaction.reply({ embeds: [e], ephemeral: true });
  },
};
