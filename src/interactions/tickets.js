const { ModalBuilder, TextInputBuilder, TextInputStyle, ActionRowBuilder, AttachmentBuilder, ChannelType } = require('discord.js');
const { queryOne } = require('../db/index');
const { getConfig, setConfig } = require('../db/index');
const { baseEmbed } = require('../utils/embeds');
const { createTicketThread, buildTranscript } = require('../utils/tickets');
const { removeTicketActivity, updateTicketActivity } = require('../utils/permissions');
const { PRIMARY, SUCCESS, HARDCODED_SUPPORT_ROLES } = require('../config/constants');

// ── Button handler ────────────────────────────────────────────────────────────
async function handleButton(interaction, client) {
  const id = interaction.customId;

  if (id === 'ticket_close_v2')        return handleCloseDirectly(interaction, client);
  if (id === 'ticket_close_reason_v2') return handleCloseBtn(interaction, client);
  if (id === 'ticket_general_btn')     return handleGeneralSupportBtn(interaction, client);
}

async function handleGeneralSupportBtn(interaction) {
  const guild  = interaction.guild;
  const member = interaction.member;
  const cfg    = await getConfig(interaction.guildId);

  const e = baseEmbed('ℹ️ General Support', SUCCESS);
  e.setDescription(
    `Welcome, ${member}!\n\n` +
    `📋 **Category:** General Support\n` +
    `🕐 **Opened:** <t:${Math.floor(Date.now() / 1000)}:F>\n\n` +
    'Staff will be with you shortly. Please describe your request in detail.'
  );
  e.setAuthor({ name: member.displayName, iconURL: member.displayAvatarURL() });

  const { ActionRowBuilder, ButtonBuilder, ButtonStyle } = require('discord.js');
  const closeView = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('ticket_close_v2').setLabel('Close Ticket').setStyle(ButtonStyle.Danger).setEmoji('🔒'),
    new ButtonBuilder().setCustomId('ticket_close_reason_v2').setLabel('Close With Reason').setStyle(ButtonStyle.Secondary).setEmoji('📝')
  );

  const overrideCh = cfg?.application_ticket_channel_id ?? null;
  const ticket = await createTicketThread(guild, member, `support-${member.user.username.slice(0, 12).toLowerCase()}`, e, closeView, cfg, overrideCh);

  const staffPings = HARDCODED_SUPPORT_ROLES.map(r => `<@&${r}>`).join(' ');
  await ticket.send({ content: staffPings, allowedMentions: { parse: ['roles'] } });
  await interaction.reply({ content: `✅ Support ticket created: ${ticket.toString()}`, ephemeral: true });
}
// NUOVO — funzione da aggiungere
async function handleCloseDirectly(interaction, client) {
  await interaction.deferReply({ ephemeral: false }).catch(() => {});

  const channel = interaction.channel;
  const guild   = interaction.guild;

  const messages = [];
  try {
    let fetched, before = null;
    do {
      fetched = await channel.messages.fetch({ limit: 100, before });
      fetched.forEach(m => messages.unshift(m));
      before = fetched.last()?.id;
    } while (fetched.size === 100 && messages.length < 500);
  } catch (_) {}

  const order = await queryOne(
    'SELECT * FROM orders WHERE ticket_channel_id = $1 ORDER BY created_at DESC LIMIT 1',
    [channel.id]
  );
  let authorMention = order?.user_id ? `<@${order.user_id}>` : null;
  if (!authorMention) {
    const firstHuman = messages.find(m => !m.author.bot);
    authorMention = firstHuman?.author.toString() ?? '—';
  }

  const chName = channel.name.toLowerCase();
  let ticketType = 'Support';
  if (chName.includes('ranked'))        ticketType = 'Ranked';
  else if (chName.includes('prestige')) ticketType = 'Prestige';
  else if (/apply|booster|staff|advertiser/.test(chName)) ticketType = 'Application';

  const htmlBuf = buildTranscript(messages, channel, ticketType, authorMention, interaction.member);
  const transcriptFile = new AttachmentBuilder(htmlBuf, { name: `transcript-${channel.name}.html` });

  const cfg     = await getConfig(guild.id);
  const logChId = cfg?.ticket_log_channel_id ? String(cfg.ticket_log_channel_id) : null;
  const logCh   = logChId ? guild.channels.cache.get(logChId) : null;

  await performClose(interaction, channel, guild, messages, order, authorMention, ticketType, transcriptFile, logCh, interaction.member, null);
                     }
