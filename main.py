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
        id TEXT PRIMARY KEY, user_id INT, from_tier TEXT, to_tier TEXT, 
        price REAL, method TEXT, status TEXT DEFAULT 'pending', 
        image_url TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, completed_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS vouchers (
        id TEXT PRIMARY KEY, code TEXT UNIQUE, amount REAL, used_by INT,
        rating INT DEFAULT 5, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS giveaways (
        id TEXT PRIMARY KEY, prize TEXT, desc TEXT, winners INT, 
        participants TEXT, winner_ids TEXT, image_url TEXT, ended_at TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('brawl.db')
    conn.row_factory = sqlite3.Row
    return conn

# MODALS
class OrderModal(ui.Modal, title="Create Carry Order"):
    from_tier = ui.TextInput(label="From (Rank/Prestige/Tier/Level)", placeholder="e.g. Mythic I")
    to_tier = ui.TextInput(label="To (Rank/Prestige/Tier/Level)", placeholder="e.g. Masters I")
    price = ui.TextInput(label="Price (USD)", placeholder="44.99")
    method = ui.TextInput(label="Payment Method", placeholder="Bank Transfer")
    
    async def on_submit(self, interaction: discord.Interaction):
        conn = get_db()
        c = conn.cursor()
        order_id = f"CARRY-{uuid.uuid4().hex[:6].upper()}"
        c.execute('''INSERT INTO orders (id, user_id, from_tier, to_tier, price, method)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                 (order_id, interaction.user.id, self.from_tier.value, 
                  self.to_tier.value, float(self.price.value), self.method.value))
        conn.commit()
        
        embed = discord.Embed(color=SUCCESS, title="🎮 RANKED ORDER")
        embed.add_field(name="👤 Buyer", value=f"{interaction.user.mention}", inline=False)
        embed.add_field(name="💰 Order Amount (USD)", value=f"**${float(self.price.value):.2f}**", inline=False)
        embed.add_field(name="📊 Order Type", value="Ranked Boost", inline=False)
        embed.add_field(name="🏆 Order Details", value=f"🎯 {self.from_tier.value} → 🥇 {self.to_tier.value}", inline=False)
        embed.add_field(name="💳 Payment Method", value=self.method.value, inline=True)
        embed.add_field(name="⭐ Rating (5/5)", value="⭐⭐⭐⭐⭐", inline=True)
        embed.set_footer(text=f"Brawl Carry | {order_id}")
        embed.timestamp = datetime.utcnow()
        
        conn.close()
        await interaction.response.send_message(embed=embed, ephemeral=True)

class VouchModal(ui.Modal, title="Fill Vouch"):
    rating = ui.TextInput(label="Rating (1-5)", placeholder="5", min_length=1, max_length=1)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            stars = int(self.rating.value)
            if stars < 1 or stars > 5:
                stars = 5
        except:
            stars = 5
        
        embed = discord.Embed(color=PRIMARY, title="Vouch from its.mention")
        embed.add_field(name="🎁 New Customer Vouch!", value="\n**+vouch very fast**", inline=False)
        embed.add_field(name="💵 Vouch Amount", value="**$XX.XX**", inline=False)
        embed.add_field(name="Rating (5/5) 📋", value="⭐" * stars, inline=False)
        embed.set_footer(text="Brawl Carry")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# BUTTONS
class OrderButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @ui.button(label="Create Order", style=discord.ButtonStyle.primary, emoji="🎮", custom_id="order_btn")
    async def order(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(OrderModal())

class VouchButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @ui.button(label="Submit A Vouch", style=discord.ButtonStyle.primary, emoji="⭐", custom_id="vouch_btn")
    async def vouch(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(VouchModal())

class GiveawayView(ui.View):
    def __init__(self, giveaway_id):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
    
    @ui.button(label="Enter Giveaway", style=discord.ButtonStyle.success, emoji="🎁", custom_id="ga_enter")
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
                await interaction.response.send_message("✅ Entered!", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Already entered", ephemeral=True)
        conn.close()
    
    @ui.button(label="View Participants", style=discord.ButtonStyle.blurple, emoji="👥", custom_id="ga_view")
    async def view(self, interaction: discord.Interaction, button: ui.Button):
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT participants FROM giveaways WHERE id = ?', (self.giveaway_id,))
        ga = c.fetchone()
        conn.close()
        
        if ga:
            count = len(json.loads(ga['participants'])) if ga['participants'] else 0
            await interaction.response.send_message(f"👥 **{count}** participants", ephemeral=True)
    
    @ui.button(label="Extra Entries", style=discord.ButtonStyle.secondary, emoji="🎊", custom_id="ga_extra")
    async def extra(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("Check pinned for extra entry methods!", ephemeral=True)

class TicketSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Carry Order", value="carry", emoji="🎮"),
            discord.SelectOption(label="Account Issues", value="account", emoji="⚠️"),
            discord.SelectOption(label="Payment Issues", value="payment", emoji="💳"),
            discord.SelectOption(label="Other", value="other", emoji="❓"),
        ]
        super().__init__(placeholder="Choose ticket type...", options=options, custom_id="ticket_select")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"✅ Ticket type: {self.values[0]}", ephemeral=True)

class TicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

# SLASH COMMANDS
@bot.tree.command(name="order", description="Create carry order panel")
async def order_cmd(interaction: discord.Interaction):
    embed = discord.Embed(color=PRIMARY, title="🎮 Create Carry Order")
    embed.description = "Click button to fill order details"
    embed.set_footer(text="Brawl Carry")
    await interaction.response.send_message(embed=embed, view=OrderButton(), ephemeral=True)

@bot.tree.command(name="ticket", description="Open support ticket panel")
async def ticket_cmd(interaction: discord.Interaction):
    embed = discord.Embed(color=PRIMARY, title="Support Tickets")
    embed.description = "Select ticket type below"
    embed.set_footer(text="Brawl Carry")
    await interaction.response.send_message(embed=embed, view=TicketView())

@bot.tree.command(name="vouch_panel", description="Send vouch to user")
@app_commands.describe(user="User to send vouch", order_id="Order ID")
async def vouch_panel(interaction: discord.Interaction, user: discord.User, order_id: str):
    embed = discord.Embed(color=PRIMARY, title="Vouch from its.mention")
    embed.add_field(name="🎁 New Customer Vouch!", value=f"Order: **{order_id}**", inline=False)
    embed.add_field(name="Rating (5/5) 📋", value="⭐⭐⭐⭐⭐", inline=False)
    embed.set_footer(text="Brawl Carry")
    
    try:
        await user.send(embed=embed, view=VouchButton())
        await interaction.response.send_message(f"✅ Vouch sent to {user.mention}", ephemeral=True)
    except:
        await interaction.response.send_message("❌ Failed to DM user", ephemeral=True)

@bot.tree.command(name="giveaway", description="Create giveaway")
@app_commands.describe(prize="Prize name", hours="Duration hours", winners="Winner count", description="Giveaway rules")
async def giveaway(interaction: discord.Interaction, prize: str, hours: int, winners: int, description: str):
    conn = get_db()
    c = conn.cursor()
    ga_id = f"GA-{uuid.uuid4().hex[:8].upper()}"
    ends_at = datetime.utcnow() + timedelta(hours=hours)
    c.execute('INSERT INTO giveaways (id, prize, desc, winners, participants, ended_at) VALUES (?, ?, ?, ?, ?, ?)',
             (ga_id, prize, description, winners, '[]', ends_at))
    conn.commit()
    conn.close()
    
    embed = discord.Embed(color=PRIMARY, title="🎁 GIVEAWAY")
    embed.add_field(name="🎯 Prize", value=f"**{prize}**", inline=False)
    embed.add_field(name="📝 Description:", value=description, inline=False)
    embed.add_field(name="🏆 Winners", value=str(winners), inline=True)
    embed.add_field(name="👥 Participants", value="0", inline=True)
    
    time_left = ends_at - datetime.utcnow()
    hours_left = int(time_left.total_seconds() // 3600)
    embed.add_field(name="⏰ Ends", value=f"in {hours_left}h ({ends_at.strftime('%A, %d %B %Y %H:%M')})", inline=False)
    
    embed.set_footer(text=f"Brawl Carry | Giveaway: {ga_id}")
    await interaction.response.send_message(f"@everyone NEW GIVEAWAY!", embed=embed, view=GiveawayView(ga_id))

@bot.tree.command(name="end_giveaway", description="End giveaway and pick winners")
@app_commands.describe(giveaway_id="Giveaway ID")
async def end_giveaway(interaction: discord.Interaction, giveaway_id: str):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM giveaways WHERE id = ?', (giveaway_id,))
    ga = c.fetchone()
    
    if not ga:
        await interaction.response.send_message("❌ Giveaway not found", ephemeral=True)
        conn.close()
        return
    
    participants = json.loads(ga['participants']) if ga['participants'] else []
    if not participants:
        await interaction.response.send_message("❌ No participants", ephemeral=True)
        conn.close()
        return
    
    winners = random.sample(participants, min(ga['winners'], len(participants)))
    c.execute('UPDATE giveaways SET winner_ids = ? WHERE id = ?', (json.dumps(winners), giveaway_id))
    conn.commit()
    conn.close()
    
    winner_text = ", ".join([f"<@{w}>" for w in winners])
    embed = discord.Embed(color=SUCCESS, title="🎉 GIVEAWAY ENDED!")
    embed.description = f"Prize: **{ga['prize']}**\n\n🏆 Winners: {winner_text}"
    embed.set_footer(text="Brawl Carry")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="backup_link", description="Send backup server to all members")
@app_commands.describe(link="Backup server invite link")
async def backup_link(interaction: discord.Interaction, link: str):
    await interaction.response.defer(ephemeral=True)
    sent = 0
    failed = 0
    
    for member in interaction.guild.members:
        if not member.bot:
            try:
                embed = discord.Embed(color=DANGER, title="⚠️ BACKUP SERVER")
                embed.description = f"If main server unavailable:\n\n{link}"
                await member.send(embed=embed)
                sent += 1
            except:
                failed += 1
    
    result = discord.Embed(color=SUCCESS)
    result.add_field(name="✅ Sent", value=sent, inline=True)
    result.add_field(name="❌ Failed", value=failed, inline=True)
    await interaction.followup.send(embed=result, ephemeral=True)

@bot.tree.command(name="stats", description="View statistics")
@app_commands.describe(user="User (optional)")
async def stats(interaction: discord.Interaction, user: discord.User = None):
    target = user or interaction.user
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) as count, SUM(price) as total FROM orders WHERE user_id = ?', (target.id,))
    result = c.fetchone()
    conn.close()
    
    embed = discord.Embed(color=PRIMARY, title=f"📊 {target.name}")
    embed.add_field(name="🎮 Carries", value=result['count'] or 0, inline=True)
    embed.add_field(name="💰 Spent", value=f"${result['total']:.2f}" if result['total'] else "$0.00", inline=True)
    embed.set_thumbnail(url=target.avatar.url if target.avatar else "")
    embed.set_footer(text="Brawl Carry")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'✅ {bot.user} | Synced slash commands')

if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("❌ DISCORD_TOKEN not set")
        exit(1)
    bot.run(token)
