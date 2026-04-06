# 🎮 Brawl Carry Bot - Quick Setup

## Local (5 min)

1. **Discord Developer Portal:** https://discord.com/developers/applications
   - Create new app
   - Bot section → Copy **Token** (needed for .env)
   - General Info → Copy **Application ID** (needed to invite bot)

2. Create `.env`: `DISCORD_TOKEN=your_token`

3. `pip install -r requirements.txt`

4. `python main.py`

5. **Invite Bot:**
   - OAuth2 → URL Generator
   - Check `bot` scope + `Administrator` permission
   - Copy generated URL → Authorize in browser

6. Run `+setup` in Discord

## Deploy (Railway - 30 min)

1. Push to GitHub
2. Go to railway.app
3. Connect GitHub repo
4. Set `DISCORD_TOKEN` variable
5. Deploy!

## Commands

**Orders:**
- `+carry mythic masters 44.99` - Create
- `+mycarries` - View
- `+complete CARRY-ABC123` - Done (admin)

**Vouchers:**
- `+makevoucher 23.99` - Create (admin) [attach image as proof]
- `+vouch BRWL-ABC123` - Redeem

**Giveaways:**
- `+giveaway "Brawl Pass" 11 1 "Description"` - Start (admin)
- `+endgiveaway GA-ABC123` - End (admin)

**Other:**
- `+stats [@user]` - View
- `+help` - Commands
- `+setup` - Setup server (admin)
