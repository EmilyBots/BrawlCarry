const APPLICATION_ID = process.env.DISCORD_APPLICATION_ID;
const BOT_TOKEN = process.env.DISCORD_TOKEN;

const metadata = [
  {
    key: "is_founder",
    name: "Founder",
    description: "Founder of BrawlCarry™",
    type: 7,
  }
];

fetch(
  `https://discord.com/api/v10/applications/${APPLICATION_ID}/role-connections/metadata`,
  {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bot ${BOT_TOKEN}`,
    },
    body: JSON.stringify(metadata),
  }
).then(r => r.json()).then(d => {
  console.log("✅ Metadata registrato:", d);
  process.exit(0);
});
