import discord
from discord.ext import commands
from discord import app_commands, ui
import json, os, sqlite3, uuid, random
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.dm_messages = True
bot = commands.Bot(command_prefix='+', intents=intents, help_command=None)

PRIMARY = 0x00D9FF
DARK = 0x0A0E27
SUCCESS = 0x00FF88
DANGER = 0xFF006E

def init_db():
    conn = sqlite3.connect('brawl.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY, user_id INT, from_rank TEXT, to_rank TEXT, 
        price REAL, method TEXT, status TEXT DEFAULT 'pending', 
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, completed_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS vouchers (
        id TEXT PRIMARY KEY, code TEXT UNIQUE, amount REAL, used_by INT,
        rating INT DEFAULT 5, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS giveaways (
        id TEXT PRIMARY KEY, prize TEXT, desc TEXT, winners INT, 
        participants TEXT, winner_ids TEXT, ended_at TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('brawl.db')
    conn.row_factory = sqlite3.Row
    return conn

# MODALS
class OrderModal(ui.Modal, title="Create Carry Order"):
    from_rank = ui.TextInput(label="From Rank", placeholder="e.g. Mythic")
    to_rank = ui.TextInput(label="To Rank", placeholder="e.g. Masters")
    price = ui.TextInput(label="Price (USD)", placeholder="e.g. 44.99")
    method = ui.TextInput(label="Payment Method", placeholder="Bank Transfer, PayPal, etc")
    
    async def on_submit(self, interaction: discord.Interaction):
        conn = get_db()
        c = conn.cursor()
        order_id = f"CARRY-{uuid.uuid4().hex[:6].upper()}"
        c.execute('''INSERT INTO orders (id, user_id, from_rank, to_rank, price, method)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                 (order_id, interaction.user.id, self.from_rank.value.lower(), 
                  self.to_rank.value.lower(), float(self.price.value), self.method.value))
        conn.commit()
        conn.close()
        
        embed = discord.Embed(color=SUCCESS, title="✅ Order Created")
        embed.add_field(name="Order ID", value=order_id, inline=False)
        embed.add_field(name="Boost", value=f"{self.from_rank.value} → {self.to_rank.value}", inline=False)
        embed.add_field(name="Price", value=f"${self.price.value}", inline=True)
        embed.add_field(name="Payment", value=self.method.value, inline=True)
        embed.set_footer(text="Brawl Carry")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class VouchModal(ui.Modal, title="Fill Vouch"):
    stars = ui.TextInput(label="Rating (1-5)", placeholder="5")
    notes = ui.TextInput(label="Notes (optional)", placeholder="Fast service!", required=False)
    
    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(color=SUCCESS, title="✅ Vouch Submitted")
        embed.add_field(name="Rating", value="⭐" * int(self.stars.value), inline=False)
        if self.notes.value:
            embed.add_field(name="Notes", value=self.notes.value, inline=False)
        embed.set_footer(text="Brawl Carry")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# BUTTONS
class OrderButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @ui.button(label="Create Order", style=discord.ButtonStyle.primary, custom_id="order_button")
    async def order(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(OrderModal())

class VouchButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @ui.button(label="Submit Vouch", style=discord.ButtonStyle.primary, custom_id="vouch_button")
    async def vouch(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(VouchModal())

class GiveawayButton(ui.View):
    def __init__(self, giveaway_id):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
    
    @ui.button(label="Enter Giveaway", style=discord.ButtonStyle.success, custom_id="giveaway_button")
    async def enter(self, interaction: discord.Interaction, button: ui.Button):
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM giveaways WHERE id = ?', (self.giveaway_id,))
        giveaway = c.fetchone()
        
        if giveaway:
            participants = json.loads(giveaway['participants']) if giveaway['participants'] else []
            if interaction.user.id not in participants:
                participants.append(interaction.user.id)
                c.execute('UPDATE giveaways SET participants = ? WHERE id = ?',
                         (json.dumps(participants), self.giveaway_id))
                conn.commit()
                embed = discord.Embed(color=SUCCESS, description="✅ Entered giveaway!")
            else:
                embed = discord.Embed(color=DANGER, description="❌ Already entered")
        conn.close()
        await interaction.response.send_message(embed=embed, ephemeral=True)

# SLASH COMMANDS
@bot.tree.command(name="order_panel", description="Create order panel")
async def order_panel(interaction: discord.Interaction):
    embed = discord.Embed(color=PRIMARY, title="🎮 Create Carry Order")
    embed.description = "Click button below to create a new order"
    embed.set_footer(text="Brawl Carry")
    await interaction.response.send_message(embed=embed, view=OrderButton())

@bot.tree.command(name="vouch_panel", description="Send vouch panel to user")
@app_commands.describe(user="User to send vouch to", order_id="Order ID completed")
async def vouch_panel(interaction: discord.Interaction, user: discord.User, order_id: str):
    embed = discord.Embed(color=PRIMARY, title="✨ Submit Your Vouch")
    embed.description = f"Order: {order_id}\n\nClick button to submit vouch & proof"
    embed.set_footer(text="Brawl Carry")
    try:
        await user.send(embed=embed, view=VouchButton())
        await interaction.response.send_message(f"✅ Vouch panel sent to {user.mention}", ephemeral=True)
    except:
        await interaction.response.send_message("❌ Failed to DM user", ephemeral=True)

@bot.tree.command(name="giveaway", description="Start giveaway panel")
@app_commands.describe(prize="Prize name", hours="Duration in hours", winners="Number of winners")
async def giveaway(interaction: discord.Interaction, prize: str, hours: int, winners: int):
    conn = get_db()
    c = conn.cursor()
    giveaway_id = f"GA-{uuid.uuid4().hex[:8].upper()}"
    ends_at = datetime.utcnow() + timedelta(hours=hours)
    c.execute('INSERT INTO giveaways (id, prize, desc, winners, participants, ended_at) VALUES (?, ?, ?, ?, ?, ?)',
             (giveaway_id, prize, "Giveaway", winners, '[]', ends_at))
    conn.commit()
    conn.close()
    
    embed = discord.Embed(color=PRIMARY, title="🎁 GIVEAWAY")
    embed.add_field(name="Prize", value=prize, inline=False)
    embed.add_field(name="Winners", value=str(winners), inline=True)
    embed.add_field(name="Ends In", value=f"{hours}h", inline=True)
    embed.set_footer(text=f"Brawl Carry | {giveaway_id}")
    await interaction.response.send_message(embed=embed, view=GiveawayButton(giveaway_id))

@bot.tree.command(name="end_giveaway", description="End giveaway and select winners")
@app_commands.describe(giveaway_id="Giveaway ID")
async def end_giveaway(interaction: discord.Interaction, giveaway_id: str):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM giveaways WHERE id = ?', (giveaway_id,))
    giveaway = c.fetchone()
    
    if not giveaway:
        await interaction.response.send_message("❌ Giveaway not found", ephemeral=True)
        conn.close()
        return
    
    participants = json.loads(giveaway['participants']) if giveaway['participants'] else []
    if not participants:
        await interaction.response.send_message("❌ No participants", ephemeral=True)
        conn.close()
        return
    
    winners_list = random.sample(participants, min(giveaway['winners'], len(participants)))
    c.execute('UPDATE giveaways SET winner_ids = ? WHERE id = ?', (json.dumps(winners_list), giveaway_id))
    conn.commit()
    conn.close()
    
    winner_mentions = ", ".join([f"<@{w}>" for w in winners_list])
    embed = discord.Embed(color=SUCCESS, title="🎉 GIVEAWAY ENDED")
    embed.description = f"Prize: {giveaway['prize']}\n\n🏆 {winner_mentions}"
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="backup_link", description="Send backup server link to all members")
@app_commands.describe(link="Backup server invite link")
async def backup_link(interaction: discord.Interaction, link: str):
    await interaction.response.defer(ephemeral=True)
    sent = 0
    failed = 0
    
    for member in interaction.guild.members:
        if not member.bot:
            try:
                embed = discord.Embed(color=DANGER, title="⚠️ BACKUP SERVER")
                embed.description = f"If main server goes down, join here:\n\n{link}"
                await member.send(embed=embed)
                sent += 1
            except:
                failed += 1
    
    result = discord.Embed(color=SUCCESS, title="✅ DM Sent")
    result.add_field(name="Sent", value=sent, inline=True)
    result.add_field(name="Failed", value=failed, inline=True)
    await interaction.followup.send(embed=result, ephemeral=True)

@bot.tree.command(name="stats", description="View user statistics")
@app_commands.describe(user="User to check (optional)")
async def stats(interaction: discord.Interaction, user: discord.User = None):
    target = user or interaction.user
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) as count, SUM(price) as total FROM orders WHERE user_id = ?', (target.id,))
    result = c.fetchone()
    conn.close()
    
    embed = discord.Embed(color=PRIMARY, title=f"Stats - {target.name}")
    embed.add_field(name="🎮 Carries", value=result['count'] or 0, inline=True)
    embed.add_field(name="💰 Total Spent", value=f"${result['total']:.2f}" if result['total'] else "$0.00", inline=True)
    embed.set_thumbnail(url=target.avatar.url if target.avatar else "")
    embed.set_footer(text="Brawl Carry")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'✅ {bot.user} online | Slash commands synced')

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(color=DANGER, description="❌ No permission")
        await ctx.send(embed=embed)

if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("❌ DISCORD_TOKEN not set")
        exit(1)
    bot.run(token)
