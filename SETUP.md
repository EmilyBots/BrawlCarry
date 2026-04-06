# BrawlMart Bot - Setup Guide

## Local Setup (5 min)

1. **Discord Developer Portal:** https://discord.com/developers/applications
   - Create new application
   - Bot section: copy your **Token**
   - General Info: copy your **Application ID** (for invite URL)

2. Create `.env` file:
   ```
   DISCORD_TOKEN=your_token_here
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Run the bot:
   ```
   python main.py
   ```

5. **Invite the bot:**
   - OAuth2 > URL Generator
   - Scopes: `bot`, `applications.commands`
   - Permissions: `Administrator`
   - Open the generated URL and authorize

---

## Railway Deployment (10 min)

1. Push project to GitHub
2. Go to https://railway.app
3. New Project > Deploy from GitHub repo
4. Add environment variable: `DISCORD_TOKEN = your_token`
5. Deploy

---

## First-Time Server Configuration

Run these commands in your Discord server after inviting the bot:

### 1. Configure channels
```
/setup vouch_channel:#vouches ticket_channel:#tickets
```

### 2. (Optional) Customise ticket panel text
```
/configure_ticket_panel
```

### 3. Post panels in the appropriate channels
```
/order_panel
/ticket_panel
```

---

## Slash Commands Reference

### Admin Commands
| Command | Description |
|---|---|
| `/setup` | Set vouch and ticket channels |
| `/configure_ticket_panel` | Customise ticket panel title and description |
| `/order_panel` | Post the carry order panel |
| `/ticket_panel` | Post the support ticket panel |
| `/vouch_panel` | Send vouch panel to a user or in channel |
| `/giveaway` | Start a new giveaway |
| `/end_giveaway` | End giveaway and draw winners |
| `/backup_link` | DM all members a backup server link |

### User Commands
| Command | Description |
|---|---|
| `/stats` | View your carry statistics |
| `/help` | View all commands |

---

## Vouch Flow

1. Staff runs `/vouch_panel user:@User order_id:CARRY-XXXXX` in the ticket channel
   OR clicks **Send Vouch Panel** button inside any ticket channel
2. User clicks **Submit A Vouch**
3. Modal opens: user fills in rating, order amount, feedback, and proof image URL
4. Vouch is posted automatically to the configured vouch channel with a watermark on the image

---

## Notes

- All vouch proof images are automatically watermarked with diagonal text
- Ticket channels are private (only opener + staff with Manage Channels can see)
- Tickets are deleted 5 seconds after the Close button is pressed
- Prefix commands have been removed. Everything is slash commands only.