async function handleCloseBtn(interaction, client) {
  const channel = interaction.channel;
  const guild   = interaction.guild;

  // Show modal FIRST — no defer before showModal
  const modal = new ModalBuilder()
    .setCustomId('close_reason_modal')
    .setTitle('Close Ticket with Reason')
    .addComponents(
      new ActionRowBuilder().addComponents(
        new TextInputBuilder()
          .setCustomId('close_reason')
          .setLabel('Reason for closing')
          .setStyle(TextInputStyle.Paragraph)
          .setPlaceholder('e.g. Order completed, customer request...')
          .setMaxLength(500)
      )
    );

  pendingCloses.set(interaction.user.id, { channel, guild, closedBy: interaction.member });
  await interaction.showModal(modal);
}

// ── Close with optional reason (called from modal or direct) ──────────────────
async function performClose(interaction, channel, guild, messages, order, authorMention, ticketType, transcriptFile, logCh, closedBy, reason) {
  const e = baseEmbed('📋 Ticket Closed', PRIMARY);
  e.addFields(
    { name: '📂 Channel Type',  value: `↳ ${ticketType}`,          inline: false },
    { name: '👤 Ticket Author', value: `↳ ${authorMention}`,       inline: true  },
    { name: '🔒 Closed By',     value: `↳ ${closedBy.toString()}`, inline: true  },
  );
  if (reason) e.addFields({ name: '📝 Close Reason', value: `↳ ${reason}`, inline: false });

  if (logCh) await logCh.send({ embeds: [e], files: [transcriptFile] }).catch(() => {});

  try { await channel.send({ embeds: [e] }); } catch (_) {}

  // Release booster if workspace thread
  if (channel.name.startsWith('active-')) {
    await queryOne(
      "UPDATE orders SET status = 'pending', booster_id = NULL, claimed_at = NULL, workspace_channel_id = NULL WHERE workspace_channel_id = $1 AND status = 'claimed'",
      [channel.id]
    ).catch(() => {});
  }

  await removeTicketActivity(channel.id);

  // Remove temporary ViewChannel overwrites (customer + booster) from the parent channel
  if (channel.type === ChannelType.PublicThread || channel.type === ChannelType.PrivateThread) {
    if (channel.parent) {
      const userId    = order?.user_id    ? String(order.user_id)    : (messages.find(m => !m.author.bot)?.author.id ?? null);
      const boosterId = order?.booster_id ? String(order.booster_id) : null;

      if (userId)    { try { await channel.parent.permissionOverwrites.delete(userId,    'Ticket closed – removing temporary customer access'); } catch (_) {} }
      if (boosterId) { try { await channel.parent.permissionOverwrites.delete(boosterId, 'Ticket closed – removing temporary booster access');  } catch (_) {} }
    }
  }
  await new Promise(r => setTimeout(r, 3000));
  try {
    if (channel.type === ChannelType.PublicThread || channel.type === ChannelType.PrivateThread) {
      if (channel.archived) await channel.setArchived(false);
    }
    await channel.delete(`Closed by ${closedBy.user?.tag}`);
  } catch (_) {}
}

const pendingCloses = new Map();

