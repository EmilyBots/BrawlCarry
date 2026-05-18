const { queryAll, queryOne } = require('../db/index');
const { baseEmbed } = require('../utils/embeds');
const { SUCCESS, DANGER, GOLD, FOOTER_BRAND } = require('../config/constants');

// ── Giveaway end loop ─────────────────────────────────────────────────────────
function startGiveawayEndLoop(client) {
  const INTERVAL = 60_000; // 1 minute

  async function tick() {
    try {
      const expired = await queryAll(
        "SELECT * FROM giveaways WHERE ended_at IS NOT NULL AND ended_at <= NOW() AND (winner_ids IS NULL OR winner_ids = '' OR winner_ids = '[]')"
      );

      for (const ga of expired) {
        const gaId        = ga.id;
        const participants = JSON.parse(ga.participants || '[]');
        const unique       = [...new Set(participants)];

        if (!unique.length) {
          await queryOne("UPDATE giveaways SET winner_ids = '[]' WHERE id = $1", [gaId]);
          const ch = await resolveChannel(client, ga.channel_id);
          if (ch) {
            const e = baseEmbed(`🎁 ${ga.prize} — Giveaway Ended`, DANGER);
            e.setDescription('😔 No one entered this giveaway — there are no winners.');
            e.setFooter({ text: `${FOOTER_BRAND} | ID: ${gaId}` });
            await ch.send({ embeds: [e] }).catch(() => {});
          }
          continue;
        }

        const winnerIds = unique.sort(() => 0.5 - Math.random()).slice(0, ga.winners);
        await queryOne('UPDATE giveaways SET winner_ids = $1 WHERE id = $2', [JSON.stringify(winnerIds), gaId]);

        const ch = await resolveChannel(client, ga.channel_id, gaId);
        if (!ch) {
          console.warn(`[WARN] giveaway_end_loop: could not find channel for ${gaId}`);
          continue;
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
        }).catch(err => console.warn(`[WARN] giveaway_end_loop announce ${gaId}:`, err));
      }
    } catch (err) {
      console.error('[WARN] giveaway_end_loop error:', err);
    }

    setTimeout(tick, INTERVAL);
  }

  tick();
}

// ── Giveaway reminder loop ────────────────────────────────────────────────────
function startGiveawayReminderLoop(client) {
  const INTERVAL  = 300_000; // 5 minutes
  const reminded  = new Map(); // gaId -> Set of sent labels

  async function tick() {
    try {
      const giveaways = await queryAll(
        "SELECT * FROM giveaways WHERE (winner_ids IS NULL OR winner_ids = '' OR winner_ids = '[]') AND ended_at IS NOT NULL"
      );

      const now = Date.now();
      const REMINDERS = [
        { upper: 86400, lower: 82800, key: '24h', label: '24 hours' },
        { upper: 43200, lower: 39600, key: '12h', label: '12 hours' },
        { upper:  3600, lower:  2400, key:  '1h', label: '1 hour'   },
      ];

      for (const ga of giveaways) {
        const endsAt    = new Date(ga.ended_at).getTime();
        const remaining = Math.floor((endsAt - now) / 1000);
        if (remaining <= 0) continue;

        if (!reminded.has(ga.id)) reminded.set(ga.id, new Set());
        const sent = reminded.get(ga.id);

        const trigger = REMINDERS.find(r => r.upper >= remaining && remaining > r.lower && !sent.has(r.key));
        if (!trigger) continue;

        sent.add(trigger.key);

        // Find channel
        const ch = await resolveChannel(client, ga.channel_id, ga.id);
        if (!ch) continue;

        const reminderE = baseEmbed('⏰ Giveaway Reminder', GOLD);
        reminderE.setDescription(
          `🎁 **${ga.prize}** giveaway ends in **${trigger.label}**!\n<t:${Math.floor(endsAt / 1000)}:R>`
        );
        const ping = ga.ping && ga.ping.toLowerCase() !== 'none' ? ga.ping : null;
        await ch.send({
          content: ping || undefined,
          embeds: [reminderE],
          allowedMentions: { parse: ['everyone', 'roles'] },
        }).catch(() => {});
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

module.exports = { startGiveawayEndLoop, startGiveawayReminderLoop };
