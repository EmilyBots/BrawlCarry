const APPLICATION_ID = process.env.DISCORD_APPLICATION_ID;
const CLIENT_ID = process.env.DISCORD_CLIENT_ID;
const CLIENT_SECRET = process.env.DISCORD_CLIENT_SECRET;
const REDIRECT_URI = process.env.DISCORD_REDIRECT_URI;

export function registerFounderRoutes(app) {
  app.get('/auth/founder', (req, res) => {
    const url = `https://discord.com/oauth2/authorize?client_id=${CLIENT_ID}&redirect_uri=${encodeURIComponent(REDIRECT_URI)}&response_type=code&scope=role_connections.write%20identify`;
    res.redirect(url);
  });

  app.get('/callback/founder', async (req, res) => {
    const code = req.query.code;
    if (!code) return res.send('❌ Nessun codice');

    const tokenRes = await fetch('https://discord.com/api/v10/oauth2/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        client_id: CLIENT_ID,
        client_secret: CLIENT_SECRET,
        grant_type: 'authorization_code',
        code,
        redirect_uri: REDIRECT_URI,
      }),
    });
    const { access_token } = await tokenRes.json();

    await fetch(
      `https://discord.com/api/v10/users/@me/applications/${APPLICATION_ID}/role-connection`,
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${access_token}`,
        },
        body: JSON.stringify({
          platform_name: 'BrawlCarry',
          metadata: { is_founder: true },
        }),
      }
    );

    res.send('✅ Founder! check your discord profile.');
  });
}
