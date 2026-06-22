const orders       = require('./orders');
const tickets      = require('./tickets');
const vouches      = require('./vouches');
const giveaways    = require('./giveaways');
const accounts     = require('./accounts');


async function loadInteractions(interaction, client) {
  const id = interaction.customId ?? '';

  // ── Buttons ──────────────────────────────────────────────────────────────
  if (interaction.isButton()) {
    if (id.startsWith('booster_claim:') || id.startsWith('booster_unclaim:') || id.startsWith('order_publish_btn') || id.startsWith('send_boosters_')) return orders.handleButton(interaction, client);
    if (id.startsWith('svc_boost_') || id.startsWith('svc_carry_')) return orders.handleButton(interaction, client);
    if (id === 'ranked_order_btn')    return orders.handleRankedPanelBtn(interaction, client);
    if (id === 'prestige_order_btn')  return orders.handlePrestigePanelBtn(interaction, client);
    if (id === 'winstreak_order_btn') return orders.handleWinstreakPanelBtn(interaction, client);
    if (id === 'trophies_order_btn')    return orders.handleTrophiesPanelBtn(interaction, client);
    if (id === 'matcherino_order_btn')  return orders.handleMatcherinoPanelBtn(interaction, client);
    if (id === 'ticket_close_v2' || id === 'ticket_close_reason_v2' || id === 'ticket_general_btn') return tickets.handleButton(interaction, client);
    if (id.startsWith('vouch_btn:') || id === 'vouch_btn_v2') return vouches.handleButton(interaction, client);
    if (id === 'vouch_continue') return vouches.handleContinueBtn(interaction, client);
    if (
  id.startsWith('ga_enter:') ||
  id.startsWith('ga_view:')  ||
  id.startsWith('ga_roles:') ||
  id.startsWith('ga_pg:')
) return giveaways.handleButton(interaction, client);
    if (id.startsWith('account_buy:') || id.startsWith('account_sold:')) return accounts.handleButton(interaction, client);
    if (id.startsWith('review_submit_ranked_v1') || id.startsWith('review_submit_prestige_v1') || id === 'simple_review_submit_v1') return vouches.handleReviewSubmit(interaction, client);
    if (id === 'ranked_confirm')    return orders.handleConfirm(interaction, client);
    if (id === 'prestige_confirm')  return orders.handleConfirmPrestige(interaction, client);
    if (id === 'winstreak_confirm') return orders.handleConfirmWinstreak(interaction, client);
    if (id === 'trophies_confirm')    return orders.handleConfirmTrophies(interaction, client);
    if (id === 'matcherino_confirm')  return orders.handleConfirmMatcherino(interaction, client);
    if (id === 'ranked_edit' || id === 'prestige_edit' || id === 'winstreak_edit' || id === 'trophies_edit' || id === 'matcherino_edit') return orders.handleEditOrder(interaction, client);
    if (id === 'ranked_close' || id === 'prestige_close' || id === 'winstreak_close' || id === 'trophies_close' || id === 'matcherino_close') return orders.handleCloseOrder(interaction, client);
    return;
  }

  // ── Select menus ──────────────────────────────────────────────────────────
  if (interaction.isStringSelectMenu()) {
    if (id.startsWith('ranked_') || id.startsWith('prest_') || id.startsWith('winstreak_') || id.startsWith('trophies_') || id.startsWith('matcherino_')) return orders.handleSelect(interaction, client);
    if (id === 'support_center_select_v1' || id === 'application_center_select_v1') return tickets.handleSelect(interaction, client);
    if (id.startsWith('vouch_') || id === 'vouch_rating_select' || id === 'vouch_pay_select' || id === 'vouch_svc_select') return vouches.handleSelect(interaction, client);
    return;
  }

// ── Modals ────────────────────────────────────────────────────────────────
  if (interaction.isModalSubmit()) {
    if (id === 'ranked_order_modal')   return orders.handleRankedModal(interaction, client);
    if (id === 'prestige_order_modal') return orders.handlePrestigeModal(interaction, client);
    if (id === 'publish_boosters_modal') return orders.handlePublishModal(interaction, client);
    if (id === 'order_complete_modal') return orders.handleOrderCompleteModal(interaction, client);
    if (id === 'prestige_trophy_modal')   return orders.handlePrestigeTrophyModal(interaction, client);
    if (id === 'winstreak_brawler_modal') return orders.handleWinstreakBrawlerModal(interaction, client);
    if (id === 'trophies_input_modal')      return orders.handleTrophiesInputModal(interaction, client);
    if (id === 'matcherino_input_modal')    return orders.handleMatcherinoInputModal(interaction, client);
    if (id === 'close_reason_modal')   return tickets.handleCloseModal(interaction, client);
    if (id === 'ticket_panel_setup_modal') return tickets.handleSetupModal(interaction, client);
    if (id === 'vouch_detail_modal')   return vouches.handleModal(interaction, client);
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


module.exports = { loadInteractions };
