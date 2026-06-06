const orders       = require('./orders');
const tickets      = require('./tickets');
const vouches      = require('./vouches');
const giveaways    = require('./giveaways');
const applications = require('./applications');
const accounts     = require('./accounts');
const boosterRating = require('./booster_rating');

/**
 * Route an incoming interaction to the correct handler.
 * Handlers return true if they handled it, false/undefined otherwise.
 */
async function loadInteractions(interaction, client) {
  const id = interaction.customId ?? '';

  // ── Buttons ──────────────────────────────────────────────────────────────
  if (interaction.isButton()) {
    if (id.startsWith('booster_claim:') || id.startsWith('booster_unclaim:') || id.startsWith('order_publish_btn') || id.startsWith('send_boosters_')) return orders.handleButton(interaction, client);
    if (id.startsWith('svc_boost_') || id.startsWith('svc_carry_')) return orders.handleButton(interaction, client);
    if (id === 'ranked_order_btn')    return orders.handleRankedPanelBtn(interaction, client);
    if (id === 'prestige_order_btn')  return orders.handlePrestigePanelBtn(interaction, client);
    if (id === 'ticket_close_v2' || id === 'ticket_close_reason_v2' || id === 'ticket_general_btn') return tickets.handleButton(interaction, client);
    if (id.startsWith('vouch_btn:') || id === 'vouch_btn_v2') return vouches.handleButton(interaction, client);
    if (id === 'vouch_continue') return vouches.handleContinueBtn(interaction, client);
    if (
  id.startsWith('ga_enter:') ||
  id.startsWith('ga_view:')  ||
  id.startsWith('ga_roles:') ||
  id.startsWith('ga_pg:')
) return giveaways.handleButton(interaction, client);
    if (id === 'app_accept_v1' || id === 'app_reject_v1') return applications.handleButton(interaction, client);
    if (id.startsWith('account_buy:') || id.startsWith('account_sold:')) return accounts.handleButton(interaction, client);
    if (id === 'avail_available' || id === 'avail_busy' || id === 'avail_offline') return handleAvailability(interaction);
    if (id.startsWith('review_submit_ranked_v1') || id.startsWith('review_submit_prestige_v1') || id === 'simple_review_submit_v1') return vouches.handleReviewSubmit(interaction, client);
    if (id === 'ranked_confirm') return orders.handleConfirm(interaction, client);
    if (id === 'prestige_confirm') return orders.handleConfirmPrestige(interaction, client);
    if (id === 'ranked_edit' || id === 'prestige_edit') return orders.handleEditOrder(interaction, client);
    if (id === 'ranked_close' || id === 'prestige_close') return orders.handleCloseOrder(interaction, client);
    return;
  }

  // ── Select menus ──────────────────────────────────────────────────────────
  if (interaction.isStringSelectMenu()) {
    if (id.startsWith('ranked_') || id.startsWith('prest_')) return orders.handleSelect(interaction, client);
    if (id === 'support_center_select_v1' || id === 'application_center_select_v1') return tickets.handleSelect(interaction, client);
    if (id.startsWith('vouch_') || id === 'vouch_rating_select' || id === 'vouch_pay_select' || id === 'vouch_svc_select') return vouches.handleSelect(interaction, client);
    if (id.startsWith('booster_rate:')) return boosterRating.handleSelect(interaction, client);
    return;
  }

// ── Modals ────────────────────────────────────────────────────────────────
  if (interaction.isModalSubmit()) {
    if (id === 'ranked_order_modal')   return orders.handleRankedModal(interaction, client);
    if (id === 'prestige_order_modal') return orders.handlePrestigeModal(interaction, client);
    if (id === 'publish_boosters_modal') return orders.handlePublishModal(interaction, client);
    if (id === 'order_complete_modal') return orders.handleOrderCompleteModal(interaction, client);
    if (id === 'prestige_trophy_modal') return orders.handlePrestigeTrophyModal(interaction, client);
    if (id === 'close_reason_modal')   return tickets.handleCloseModal(interaction, client);
    if (id === 'ticket_panel_setup_modal') return tickets.handleSetupModal(interaction, client);
    if (id === 'vouch_detail_modal')   return vouches.handleModal(interaction, client);
    if (id.startsWith('app_modal_'))   return applications.handleModal(interaction, client);
    if (id === 'account_sale_modal')   return accounts.handleModal(interaction, client);
    return;
  }

  // ── Autocomplete ──────────────────────────────────────────────────────────
  if (interaction.isAutocomplete()) {
    const name = interaction.commandName;
    if (name === 'end-giveaway' || name === 'reroll-giveaway' || name === 'giveaway-reminder') {
      const cmds = require('../commands/admin/giveaway');
      const cmd  = cmds.find(c => c.data.name === name);
      if (cmd?.autocomplete) return cmd.autocomplete(interaction).catch(() => interaction.respond([]).catch(() => {}));
    }
    return;
  }
}

// ── Availability buttons (simple enough to live here) ─────────────────────────
const { setBoosterStatus } = require('../utils/permissions');
const { baseEmbed } = require('../utils/embeds');
const { SUCCESS, GOLD, DANGER } = require('../config/constants');

async function handleAvailability(interaction) {
  const status = interaction.customId.replace('avail_', '');
  await setBoosterStatus(interaction.user.id, interaction.guildId, status);

  const labels = { available: '🟢 Available', busy: '🟡 Busy', offline: '🔴 Offline' };
  const colors = { available: SUCCESS, busy: GOLD, offline: DANGER };
  const descs  = {
    available: 'Your status is now set to **🟢 Available**.\nYou can now claim new boost orders.',
    busy:      'Your status is now set to **🟡 Busy**.\nYou won\'t be able to claim new orders until you set yourself as Available.',
    offline:   'Your status is now set to **🔴 Offline**.\nYou won\'t be able to claim orders until you change your status.',
  };

  const e = baseEmbed(`${labels[status]} — Status Updated`, colors[status], descs[status]);
  await interaction.update({ embeds: [e], components: [] });
}

module.exports = { loadInteractions };
