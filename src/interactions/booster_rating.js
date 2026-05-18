const { queryOne } = require('../db/index');
const { baseEmbed } = require('../utils/embeds');
const { SUCCESS, GOLD } = require('../config/constants');

async function handleSelect(interaction) {
  const id      = interaction.customId; // booster_rate:ORDER_ID
  const orderId = id.split(':')[1];
  const rating  = parseInt(interaction.values[0]);

  if (!orderId || isNaN(rating)) return;

  const order = await queryOne('SELECT * FROM orders WHERE id = $1', [orderId]);
  if (!order) return interaction.reply({ content: '❌ Order not found.', ephemeral: true });
  if (order.booster_rating !== null) return interaction.reply({ content: '❌ You have already rated this order.', ephemeral: true });
  if (String(order.user_id) !== interaction.user.id) return interaction.reply({ content: '❌ This rating is not for you.', ephemeral: true });

  await queryOne('UPDATE orders SET booster_rating = $1 WHERE id = $2', [rating, orderId]);

  const stars = '⭐'.repeat(rating) + '☆'.repeat(5 - rating);
  const e     = baseEmbed('⭐ Rating Submitted', SUCCESS);
  e.setDescription(`Thank you for rating your booster!\n\n**Your rating:** ${stars} (${rating}/5)\n\nYour feedback helps us maintain quality service.`);

  await interaction.update({ embeds: [e], components: [] });
}

module.exports = { handleSelect };
