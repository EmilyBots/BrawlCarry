import discord
from discord.ext import commands
from discord.ext.commands import has_permissions
import json, os, sqlite3, uuid, random
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='+', intents=intents)

# Colors
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

def create_order_embed(order_id, user_id, from_rank, to_rank, price, method, rating=5):
    embed = discord.Embed(color=PRIMARY)
    embed.add_field(name="👤 Buyer", value=f"<@{user_id}>", inline=False)
    embed.add_field(name="💰 Amount", value=f"**${price:.2f}**", inline=False)
    embed.add_field(name="🏆 Boost", value=f"{from_rank.title()} → {to_rank.title()}", inline=False)
    embed.add_field(name="💳 Payment", value=method, inline=True)
    embed.add_field(name="⭐", value="⭐" * rating, inline=True)
    embed.set_footer(text=f"Brawl Carry | {order_id}")
    return embed

def create_voucher_embed(code, amount, rating=5):
    embed = discord.Embed(color=PRIMARY)
    embed.add_field(name="🎁 Voucher", value=f"**+vouch {code.lower()}**", inline=False)
    embed.add_field(name="💵 Amount", value=f"**${amount:.2f}**", inline=False)
    embed.add_field(name="⭐ Rating", value="⭐" * rating, inline=False)
    embed.set_footer(text="Brawl Carry")
    return embed

def create_giveaway_embed(prize, desc, winners, participants, ends_at, giveaway_id):
    embed = discord.Embed(color=PRIMARY)
    embed.add_field(name="🎯 Prize", value=f"**{prize}**", inline=False)
    embed.add_field(name="📝 Info", value=desc, inline=False)
    embed.add_field(name="🏆", value=str(winners), inline=True)
    embed.add_field(name="👥", value=str(participants), inline=True)
    time_left = ends_at - datetime.utcnow()
    hours = int(time_left.total_seconds() // 3600)
    embed.add_field(name="⏰", value=f"in {hours}h", inline=False)
    embed.set_footer(text=f"Brawl Carry | {giveaway_id}")
    return embed

@bot.event
async def on_ready():
    print(f'✅ {bot.user} online')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, name="Brawl Carry services"))

# SETUP
@bot.command(name='setup')
@has_permissions(administrator=True)
async def setup(ctx):
    try:
        await ctx.guild.create_role(name='Carrier', color=discord.Color.purple())
    except: pass
    try:
        await ctx.guild.create_text_channel('carries')
    except: pass
    try:
        await ctx.guild.create_text_channel('vouchers')
    except: pass
    try:
        await ctx.guild.create_text_channel('giveaways')
    except: pass
    embed = discord.Embed(color=SUCCESS, description="✅ Server setup complete")
    await ctx.send(embed=embed)

# ORDERS
@bot.command(name='carry')
async def create_order(ctx, from_rank: str, to_rank: str, price: float, *, method: str = "Bank Transfer"):
    conn = get_db()
    c = conn.cursor()
    order_id = f"CARRY-{uuid.uuid4().hex[:6].upper()}"
    c.execute('''INSERT INTO orders (id, user_id, from_rank, to_rank, price, method)
                VALUES (?, ?, ?, ?, ?, ?)''',
             (order_id, ctx.author.id, from_rank.lower(), to_rank.lower(), price, method))
    conn.commit()
    conn.close()
    embed = create_order_embed(order_id, ctx.author.id, from_rank, to_rank, price, method)
    await ctx.send(embed=embed)

@bot.command(name='mycarries')
async def my_carries(ctx):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 5', (ctx.author.id,))
    orders = c.fetchall()
    conn.close()
    if not orders:
        embed = discord.Embed(color=DANGER, description="No carries yet")
        await ctx.send(embed=embed)
        return
    embed = discord.Embed(color=PRIMARY, title=f"Your Carries ({len(orders)})")
    for order in orders:
        status = "✅" if order['status'] == 'completed' else "⏳"
        embed.add_field(name=f"{status} {order['id']}", 
                       value=f"{order['from_rank'].title()} → {order['to_rank'].title()} | ${order['price']:.2f}", 
                       inline=False)
    await ctx.send(embed=embed)

@bot.command(name='complete')
@has_permissions(administrator=True)
async def complete_carry(ctx, order_id: str):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE orders SET status = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?', 
             ('completed', order_id))
    conn.commit()
    conn.close()
    embed = discord.Embed(color=SUCCESS, description=f"✅ {order_id} completed")
    await ctx.send(embed=embed)

