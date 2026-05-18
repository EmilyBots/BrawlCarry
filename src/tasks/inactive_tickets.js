const { queryAll, queryOne } = require('../db/index');
const { getConfig } = require('../db/index');
const { baseEmbed } = require('../utils/embeds');
const { removeTicketActivity } = require('../utils/permissions');
const { GOLD, DANGER } = require('../config/constants');
const { ChannelType } = require('discord.js');

function startInactiveTicketLoop(client) {
  const INTERVAL = 1_800_000; // 30 minutes

  async function tick() {
    try {
      const tickets = await queryAll('SELECT * FROM ticket_activity');
      const now     = Date.now();

      for (const row of tickets) {
        const guild = client.guilds.cache.get(String(row.guild_id));
        if (!guild) continue;

        const cfg              = await getConfig(row.guild_id);
        const thresholdHours   = cfg?.inactive_ticket_hours ?? 24;
        const lastActivity     = new Date(row.last_activity).getTime();
        const hoursInactive    = (now - lastActivity) / 3_600_000;

        // Resolve channel
        let channel = guild.channels.cache.get(String(row.channel_id))
          ?? await guild.channels.fetch(String(row.channel_id)).catch(() => null);

        if (!channel) {
          try {
            const threads = await guild.channels.fetchActiveThreads();
            channel = threads.threads.get(String(row.channel_id)) ?? null;
          } catch (_) {}
        }

        if (!channel) {
          await removeTicketActivity(row.channel_id);
          continue;
        }

        const isThread = channel.type === ChannelType.PublicThread || channel.type === ChannelType.PrivateThread;

        if (hoursInactive >= thresholdHours && !row.warned) {
          // Only warn actual threads, not text channels
          if (!isThread) {
            await removeTicketActivity(row.channel_id);
            continue;
          }

          try {
            const warnE = baseEmbed('⚠️ Ticket Inactivity Warning', GOLD);
            warnE.setDescription(
              `This ticket has been inactive for **${Math.floor(hoursInactive)}** hours.\n\n` +
              'If there is no activity within **12 hours**, this ticket will be automatically closed.'
            );
            await channel.send({ embeds: [warnE] });
            await queryOne('UPDATE ticket_activity SET warned = 1 WHERE channel_id = $1', [row.channel_id]);
          } catch (err) {
            console.warn(`[WARN] Could not warn ticket ${row.channel_id}:`, err.message);
          }

        } else if (hoursInactive >= thresholdHours + 12 && row.warned) {
          // Only auto-close threads, never text channels
          if (!isThread) {
            console.warn(`[WARN] Inactivity system skipped non-thread channel ${channel.id} (${channel.name})`);
            await removeTicketActivity(row.channel_id);
            continue;
          }

          try {
            const closeE = baseEmbed('🔒 Ticket Auto-Closed', DANGER);
            closeE.setDescription('This ticket has been automatically closed due to inactivity.');
            await channel.send({ embeds: [closeE] });
            await removeTicketActivity(row.channel_id);
            await new Promise(r => setTimeout(r, 3000));
            if (channel.archived) await channel.setArchived(false).catch(() => {});
            await channel.delete().catch(() => {});
          } catch (err) {
            console.warn(`[WARN] Could not auto-close ticket ${row.channel_id}:`, err.message);
            await removeTicketActivity(row.channel_id);
          }
        }
      }
    } catch (err) {
      console.error('[WARN] inactive_ticket_loop error:', err);
    }

    setTimeout(tick, INTERVAL);
  }

  tick();
}

module.exports = { startInactiveTicketLoop };
