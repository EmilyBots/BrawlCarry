const {
  ModalBuilder, TextInputBuilder, TextInputStyle, ActionRowBuilder, EmbedBuilder,
} = require('discord.js');
const { getConfig } = require('../db/index');
const { baseEmbed } = require('../utils/embeds');
const { PRIMARY, SUCCESS, DANGER, FOOTER_BRAND } = require('../config/constants');

// ── Accept / Reject buttons ───────────────────────────────────────────────────
async function handleButton(interaction) {
  const id = interaction.customId;
  if (id === 'app_accept_v1') return handleAccept(interaction);
  if (id === 'app_reject_v1') return handleReject(interaction);
}

async function resolveApplicantFromEmbed(interaction) {
  const embed = interaction.message?.embeds[0];
  if (!embed) return null;

  let applicantId = null;
  let roleName    = null;

  for (const field of embed.fields) {
    if (field.name.includes('User ID')) {
      try { applicantId = field.value.replace(/`/g, '').trim(); } catch (_) {}
    }
    if (field.name.includes('Role Applied')) {
      roleName = field.value.replace(/\*/g, '').trim();
    }
  }
  return { applicantId, roleName };
}

async function checkReviewerPermission(interaction) {
  const cfg            = await getConfig(interaction.guildId);
  const reviewerRoles  = new Set();
  if (cfg?.reviewer_roles) {
    for (const rid of cfg.reviewer_roles.split(',')) {
      const clean = rid.trim().replace(/<@&|>/g, '');
      if (clean) reviewerRoles.add(clean);
    }
  }
  const memberRoles = new Set(interaction.member.roles.cache.keys());
  const hasRole     = [...reviewerRoles].some(r => memberRoles.has(r));
  return interaction.memberPermissions?.has('ManageRoles') || hasRole;
}

async function handleAccept(interaction) {
  if (!(await checkReviewerPermission(interaction))) {
    return interaction.reply({ content: '❌ You don\'t have permission to review applications.', ephemeral: true });
  }

  const ctx = await resolveApplicantFromEmbed(interaction);
  if (!ctx?.applicantId || !ctx?.roleName) {
    return interaction.reply({ content: '❌ Could not read application data from embed.', ephemeral: true });
  }

  const member    = interaction.guild.members.cache.get(ctx.applicantId) ?? await interaction.guild.members.fetch(ctx.applicantId).catch(() => null);
  let resultText  = '';

  if (member) {
    const roleObj = interaction.guild.roles.cache.find(r => r.name === ctx.roleName);
    if (roleObj) {
      try {
        await member.roles.add(roleObj, `Application accepted by ${interaction.user.tag}`);
        resultText = ` Role **${ctx.roleName}** has been assigned.`;
      } catch (_) {
        resultText = ' ⚠️ Could not assign role (missing permissions).';
      }
    } else {
      resultText = ` ⚠️ Role **${ctx.roleName}** not found — create it manually.`;
    }

    try {
      const dmE = baseEmbed('✅ Application Accepted!', SUCCESS);
      dmE.setDescription(`Congratulations! Your **${ctx.roleName}** application in **${interaction.guild.name}** has been accepted.\n\nWelcome to the team! 🎉`);
      await member.send({ embeds: [dmE] });
    } catch (_) {}
  }

  const orig = interaction.message.embeds[0];
  const updated = EmbedBuilder.from(orig)
    .setColor(SUCCESS)
    .setTitle(`✅ ACCEPTED — ${orig.title ?? ''}`)
    .addFields({ name: '✅ Reviewed By', value: interaction.user.toString(), inline: true });

  await interaction.message.edit({ embeds: [updated], components: [] });
  await interaction.reply({ content: `✅ Application accepted.${resultText}`, ephemeral: true });
}

async function handleReject(interaction) {
  if (!(await checkReviewerPermission(interaction))) {
    return interaction.reply({ content: '❌ You don\'t have permission to review applications.', ephemeral: true });
  }

  const ctx = await resolveApplicantFromEmbed(interaction);
  if (!ctx?.applicantId || !ctx?.roleName) {
    return interaction.reply({ content: '❌ Could not read application data from embed.', ephemeral: true });
  }

  const member = interaction.guild.members.cache.get(ctx.applicantId) ?? await interaction.guild.members.fetch(ctx.applicantId).catch(() => null);
  if (member) {
    try {
      const dmE = baseEmbed('❌ Application Rejected', DANGER);
      dmE.setDescription(`Unfortunately, your **${ctx.roleName}** application in **${interaction.guild.name}** has been rejected.\n\nYou may re-apply in the future. Thank you for your interest.`);
      await member.send({ embeds: [dmE] });
    } catch (_) {}
  }

  const orig = interaction.message.embeds[0];
  const updated = EmbedBuilder.from(orig)
    .setColor(DANGER)
    .setTitle(`❌ REJECTED — ${orig.title ?? ''}`)
    .addFields({ name: '❌ Reviewed By', value: interaction.user.toString(), inline: true });

  await interaction.message.edit({ embeds: [updated], components: [] });
  await interaction.reply({ content: '❌ Application rejected and applicant notified.', ephemeral: true });
}

// ── Application modal submit ──────────────────────────────────────────────────
async function handleModal(interaction) {
  const id   = interaction.customId; // app_modal_booster | app_modal_staff | app_modal_advertiser
  const role = id.replace('app_modal_', '').charAt(0).toUpperCase() + id.replace('app_modal_', '').slice(1);

  const guild    = interaction.guild;
  const member   = interaction.member;
  const cfg      = await getConfig(interaction.guildId);
  const reviewCh = cfg?.application_review_channel_id
    ? guild.channels.cache.get(String(cfg.application_review_channel_id))
    : null;

  if (!reviewCh) {
    return interaction.reply({ content: '❌ Application review channel not configured. Ask an admin to run `/setup`.', ephemeral: true });
  }

  const why       = interaction.fields.getTextInputValue('why');
  const exp       = interaction.fields.getTextInputValue('exp');
  const age       = interaction.fields.getTextInputValue('age');
  const extra     = interaction.fields.getTextInputValue('extra') || null;
  let rankProof   = null;
  try { rankProof = interaction.fields.getTextInputValue('rank_proof'); } catch (_) {}

  const e = baseEmbed(`📝 New ${role} Application`, PRIMARY);
  e.setAuthor({ name: member.displayName, iconURL: member.displayAvatarURL() });
  e.addFields(
    { name: '👤 Applicant',    value: member.toString(),    inline: true },
    { name: '🆔 User ID',      value: `\`${member.id}\``,  inline: true },
    { name: '🎭 Role Applied', value: `**${role}**`,        inline: true },
    { name: '❓ Why This Role', value: why,                 inline: false },
    { name: '📋 Experience',   value: exp,                  inline: false },
    { name: '🎂 Age',          value: age,                  inline: true },
  );
  if (rankProof) e.addFields({ name: '🏆 Rank Proof', value: rankProof, inline: false });
  if (extra)     e.addFields({ name: '💬 Extra Info', value: extra,     inline: false });
  e.setFooter({ text: `${FOOTER_BRAND} | Use buttons below to accept or reject` });

  const { ButtonBuilder, ButtonStyle } = require('discord.js');
  const reviewView = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('app_accept_v1').setLabel('Accept').setStyle(ButtonStyle.Success).setEmoji('✅'),
    new ButtonBuilder().setCustomId('app_reject_v1').setLabel('Reject').setStyle(ButtonStyle.Danger).setEmoji('❌'),
  );

  await reviewCh.send({ embeds: [e], components: [reviewView] });
  await interaction.reply({ content: `✅ Your **${role}** application has been submitted! Staff will review it shortly.`, ephemeral: true });
}

module.exports = { handleButton, handleModal };
