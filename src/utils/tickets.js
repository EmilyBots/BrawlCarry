const { ChannelType, PermissionOverwrite } = require('discord.js');
const { HARDCODED_SUPPORT_ROLES } = require('../config/constants');
const { updateTicketActivity } = require('./permissions');

/**
 * Create a ticket thread or text channel for a member.
 * Prefers a private thread inside the configured ticket channel; falls back to
 * a public thread, then a dedicated text channel in the configured category.
 *
 * @param {import('discord.js').Guild} guild
 * @param {import('discord.js').GuildMember} member
 * @param {string} name  channel/thread name
 * @param {import('discord.js').EmbedBuilder} topicEmbed
 * @param {import('discord.js').ActionRowBuilder} view
 * @param {object|null} cfg   guild config row
 * @param {bigint|null} overrideChannelId  force a specific parent channel
 * @returns {Promise<import('discord.js').ThreadChannel|import('discord.js').TextChannel>}
 */
async function createTicketThread(guild, member, name, topicEmbed, view, cfg, overrideChannelId = null, pingContent = null) {
  const ticketChId = overrideChannelId ?? cfg?.ticket_channel_id ?? null;
  const categoryId = cfg?.ticket_category_id ?? null;

  if (ticketChId) {
    const textCh = guild.channels.cache.get(String(ticketChId));
    if (textCh?.isTextBased() && textCh.type === ChannelType.GuildText) {
      // Grant temporary view access to the member so they can see the thread
      try {
        await textCh.permissionOverwrites.edit(member, {
  ViewChannel: true,
});
      } catch (_) {}

      let thread;
      try {
        thread = await textCh.threads.create({
          name,
          type:   ChannelType.PrivateThread,
          reason: `Ticket opened by ${member.user.tag}`,
        });
      } catch (_) {
        thread = await textCh.threads.create({
          name,
          type:   ChannelType.PublicThread,
          reason: `Ticket opened by ${member.user.tag}`,
        });
      }

      await thread.members.add(member.id);
      if (pingContent) await thread.send({ content: pingContent, allowedMentions: { parse: ['roles'] } });
      await thread.send({ content: member.toString(), embeds: [topicEmbed], components: [view] });
      await updateTicketActivity(thread.id, guild.id);
      return thread;
    }
  }

  // Fallback: create a dedicated text channel with permission overwrites
  const category = categoryId ? guild.channels.cache.get(String(categoryId)) : null;

  const overwrites = [
    {
      id:   guild.id,  // @everyone
      deny: ['ViewChannel'],
    },
    {
      id:    member.id,
      allow: ['ViewChannel', 'SendMessages', 'ReadMessageHistory'],
    },
  ];

  // Grant staff roles
  for (const role of guild.roles.cache.values()) {
    if (role.permissions.has('Administrator') || role.permissions.has('ManageChannels')) {
      overwrites.push({ id: role.id, allow: ['ViewChannel', 'SendMessages'] });
    }
  }
  for (const rid of HARDCODED_SUPPORT_ROLES) {
    const role = guild.roles.cache.get(String(rid));
    if (role) overwrites.push({ id: role.id, allow: ['ViewChannel', 'SendMessages'] });
  }

  const ch = await guild.channels.create({
    name,
    type:               ChannelType.GuildText,
    parent:             category?.id ?? null,
    permissionOverwrites: overwrites,
    topic:              `Opened by ${member.user.tag} | ${new Date().toISOString().slice(0, 16)} UTC`,
  });

  if (pingContent) await ch.send({ content: pingContent, allowedMentions: { parse: ['roles'] } });
  await ch.send({ content: member.toString(), embeds: [topicEmbed], components: [view] });
  await updateTicketActivity(ch.id, guild.id);
  return ch;
}

/**
 * Build an HTML transcript from a list of Discord Messages.
 * Returns a Buffer containing the HTML.
 *
 * @param {import('discord.js').Message[]} messages
 * @param {import('discord.js').TextChannel|import('discord.js').ThreadChannel} channel
 * @param {string} ticketType
 * @param {string} authorMention
 * @param {import('discord.js').GuildMember} closedBy
 * @returns {Buffer}
 */