// ── Modal: ticket panel setup ─────────────────────────────────────────────────
async function handleSetupModal(interaction) {
  const title = interaction.fields.getTextInputValue('panel_title');
  const desc  = interaction.fields.getTextInputValue('panel_desc');
  await setConfig(interaction.guildId, { ticket_panel_title: title, ticket_panel_desc: desc });
  await interaction.reply({ content: '✅ Ticket panel configuration saved.', ephemeral: true });
}

// ── Modal: close with reason ──────────────────────────────────────────────────
async function handleCloseModal(interaction, client) {
  const reason = interaction.fields.getTextInputValue('close_reason');
  await interaction.deferReply({ ephemeral: false }).catch(() => {});

  const ctx = pendingCloses.get(interaction.user.id);
  if (!ctx) return;
  pendingCloses.delete(interaction.user.id);

  const { channel, guild, closedBy } = ctx;

  const messages = [];
  try {
    let fetched;
    let before = null;
    do {
      fetched = await channel.messages.fetch({ limit: 100, before });
      fetched.forEach(m => messages.unshift(m));
      before = fetched.last()?.id;
    } while (fetched.size === 100 && messages.length < 500);
  } catch (_) {}

  const order = await queryOne(
    'SELECT * FROM orders WHERE ticket_channel_id = $1 ORDER BY created_at DESC LIMIT 1',
    [channel.id]
  );
  let authorMention = order?.user_id ? `<@${order.user_id}>` : null;
  if (!authorMention) {
    const firstHuman = messages.find(m => !m.author.bot);
    authorMention = firstHuman?.author.toString() ?? '—';
  }

  const chName = channel.name.toLowerCase();
  let ticketType = 'Support';
  if (chName.includes('ranked'))        ticketType = 'Ranked';
  else if (chName.includes('prestige')) ticketType = 'Prestige';
  else if (/apply|booster|staff|advertiser/.test(chName)) ticketType = 'Application';

  const htmlBuf = buildTranscript(messages, channel, ticketType, authorMention, closedBy);
  const transcriptFile = new AttachmentBuilder(htmlBuf, { name: `transcript-${channel.name}.html` });

  const cfg     = await getConfig(guild.id);
  const logChId = cfg?.ticket_log_channel_id ? String(cfg.ticket_log_channel_id) : null;
  const logCh   = logChId ? guild.channels.cache.get(logChId) : null;

  await performClose(interaction, channel, guild, messages, order, authorMention, ticketType, transcriptFile, logCh, closedBy, reason);
}

// ── Select: support center ────────────────────────────────────────────────────
async function handleSelect(interaction, client) {
  const id     = interaction.customId;
  const choice = interaction.values[0];

  if (id === 'support_center_select_v1') return handleSupportCenterSelect(interaction, choice);
  if (id === 'application_center_select_v1') return handleApplicationCenterSelect(interaction, choice);
}

