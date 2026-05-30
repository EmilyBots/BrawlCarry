const { queryAll, queryOne } = require('../db/index');
const { baseEmbed } = require('../utils/embeds');
const { SUCCESS, DANGER, GOLD, FOOTER_BRAND } = require('../config/constants');

// ── Core: termina un singolo giveaway ────────────────────────────────────────
async function finishGiveaway(client, ga) {
  const gaId         = ga.id;
  const participants = JSON.parse(ga.participants || '[]');
  const unique       = [...new Set(participants)];

  if (!unique.length) {
    await queryOne("UPDATE giveaways SET winner_ids = '[\"NO_WINNER\"]' WHERE id = $1", [gaId]);
    const ch = await resolveChannel(client, ga.channel_id);
    if (ch) {
      const e = baseEmbed(`🎁 ${ga.prize} — Giveaway Ended`, DANGER);
      e.setDescription('😔 No one entered this giveaway — there are no winners.');
      e.setFooter({ text: `${FOOTER_BRAND} | ID: ${gaId}` });
      await ch.send({ embeds: [e] }).catch(() => {});
    }
    return { noWinner: true };
  }

  const winnerIds = unique.sort(() => 0.5 - Math.random()).slice(0, ga.winners);
  await queryOne('UPDATE giveaways SET winner_ids = $1 WHERE id = $2', [JSON.stringify(winnerIds), gaId]);

  const ch = await resolveChannel(client, ga.channel_id, gaId);
  if (!ch) {
    console.warn(`[WARN] finishGiveaway: could not find channel for ${gaId}`);
    return { noChannel: true, winnerIds };
  }

  const winnerMentions = winnerIds.map(w => `<@${w}>`).join(' ');
  const e = baseEmbed(`🎁 ${ga.prize} — Giveaway Ended`, SUCCESS);
  e.addFields(
    { name: '🏆 Winners',            value: winnerMentions,                        inline: false },
    { name: '👥 Total Participants', value: `**${unique.length.toLocaleString()}**`, inline: true  },
    { name: '🆔 Giveaway ID',        value: `\`${gaId}\``,                          inline: true  },
  )
  .setFooter({ text: `${FOOTER_BRAND} | ID: ${gaId}` })
  .setTimestamp();

  await ch.send({
    content: `🎉 Congratulations ${winnerMentions}! You won **${ga.prize}**!`,
    embeds: [e],
    allowedMentions: { users: winnerIds },
  }).catch(err => console.warn(`[WARN] finishGiveaway announce ${gaId}:`, err));

  return { winnerIds };
}

// ── Giveaway end loop ─────────────────────────────────────────────────────────
function startGiveawayEndLoop(client) {
  const INTERVAL = 60_000; // 1 minute

  async function tick() {
    try {
      const expired = await queryAll(
        "SELECT * FROM giveaways WHERE ended_at IS NOT NULL AND ended_at <= NOW() AND (winner_ids IS NULL OR winner_ids = '' OR winner_ids = '[]')"
      );

      for (const ga of expired) {
        await finishGiveaway(client, ga).catch(err =>
          console.warn(`[WARN] giveaway_end_loop: error finishing ${ga.id}:`, err)
        );
      }
    } catch (err) {
      console.error('[WARN] giveaway_end_loop error:', err);
    }

    setTimeout(tick, INTERVAL);
  }

  tick();
}

// ── Core: invia il reminder per un singolo giveaway ──────────────────────────
function formatRemaining(seconds) {
  if (seconds >= 82_800) return '24 hours';   // ≥ 23h
  if (seconds >= 39_600) return '12 hours';   // ≥ 11h
  if (seconds >= 18_000) return '6 hours';    // ≥ 5h
  if (seconds >= 3_000)  return '1 hour';     // ≥ 50m
  const m = Math.round(seconds / 60);
  return `${m} minute${m !== 1 ? 's' : ''}`;
}