function buildTranscript(messages, channel, ticketType, authorMention, closedBy) {
  const guild     = channel.guild;
  const guildIcon = guild.iconURL() ?? 'https://cdn.discordapp.com/embed/avatars/0.png';
  const openedTs  = messages[0]?.createdAt.toUTCString().slice(0, 22) ?? '—';
  const closedTs  = new Date().toUTCString().slice(0, 22);

  function esc(s) {
    return (s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function avatar(user) {
    try { return user.displayAvatarURL({ size: 64 }); }
    catch (_) { return 'https://cdn.discordapp.com/embed/avatars/0.png'; }
  }

  function renderMsg(msg) {
    try {
      const ts      = msg.createdAt.toUTCString().slice(0, 22);
      const av      = avatar(msg.author);
      const name    = esc(msg.member?.displayName ?? msg.author.username);
      const content = esc(msg.content) || "<em class='muted'>—</em>";

      let parts = [
        `<div class="msg">`,
        `<img class="av" src="${av}" loading="lazy">`,
        `<div class="body">`,
        `<div class="row"><span class="name">${name}</span><span class="ts">${ts}</span></div>`,
        `<div class="content">${content}</div>`,
      ];

      for (const a of msg.attachments.values()) {
        if (a.contentType?.startsWith('image')) {
          parts.push(`<a href="${a.url}" target="_blank"><img class="att" src="${a.url}" loading="lazy"></a>`);
        } else {
          parts.push(`<a class="file" href="${a.url}" target="_blank">📎 ${esc(a.name)}</a>`);
        }
      }

      for (const emb of msg.embeds) {
        const color  = emb.color ? `#${emb.color.toString(16).padStart(6, '0')}` : '#5865f2';
        const etitle = esc(emb.title ?? '');
        const edesc  = esc(emb.description ?? '');
        parts.push(`<div class="emb" style="border-color:${color}"><div class="et">${etitle}</div><div class="ed">${edesc}</div></div>`);
      }

      parts.push('</div></div>');
      return parts.join('');
    } catch (_) {
      return '';
    }
  }

  const msgsHtml = messages.map(renderMsg).join('\n');

  const html = `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Transcript — ${esc(channel.name)}</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f1013;color:#dcddde;font-family:"gg sans","Helvetica Neue",Arial,sans-serif;font-size:15px;line-height:1.6}
header{background:#1a1b1e;padding:20px 32px;border-bottom:1px solid #2b2d31;display:flex;align-items:center;gap:16px}
header img{width:48px;height:48px;border-radius:50%;border:2px solid #5865f2}
.hd h1{font-size:17px;font-weight:700;color:#fff;margin-bottom:2px}
.hd p{font-size:12px;color:#72767d}
.badge{display:inline-block;background:#5865f2;color:#fff;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;text-transform:uppercase;letter-spacing:.5px;margin-left:8px;vertical-align:middle}
.meta-bar{display:flex;flex-wrap:wrap;gap:0;background:#1a1b1e;border-top:1px solid #2b2d31;border-bottom:1px solid #2b2d31;padding:0 32px}
.mi{padding:12px 24px 12px 0;margin-right:24px;border-right:1px solid #2b2d31}
.mi:last-child{border-right:none}
.mi label{display:block;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#72767d;margin-bottom:4px}
.mi span{font-size:13px;color:#e3e5e8;font-weight:500}
.msgs{padding:16px 32px 48px}
.msg{display:flex;gap:14px;padding:4px 8px;border-radius:6px;margin-bottom:1px}
.msg:hover{background:#1e1f22}
.av{width:38px;height:38px;border-radius:50%;flex-shrink:0;margin-top:4px;object-fit:cover}
.body{flex:1;min-width:0}
.row{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:2px}
.name{font-weight:700;color:#fff;font-size:14px}
.ts{font-size:11px;color:#72767d}
.content{word-break:break-word;white-space:pre-wrap;color:#dcddde;font-size:14px}
.muted{color:#72767d;font-style:italic}
.att{max-width:340px;max-height:220px;border-radius:6px;margin-top:8px;display:block;object-fit:cover;border:1px solid #2b2d31}
.file{display:inline-flex;align-items:center;gap:6px;margin-top:6px;color:#00aff4;background:#1e1f22;padding:5px 12px;border-radius:6px;font-size:12px;text-decoration:none;border:1px solid #2b2d31}
.emb{border-left:4px solid #5865f2;background:#1e1f22;border-radius:0 6px 6px 0;padding:10px 14px;margin-top:8px;max-width:520px;border-top:1px solid #2b2d31;border-right:1px solid #2b2d31;border-bottom:1px solid #2b2d31}
.et{font-weight:700;color:#fff;font-size:13px;margin-bottom:4px}
.ed{font-size:12px;color:#b5bac1;white-space:pre-wrap}
footer{text-align:center;padding:20px;font-size:11px;color:#4e5058;border-top:1px solid #1a1b1e}
</style></head><body>
<header>
  <img src="${guildIcon}">
  <div class="hd">
    <h1>${esc(guild.name)} <span class="badge">${ticketType}</span></h1>
    <p>#${esc(channel.name)} &nbsp;·&nbsp; ${messages.length} messages</p>
  </div>
</header>
<div class="meta-bar">
  <div class="mi"><label>Opened</label><span>${openedTs} UTC</span></div>
  <div class="mi"><label>Closed</label><span>${closedTs} UTC</span></div>
  <div class="mi"><label>Ticket Author</label><span>${esc(authorMention.replace(/<@!?|>/g, ''))}</span></div>
  <div class="mi"><label>Closed By</label><span>${esc(closedBy.displayName ?? closedBy.user?.username)}</span></div>
  <div class="mi"><label>Messages</label><span>${messages.length}</span></div>
</div>
<div class="msgs">${msgsHtml}</div>
<footer>Generated by ${esc(guild.name)} · ${closedTs} UTC</footer>
</body></html>`;

  return Buffer.from(html, 'utf8');
}

module.exports = { createTicketThread, buildTranscript };
