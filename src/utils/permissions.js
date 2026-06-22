const { queryAll, queryOne } = require('../db/index');
const { DEFAULT_PAYMENT_METHODS } = require('../config/constants');


function isStaff(member) {
  return member.permissions.has('Administrator') || member.permissions.has('ManageChannels');
}

// ── Payment methods ───────────────────────────────────────────────────────────

async function getPaymentMethods(guildId) {
  const rows = await queryAll(
    'SELECT label, emoji FROM payment_methods WHERE guild_id = $1 ORDER BY id',
    [guildId]
  );
  return rows.length ? rows : DEFAULT_PAYMENT_METHODS;
}

async function addPaymentMethod(guildId, label, emoji) {
  try {
    await queryOne(
      'INSERT INTO payment_methods (guild_id, label, emoji) VALUES ($1, $2, $3)',
      [guildId, label, emoji]
    );
    return true;
  } catch (_) {
    return false;
  }
}

async function removePaymentMethod(guildId, label) {
  const result = await queryOne(
    'DELETE FROM payment_methods WHERE guild_id = $1 AND label = $2 RETURNING id',
    [guildId, label]
  );
  return result !== null;
}

async function getPaymentEmoji(methodLabel, guildId) {
  if (!methodLabel) return '💳';
  const methods = await getPaymentMethods(guildId);
  const found = methods.find(m => m.label.toLowerCase() === methodLabel.toLowerCase());
  return found?.emoji ?? '💳';
}

// ── Ticket activity ───────────────────────────────────────────────────────────

async function updateTicketActivity(channelId, guildId) {
  await queryOne(
    `INSERT INTO ticket_activity (channel_id, guild_id, last_activity, warned)
     VALUES ($1, $2, NOW(), 0)
     ON CONFLICT (channel_id) DO UPDATE
     SET guild_id = EXCLUDED.guild_id, last_activity = EXCLUDED.last_activity, warned = 0`,
    [channelId, guildId]
  );
}

async function removeTicketActivity(channelId) {
  await queryOne('DELETE FROM ticket_activity WHERE channel_id = $1', [channelId]);
}

module.exports = {
  isStaff,
  getPaymentMethods, addPaymentMethod, removePaymentMethod, getPaymentEmoji,
  updateTicketActivity, removeTicketActivity,
};