async function handleSupportCenterSelect(interaction, choice) {
  const { ButtonBuilder, ButtonStyle } = require('discord.js');
  const guild  = interaction.guild;
  const member = interaction.member;
  const cfg    = await getConfig(interaction.guildId);

  const closeView = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('ticket_close_v2').setLabel('Close Ticket').setStyle(ButtonStyle.Danger).setEmoji('🔒'),
    new ButtonBuilder().setCustomId('ticket_close_reason_v2').setLabel('Close With Reason').setStyle(ButtonStyle.Secondary).setEmoji('📝')
  );

  if (choice === 'support') {
    const e = baseEmbed('<:microphone:1491490055636647966> Support Ticket', SUCCESS);
    e.setDescription('## Your support request has been successfully created.\n\nOur team will assist you shortly.\n\nYou can manage your ticket using the options below.');
    const ticket = await createTicketThread(guild, member, `support-${member.user.username.slice(0, 12).toLowerCase()}`, e, closeView, cfg);
    const staffPings = HARDCODED_SUPPORT_ROLES.map(r => `<@&${r}>`).join(' ');
    await ticket.send({ content: staffPings, allowedMentions: { parse: ['roles'] } });
    await interaction.reply({ content: `✅ Support ticket created: ${ticket.toString()}`, ephemeral: true });

  } else if (choice === 'apply') {
    const { StringSelectMenuBuilder, StringSelectMenuOptionBuilder } = require('discord.js');
    const e = baseEmbed('<:Info:1501221322183934002> Application Center', PRIMARY);
    e.setDescription(
      '>>> Select the role you want to apply for below.\n\n' +
      '<:rocket:1491490870979985438> **Booster** — Masters III minimum\n' +
      '<:shield:1491489447445794866> **Staff** — Fluent English & trusted member\n' +
      '<:Carry:1501221214251651082> **Advertiser** — Previous advertising experience preferred'
    );
    const appSelect = new StringSelectMenuBuilder()
      .setCustomId('application_center_select_v1')
      .setPlaceholder('Select an application type...')
      .addOptions(
        new StringSelectMenuOptionBuilder().setLabel('Booster Application').setValue('apply_booster').setEmoji('<:rocket:1491490870979985438>').setDescription('Apply as a booster'),
        new StringSelectMenuOptionBuilder().setLabel('Staff Application').setValue('apply_staff').setEmoji('<:shield:1491489447445794866>').setDescription('Apply for staff team'),
        new StringSelectMenuOptionBuilder().setLabel('Advertiser Application').setValue('apply_advertiser').setEmoji('<:Carry:1501221214251651082>').setDescription('Apply as an advertiser'),
      );
    await interaction.reply({ embeds: [e], components: [new ActionRowBuilder().addComponents(appSelect)], ephemeral: true });

  } else if (choice === 'services') {
    const e = baseEmbed('<:rocket:1491490870979985438> Our Services', PRIMARY);
    e.setDescription('> <:master:1491521740860428459> <#1477338397570760784>\n> <:copyright:1485657838897467534> <#1355262063437414564>\n\n-# Please head over to one of these channels to create your order.');
    await interaction.reply({ embeds: [e], ephemeral: true });
  }
}

async function handleApplicationCenterSelect(interaction, choice) {
  const { ButtonBuilder, ButtonStyle } = require('discord.js');
  const guild  = interaction.guild;
  const member = interaction.member;
  const cfg    = await getConfig(interaction.guildId);

  const titles = {
    apply_booster:    '<:rocket:1491490870979985438> Booster Application',
    apply_staff:      '<:shield:1491489447445794866> Staff Application',
    apply_advertiser: '<:Carry:1501221214251651082> Advertiser Application',
  };
  const slugs = { apply_booster: 'booster', apply_staff: 'staff', apply_advertiser: 'advertiser' };

  const title    = titles[choice];
  const slug     = slugs[choice];
  const overrideChId = '1491397629546860614'; // hardcoded application ticket channel

  const e = baseEmbed(title, PRIMARY);
  e.setDescription(`## Your ${slug} application has been successfully created.\n\nOur management team will review your application shortly.\n\nYou can manage your ticket using the options below.`);
  
  const closeView = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('ticket_close_v2').setLabel('Close Ticket').setStyle(ButtonStyle.Danger).setEmoji('🔒'),
    new ButtonBuilder().setCustomId('ticket_close_reason_v2').setLabel('Close With Reason').setStyle(ButtonStyle.Secondary).setEmoji('📝')
  );

  const ticket = await createTicketThread(guild, member, `${slug}-${member.user.username.slice(0, 12).toLowerCase()}`, e, closeView, cfg, overrideChId);
  const staffPings = HARDCODED_SUPPORT_ROLES.map(r => `<@&${r}>`).join(' ');
  await ticket.send({ content: staffPings, allowedMentions: { parse: ['roles'] } });
  await interaction.reply({ content: `✅ ${title} ticket created: ${ticket.toString()}`, ephemeral: true });
}

module.exports = { handleButton, handleSelect, handleCloseModal, handleSetupModal };