# VOUCHERS
@bot.command(name='makevoucher')
@has_permissions(administrator=True)
async def make_voucher(ctx, amount: float, rating: int = 5):
    conn = get_db()
    c = conn.cursor()
    code = f"BRWL-{uuid.uuid4().hex[:6].upper()}"
    voucher_id = f"VOUCH-{uuid.uuid4().hex[:6].upper()}"
    c.execute('INSERT INTO vouchers (id, code, amount, rating) VALUES (?, ?, ?, ?)',
             (voucher_id, code, amount, rating))
    conn.commit()
    conn.close()
    embed = create_voucher_embed(code, amount, rating)
    await ctx.send(embed=embed)

@bot.command(name='vouch')
async def use_voucher(ctx, code: str):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM vouchers WHERE code = ?', (code.upper(),))
    voucher = c.fetchone()
    if not voucher:
        embed = discord.Embed(color=DANGER, description="❌ Invalid voucher")
        await ctx.send(embed=embed)
        conn.close()
        return
    if voucher['used_by']:
        embed = discord.Embed(color=DANGER, description="❌ Already used")
        await ctx.send(embed=embed)
        conn.close()
        return
    c.execute('UPDATE vouchers SET used_by = ? WHERE id = ?', (ctx.author.id, voucher['id']))
    conn.commit()
    conn.close()
    embed = discord.Embed(color=SUCCESS, description=f"✅ ${voucher['amount']:.2f} credit claimed")
    await ctx.send(embed=embed)

# GIVEAWAYS
@bot.command(name='giveaway')
@has_permissions(administrator=True)
async def start_giveaway(ctx, prize: str, hours: int, winners: int, *, desc: str = ""):
    conn = get_db()
    c = conn.cursor()
    giveaway_id = f"GA-{uuid.uuid4().hex[:8].upper()}"
    ends_at = datetime.utcnow() + timedelta(hours=hours)
    c.execute('INSERT INTO giveaways (id, prize, desc, winners, participants, ended_at) VALUES (?, ?, ?, ?, ?, ?)',
             (giveaway_id, prize, desc or "Prize giveaway", winners, '[]', ends_at))
    conn.commit()
    conn.close()
    embed = create_giveaway_embed(prize, desc or "Prize giveaway", winners, 0, ends_at, giveaway_id)
    await ctx.send(f"@everyone GIVEAWAY!", embed=embed)

@bot.command(name='endgiveaway')
@has_permissions(administrator=True)
async def end_giveaway(ctx, giveaway_id: str):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM giveaways WHERE id = ?', (giveaway_id,))
    giveaway = c.fetchone()
    if not giveaway:
        embed = discord.Embed(color=DANGER, description="❌ Giveaway not found")
        await ctx.send(embed=embed)
        conn.close()
        return
    participants = json.loads(giveaway['participants']) if giveaway['participants'] else []
    if not participants:
        embed = discord.Embed(color=DANGER, description="❌ No participants")
        await ctx.send(embed=embed)
        conn.close()
        return
    winners_list = random.sample(participants, min(giveaway['winners'], len(participants)))
    c.execute('UPDATE giveaways SET winner_ids = ? WHERE id = ?', (json.dumps(winners_list), giveaway_id))
    conn.commit()
    conn.close()
    winner_mentions = ", ".join([f"<@{w}>" for w in winners_list])
    embed = discord.Embed(color=SUCCESS, title="🎉 GIVEAWAY ENDED",
                         description=f"Prize: {giveaway['prize']}\n🏆 {winner_mentions}")
    await ctx.send(embed=embed)

# STATS
@bot.command(name='stats')
async def stats(ctx, user: discord.User = None):
    target = user or ctx.author
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) as count, SUM(price) as total FROM orders WHERE user_id = ?', (target.id,))
    result = c.fetchone()
    conn.close()
    embed = discord.Embed(color=PRIMARY, title=f"Stats - {target.name}")
    embed.add_field(name="🎮 Carries", value=result['count'] or 0, inline=True)
    embed.add_field(name="💰 Total Spent", value=f"${result['total']:.2f}" if result['total'] else "$0.00", inline=True)
    embed.set_thumbnail(url=target.avatar.url if target.avatar else "")
    await ctx.send(embed=embed)

# HELP
@bot.command(name='help')
async def help_cmd(ctx):
    embed = discord.Embed(color=PRIMARY, title="Commands")
    embed.add_field(name="Orders", value="`+carry <from> <to> <price>` - Create\n`+mycarries` - View\n`+complete <id>` - Done (admin)", inline=False)
    embed.add_field(name="Vouchers", value="`+makevoucher <amount>` - Create (admin)\n`+vouch <code>` - Redeem", inline=False)
    embed.add_field(name="Giveaways", value="`+giveaway <prize> <hours> <winners> <desc>` - Start (admin)\n`+endgiveaway <id>` - End (admin)", inline=False)
    embed.add_field(name="Other", value="`+stats [@user]` - View\n`+setup` - Setup server (admin)", inline=False)
    embed.set_footer(text="Brawl Carry")
    await ctx.send(embed=embed)

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