async function sendGiveawayReminder(client, ga, remainingSeconds = null) {
  const ch = await resolveChannel(client, ga.channel_id, ga.id);
  if (!ch) return false;

  const endsAt  = new Date(ga.ended_at).getTime();
  const seconds = remainingSeconds ?? Math.floor((endsAt - Date.now()) / 1000);
  const timeStr = formatRemaining(seconds);

  const { EmbedBuilder } = require('discord.js');
  const reminderE = new EmbedBuilder()
    .setColor(0xFFD700)
    .setDescription(
      `<a:giveaway:1506218898255773827> ***GIVEAWAY ENDING SOON!*** <a:giveaway:1506218898255773827>\n\n` +
      `## <:Gift:1509855137156567130> **${ga.prize}**\n\n` +
      `## <:warning:1508835752430141482> Last **${timeStr}** to enter!\n\n` +
      `**Good luck everyone** 🍀`
    );

  await ch.send({
    content: `@everyone`,
    embeds: [reminderE],
    allowedMentions: { parse: ['everyone'] },
  }).catch(() => {});

  return true;
}

// ── Giveaway reminder loop ────────────────────────────────────────────────────
function startGiveawayReminderLoop(client) {
  const INTERVAL = 300_000; // 5 minutes

  // 24h reminder window: fires when between 24h5m and 23h45m remain.
  // Wide enough to survive any 5-min tick gap, but never overlaps itself.
  const WINDOW_UPPER = 86_700; // 24h 5m  in seconds
  const WINDOW_LOWER = 85_500; // 23h 45m in seconds

  async function tick() {
    try {
      // FIX: Query now also excludes giveaways that already have reminder_sent = TRUE.
      // This replaces the in-memory Map which was lost on every bot restart.
      //
      // REQUIRED: Add this column once to your DB:
      //   ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS reminder_sent BOOLEAN NOT NULL DEFAULT FALSE;
      //
      // If you cannot alter the schema, see the fallback comment below.
      const giveaways = await queryAll(
        `SELECT * FROM giveaways
         WHERE (winner_ids IS NULL OR winner_ids = '' OR winner_ids = '[]')
           AND ended_at IS NOT NULL
           AND reminder_sent = FALSE`
      );

      const now = Date.now();

      for (const ga of giveaways) {
        const endsAt    = new Date(ga.ended_at).getTime();
        const remaining = Math.floor((endsAt - now) / 1000);

        // Skip already-expired or not-yet-in-window giveaways.
        if (remaining <= 0) continue;

        // FIX: Skip giveaways shorter than 24h total — they will never
        // pass through the 24h window so a reminder makes no sense.
        // created_at must exist on the row. If it doesn't, remove this block
        // and accept that sub-24h giveaways are silently skipped by the window check.
        if (ga.created_at) {
          const totalDuration = (endsAt - new Date(ga.created_at).getTime()) / 1000;
          if (totalDuration < 86_400) continue; // giveaway is shorter than 24h
        }

        // FIX: Only one reminder — exactly when 24h remains.
        // Window is intentionally wider than the tick interval to avoid missed ticks.
        const inWindow = remaining <= WINDOW_UPPER && remaining > WINDOW_LOWER;
        if (!inWindow) continue;

        // Mark FIRST — crash mid-send cannot cause duplicate on next tick.
        await queryOne('UPDATE giveaways SET reminder_sent = TRUE WHERE id = $1', [ga.id]);
        await sendGiveawayReminder(client, ga, remaining);
      }
    } catch (err) {
      console.error('[WARN] giveaway_reminder_loop error:', err);
    }

    setTimeout(tick, INTERVAL);
  }

  tick();
}

// ── Channel resolver ──────────────────────────────────────────────────────────
async function resolveChannel(client, channelId, gaId = null) {
  if (channelId) {
    for (const guild of client.guilds.cache.values()) {
      const ch = guild.channels.cache.get(String(channelId));
      if (ch) return ch;
    }
  }

  // Fallback: scan for embed with gaId in footer
  if (gaId) {
    for (const guild of client.guilds.cache.values()) {
      for (const ch of guild.channels.cache.filter(c => c.isTextBased()).values()) {
        try {
          const msgs = await ch.messages.fetch({ limit: 100 });
          const match = msgs.find(m => m.author.id === client.user.id && m.embeds.some(e => e.footer?.text?.includes(gaId)));
          if (match) return ch;
        } catch (_) {}
      }
    }
  }

  return null;
}

module.exports = { startGiveawayEndLoop, startGiveawayReminderLoop, finishGiveaway, sendGiveawayReminder, resolveChannel };
