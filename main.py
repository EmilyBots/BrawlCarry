import discord
from discord.ext import commands
from discord import app_commands, ui
import json, os, sqlite3, uuid, random, io, aiohttp, asyncio
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
PRIMARY      = 0x9B59B6
GOLD         = 0xF1C40F
SUCCESS      = 0x2ECC71
DANGER       = 0xE74C3C
DARK         = 0x0A0E1A
ACCENT       = 0xA855F7

FOOTER_BRAND = "Powered by Brawl Carry™"

intents = discord.Intents.default()
intents.message_content = True
intents.members         = True
intents.guilds          = True
intents.dm_messages     = True

bot = commands.Bot(command_prefix="\x00", intents=intents, help_command=None)

# ---------------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect("brawl.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        user_id INT,
        from_tier TEXT,
        to_tier TEXT,
        price REAL,
        method TEXT,
        status TEXT DEFAULT 'pending',
        image_url TEXT,
        ticket_channel_id INT,
        booster_id INT,
        booster_earnings REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS vouchers (
        id TEXT PRIMARY KEY,
        code TEXT UNIQUE,
        amount REAL,
        used_by INT,
        rating INT DEFAULT 5,
        feedback TEXT,
        image_url TEXT,
        method TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS giveaways (
        id TEXT PRIMARY KEY,
        prize TEXT,
        desc TEXT,
        winners INT,
        hosted_by INT,
        participants TEXT,
        winner_ids TEXT,
        image_url TEXT,
        extra_entries TEXT,
        ping TEXT,
        ended_at TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS guild_config (
        guild_id INT PRIMARY KEY,
        vouch_channel_id INT,
        ticket_channel_id INT,
        completed_channel_id INT,
        ticket_category_id INT,
        ticket_panel_title TEXT,
        ticket_panel_desc TEXT,
        ranked_panel_channel_id INT,
        prestige_panel_channel_id INT,
        ranked_ticket_channel_id INT,
        prestige_ticket_channel_id INT,
        owner_id INT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS payment_methods (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INT,
        label TEXT,
        emoji TEXT,
        UNIQUE(guild_id, label)
    )""")

    migrations = [
        ("giveaways",    "extra_entries TEXT"),
        ("giveaways",    "ping TEXT"),
        ("guild_config", "completed_channel_id INT"),
        ("guild_config", "ticket_category_id INT"),
        ("vouchers",     "method TEXT"),
        ("guild_config", "ranked_panel_channel_id INT"),
        ("guild_config", "prestige_panel_channel_id INT"),
        ("guild_config", "ranked_ticket_channel_id INT"),
        ("guild_config", "prestige_ticket_channel_id INT"),
        ("guild_config", "owner_id INT"),
        ("orders",       "ticket_channel_id INT"),
        ("orders",       "booster_id INT"),
        ("orders",       "booster_earnings REAL"),
    ]
    for table, col_def in migrations:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        except Exception:
            pass

    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect("brawl.db")
    conn.row_factory = sqlite3.Row
    return conn

def get_config(guild_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,))
    row = c.fetchone()
    conn.close()
    return row

ALLOWED_CONFIG_KEYS = {
    "vouch_channel_id", "ticket_channel_id",
    "completed_channel_id", "ticket_category_id",
    "ticket_panel_title", "ticket_panel_desc",
    "ranked_panel_channel_id", "prestige_panel_channel_id",
    "ranked_ticket_channel_id", "prestige_ticket_channel_id",
    "owner_id",
}

def set_config(guild_id: int, **kwargs):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,))
    for key, val in kwargs.items():
        if key not in ALLOWED_CONFIG_KEYS:
            continue
        c.execute(f"UPDATE guild_config SET {key} = ? WHERE guild_id = ?", (val, guild_id))
    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# PAYMENT METHOD HELPERS
# ---------------------------------------------------------------------------
PAYPAL_EMOJI = "<:Paypal:1490768356960243764>"
DEFAULT_PAYMENT_METHODS = [
    ("PayPal",        PAYPAL_EMOJI),
    ("Bank Transfer", "🏦"),
    ("Crypto",        "🪙"),
]

def get_payment_methods(guild_id: int) -> list:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT label, emoji FROM payment_methods WHERE guild_id = ? ORDER BY id", (guild_id,))
    rows = c.fetchall()
    conn.close()
    if rows:
        return [(r["label"], r["emoji"]) for r in rows]
    return DEFAULT_PAYMENT_METHODS

def add_payment_method(guild_id: int, label: str, emoji: str) -> bool:
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO payment_methods (guild_id, label, emoji) VALUES (?, ?, ?)",
            (guild_id, label, emoji)
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def remove_payment_method(guild_id: int, label: str) -> bool:
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM payment_methods WHERE guild_id = ? AND label = ?", (guild_id, label))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

# ---------------------------------------------------------------------------
# TICKET HELPER
# ---------------------------------------------------------------------------
async def create_ticket_thread(
    guild: discord.Guild,
    member: discord.Member,
    name: str,
    topic_embed: discord.Embed,
    view: "ui.View",
    cfg,
    override_channel_id: int = None,   # ranked_ticket_channel_id / prestige_ticket_channel_id
) -> discord.Thread | discord.TextChannel:
    # Use override channel if provided, else fall back to generic ticket_channel_id
    ticket_ch_id = override_channel_id or (cfg["ticket_channel_id"] if cfg else None)
    category_id  = cfg["ticket_category_id"] if cfg else None

    if ticket_ch_id:
        text_ch = guild.get_channel(ticket_ch_id)
        if isinstance(text_ch, discord.TextChannel):
            thread = await text_ch.create_thread(
                name=name,
                type=discord.ChannelType.private_thread,
                reason=f"Ticket opened by {member}",
            )
            await thread.add_user(member)
            await thread.send(content=member.mention, embed=topic_embed, view=view)
            return thread

    category = guild.get_channel(category_id) if category_id else None
    if not isinstance(category, discord.CategoryChannel):
        category = None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member:             discord.PermissionOverwrite(
                                view_channel=True,
                                send_messages=True,
                                read_message_history=True,
                            ),
    }
    for role in guild.roles:
        if role.permissions.administrator or role.permissions.manage_channels:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    ch = await guild.create_text_channel(
        name=name,
        overwrites=overwrites,
        category=category,
        topic=f"Opened by {member} | {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
    )
    await ch.send(content=member.mention, embed=topic_embed, view=view)
    return ch

# ---------------------------------------------------------------------------
# WATERMARK UTILITY
# ---------------------------------------------------------------------------
def watermark_image(image_bytes: bytes, text: str = "Brawl Carry Vouches", blur: bool = False) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=6))
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(16, w // 18))
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    step_x = tw + 60
    step_y = th + 40
    for y in range(-h, h * 2, step_y):
        for x in range(-w, w * 2, step_x):
            draw.text((x, y), text, font=font, fill=(255, 255, 255, 55))
    watermarked = Image.alpha_composite(img, overlay).convert("RGB")
    buf = io.BytesIO()
    watermarked.save(buf, format="JPEG", quality=92)
    return buf.getvalue()

async def fetch_and_watermark(url: str, blur: bool = False):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                raw = await resp.read()
        loop = asyncio.get_event_loop()
        marked = await loop.run_in_executor(None, watermark_image, raw, "Brawl Carry Vouches", blur)
        return discord.File(io.BytesIO(marked), filename="proof.jpg")
    except Exception:
        return None

# ---------------------------------------------------------------------------
# EMBED HELPER
# ---------------------------------------------------------------------------
def base_embed(title: str = None, color: int = PRIMARY, description: str = None) -> discord.Embed:
    e = discord.Embed(title=title, color=color, description=description)
    e.set_footer(text=FOOTER_BRAND)
    e.timestamp = datetime.utcnow()
    return e

# ---------------------------------------------------------------------------
# RANKED BOOST OPTIONS
# ---------------------------------------------------------------------------
CURRENT_RANKS = [
    "Bronze I", "Bronze II", "Bronze III",
    "Silver I", "Silver II", "Silver III",
    "Gold I", "Gold II", "Gold III",
    "Diamond I", "Diamond II", "Diamond III",
    "Mythic I", "Mythic II", "Mythic III",
    "Legendary I", "Legendary II", "Legendary III",
    "Masters I", "Masters II", "Masters III",
]

DESIRED_RANKS = [
    "Diamond I", "Diamond II", "Diamond III",
    "Mythic I", "Mythic II", "Mythic III",
    "Legendary I", "Legendary II", "Legendary III",
    "Masters I", "Masters II", "Masters III",
    "Pro",
]

RANK_EMOJI = {
    "Bronze":    "<:Bronze:1490768371619336493>",
    "Silver":    "<:Silver:1490768369551409312>",
    "Gold":      "<:Gold:1490768358898139146>",
    "Diamond":   "<:Diamond:1490768360475201760>",
    "Mythic":    "<:Mythic:1490768362266034286>",
    "Legendary": "<:Legendary:1490768363981508758>",
    "Masters":   "<:Masters:1490768366464663794>",
    "Pro":       "<:Pro:1490768368024682506>",
}

# ---------------------------------------------------------------------------
# PRESTIGE OPTIONS & EMOJIS
# Replace the emoji IDs below with the ones from your Discord Developer Portal
# ---------------------------------------------------------------------------
PRESTIGE_OPTIONS = [
    "Prestige 0 -> Prestige 1",
    "Prestige 1 -> Prestige 2",
    "Prestige 2 -> Prestige 3",
]

PRESTIGE_EMOJI = {
    "Prestige 0 -> Prestige 1": "<:Prestige1:1491103698116677693>",
    "Prestige 1 -> Prestige 2": "<:Prestige2:1491103696153477161>",
    "Prestige 2 -> Prestige 3": "<:Prestige3:1491103694433816688>",
}

def prestige_emoji(spec: str) -> str:
    return PRESTIGE_EMOJI.get(spec, "✨")

def rank_emoji(rank_name: str) -> str:
    for prefix, emoji in RANK_EMOJI.items():
        if rank_name.startswith(prefix):
            return emoji
    return ""

P11_OPTIONS      = ["0-10", "11-20", "21-30", "31-40", "41-50", "51-60", "61-70", "71+"]
P11_EMOJI        = "<:P11:1491455088429109258>"

RATING_OPTIONS = [
    discord.SelectOption(label="5 Stars", value="5", emoji="⭐", description="Excellent service"),
    discord.SelectOption(label="4 Stars", value="4", emoji="⭐", description="Great service"),
    discord.SelectOption(label="3 Stars", value="3", emoji="⭐", description="Good service"),
    discord.SelectOption(label="2 Stars", value="2", emoji="⭐", description="Average service"),
    discord.SelectOption(label="1 Star",  value="1", emoji="⭐", description="Below expectations"),
]

# ---------------------------------------------------------------------------
# DIRECT BOOSTER CLAIM VIEW  (posted in the panel/booster channel after owner publishes)
# ---------------------------------------------------------------------------
class BoosterClaimView(ui.View):
    """
    Posted in the booster/panel channel after the owner publishes an order.
    Clicking Claim immediately adds the booster to the customer's ticket.
    """
    def __init__(self, order_id: str, ticket_channel_id: int | None = None):
        super().__init__(timeout=None)
        self.order_id          = order_id
        self.ticket_channel_id = ticket_channel_id

    @ui.button(label="🟠 Claim This Boost", style=discord.ButtonStyle.primary, custom_id="booster_claim_direct_v1")
    async def claim(self, interaction: discord.Interaction, button: ui.Button):
        guild   = interaction.guild
        booster = interaction.user

        conn = get_db()
        c    = conn.cursor()
        c.execute("SELECT * FROM orders WHERE id = ?", (self.order_id,))
        order = c.fetchone()
        conn.close()

        if not order:
            await interaction.response.send_message("❌ Order not found.", ephemeral=True)
            return
        if order["status"] == "claimed":
            await interaction.response.send_message(
                "❌ This order has already been claimed by another booster.", ephemeral=True
            )
            return

        # Mark order as claimed
        conn = get_db()
        c    = conn.cursor()
        c.execute(
            "UPDATE orders SET booster_id = ?, status = 'claimed' WHERE id = ?",
            (booster.id, self.order_id)
        )
        conn.commit()
        conn.close()

        # Disable the button on the original message
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        # Resolve ticket channel (stored on the view or fallback to order row)
        ticket_ch_id = self.ticket_channel_id or order["ticket_channel_id"]

        if ticket_ch_id and guild:
            ticket_ch = guild.get_channel(ticket_ch_id)
            if ticket_ch:
                try:
                    if isinstance(ticket_ch, discord.Thread):
                        await ticket_ch.add_user(booster)
                    elif isinstance(ticket_ch, discord.TextChannel):
                        await ticket_ch.set_permissions(
                            booster,
                            view_channel=True,
                            send_messages=True,
                            read_message_history=True,
                        )
                    notify_e = base_embed("🟠 Booster Assigned", color=SUCCESS)
                    notify_e.description = (
                        f"{booster.mention} has claimed order `{self.order_id}` and has been added to this ticket.\n"
                        "Please coordinate here to complete the boost! 🏆"
                    )
                    await ticket_ch.send(embed=notify_e)
                except Exception as ex:
                    print(f"[WARN] Could not add booster to ticket: {ex}")

        # DM the booster
        try:
            dm_e = base_embed("✅ Boost Claimed!", color=SUCCESS)
            dm_e.description = (
                f"You've successfully claimed order **`{self.order_id}`**!\n\n"
                "You have been added to the customer's ticket. Good luck! 🏆"
            )
            await booster.send(embed=dm_e)
        except discord.Forbidden:
            pass

        await interaction.response.send_message(
            f"✅ You've claimed order `{self.order_id}`! Check the customer's ticket.",
            ephemeral=True
        )


# ---------------------------------------------------------------------------
# PUBLISH TO BOOSTERS MODAL  (owner fills in booster earnings before posting)
# ---------------------------------------------------------------------------
class PublishToBoostersModal(ui.Modal, title="Publish Order to Boosters"):
    booster_earnings = ui.TextInput(
        label="Booster Earnings (USD)",
        placeholder="e.g. 12.00",
        style=discord.TextStyle.short
    )
    extra_notes = ui.TextInput(
        label="Extra Notes for Boosters (Optional)",
        placeholder="Any special info boosters should know...",
        required=False,
        style=discord.TextStyle.long,
        max_length=300
    )

    def __init__(self, order_id: str, ticket_channel_id: int | None, panel_channel_id: int | None, order_type: str):
        super().__init__()
        self.order_id         = order_id
        self.ticket_channel_id = ticket_channel_id
        self.panel_channel_id  = panel_channel_id
        self.order_type        = order_type  # "ranked" or "prestige"

    async def on_submit(self, interaction: discord.Interaction):
        try:
            earnings = float(self.booster_earnings.value.replace("$", "").strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid earnings amount. Please enter a number like `12.00`.", ephemeral=True
            )
            return

        conn = get_db()
        c    = conn.cursor()
        c.execute("SELECT * FROM orders WHERE id = ?", (self.order_id,))
        order = c.fetchone()
        if not order:
            conn.close()
            await interaction.response.send_message("❌ Order not found.", ephemeral=True)
            return

        # Save booster earnings
        c.execute("UPDATE orders SET booster_earnings = ? WHERE id = ?", (earnings, self.order_id))
        conn.commit()
        conn.close()

        # Resolve the claiming (panel) channel
        guild         = interaction.guild
        panel_ch_id   = self.panel_channel_id
        if not panel_ch_id:
            cfg = get_config(guild.id)
            if cfg:
                panel_ch_id = (
                    cfg["ranked_panel_channel_id"] if self.order_type == "ranked"
                    else cfg["prestige_panel_channel_id"]
                )

        panel_ch = guild.get_channel(panel_ch_id) if panel_ch_id else None
        if not panel_ch:
            await interaction.response.send_message(
                "❌ Panel channel not found. Make sure it is configured via `/setup`.", ephemeral=True
            )
            return

        color = PRIMARY if self.order_type == "ranked" else ACCENT
        title = "🔥 Ranked Boost Available" if self.order_type == "ranked" else "✨ Prestige Boost Available"

        claim_e = base_embed(title, color=color)
        claim_e.set_author(
            name="BrawlCarry | Boost Available",
            icon_url=guild.icon.url if guild.icon else discord.Embed.Empty
        )
        claim_e.add_field(name="📦 Route",      value=f"`{order['from_tier']}` → `{order['to_tier']}`", inline=True)
        claim_e.add_field(name="💰 You Earn",   value=f"**${earnings:.2f}**", inline=True)
        claim_e.add_field(name="💳 Payment",    value=order["method"] or "—", inline=True)
        claim_e.add_field(name="🆔 Order ID",   value=f"`{self.order_id}`", inline=True)
        claim_e.add_field(name="🕐 Posted",     value=f"<t:{int(datetime.utcnow().timestamp())}:R>", inline=True)

        if self.order_type == "ranked":
            # Pull P11 from the order notes if stored (stored in to_tier field for ranked view)
            pass  # P11 is already part of from_tier/to_tier display

        if self.extra_notes.value:
            claim_e.add_field(name="📝 Notes", value=self.extra_notes.value, inline=False)

        claim_e.set_footer(text=f"{FOOTER_BRAND} | Click the button below to claim this order")

        await panel_ch.send(
            embed=claim_e,
            view=BoosterClaimView(self.order_id, ticket_channel_id=self.ticket_channel_id)
        )

        await interaction.response.send_message(
            f"✅ Order `{self.order_id}` published to {panel_ch.mention} with **${earnings:.2f}** booster earnings.",
            ephemeral=True
        )


# ---------------------------------------------------------------------------
# ORDER ACTIONS VIEW  (posted on the order card in the ticket/order channel)
# Staff-only: owner/admin clicks "Publish to Boosters" to release the order
# ---------------------------------------------------------------------------
class OrderActionsView(ui.View):
    """
    Shown on the order card inside the customer's ticket channel.
    Staff click 'Publish to Boosters' to release it with a set earnings amount.
    """
    def __init__(self, order_id: str, ticket_channel_id: int | None = None, order_type: str = "ranked"):
        super().__init__(timeout=None)
        self.order_id          = order_id
        self.ticket_channel_id = ticket_channel_id
        self.order_type        = order_type

    @ui.button(label="📢 Publish to Boosters", style=discord.ButtonStyle.success, custom_id="order_publish_btn_v1")
    async def publish(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "❌ Only staff can publish orders to boosters.", ephemeral=True
            )
            return

        cfg = get_config(interaction.guild.id)
        panel_ch_id = None
        if cfg:
            panel_ch_id = (
                cfg["ranked_panel_channel_id"] if self.order_type == "ranked"
                else cfg["prestige_panel_channel_id"]
            )

        await interaction.response.send_modal(
            PublishToBoostersModal(
                order_id=self.order_id,
                ticket_channel_id=self.ticket_channel_id,
                panel_channel_id=panel_ch_id,
                order_type=self.order_type,
            )
        )


# ---------------------------------------------------------------------------
# MODALS
# ---------------------------------------------------------------------------
class OrderModal(ui.Modal, title="Create Carry Order"):
    from_tier = ui.TextInput(label="From (Current Rank / Prestige / Tier)", placeholder="e.g. Diamond III", style=discord.TextStyle.short)
    to_tier   = ui.TextInput(label="To (Target Rank / Prestige / Tier)",   placeholder="e.g. Masters I",   style=discord.TextStyle.short)
    price     = ui.TextInput(label="Agreed Price (USD)",                    placeholder="44.99",             style=discord.TextStyle.short)
    method    = ui.TextInput(label="Payment Method",                        placeholder="PayPal / Bank Transfer / Crypto ...", style=discord.TextStyle.short)
    image_url = ui.TextInput(label="Proof Image URL (optional)", placeholder="https://i.imgur.com/...", required=False, style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price_val = float(self.price.value.replace("$", "").strip())
        except ValueError:
            await interaction.response.send_message("❌ Invalid price. Please enter a number like `44.99`.", ephemeral=True)
            return

        conn     = get_db()
        c        = conn.cursor()
        order_id = f"CARRY-{uuid.uuid4().hex[:6].upper()}"
        img      = self.image_url.value.strip() if self.image_url.value else None
        c.execute(
            "INSERT INTO orders (id, user_id, from_tier, to_tier, price, method, image_url) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (order_id, interaction.user.id, self.from_tier.value, self.to_tier.value, price_val, self.method.value, img)
        )
        conn.commit()
        conn.close()

        e = base_embed("🚀 New Carry Order", color=PRIMARY)
        e.set_author(name="BrawlCarry | Brawl Stars Boost", icon_url=interaction.user.display_avatar.url)
        e.add_field(name="👤 Customer", value=interaction.user.mention, inline=True)
        e.add_field(name="💵 Amount",   value=f"**${price_val:.2f}**",  inline=True)
        e.add_field(name="🎮 Type",     value="Ranked Boost",           inline=True)
        e.add_field(name="📦 Route",    value=f"`{self.from_tier.value}` → `{self.to_tier.value}`", inline=False)
        e.add_field(name="💳 Payment",  value=self.method.value,        inline=True)
        e.add_field(name="🆔 Order ID", value=f"`{order_id}`",          inline=True)

        wm_file = None
        if img:
            wm_file = await fetch_and_watermark(img)
            if wm_file:
                e.set_image(url="attachment://proof.jpg")

        view = OrderActionsView(order_id, order_type="ranked")
        if wm_file:
            await interaction.channel.send(embed=e, view=view, file=wm_file)
        else:
            await interaction.channel.send(embed=e, view=view)
        await interaction.response.send_message("✅ Order submitted!", ephemeral=True)


# ---------------------------------------------------------------------------
# VOUCH DETAIL MODAL
# ---------------------------------------------------------------------------
class VouchDetailModal(ui.Modal, title="Submit Your Vouch"):
    amount   = ui.TextInput(label="Order Amount (USD)", placeholder="44.99", style=discord.TextStyle.short)
    feedback = ui.TextInput(label="Your Feedback", placeholder="Fast service, very professional...", style=discord.TextStyle.long, max_length=500)
    image_url = ui.TextInput(label="Proof Image URL (optional)", placeholder="https://i.imgur.com/...", required=False, style=discord.TextStyle.short)

    def __init__(self, rating: int, payment_method: str, order_id: str = None):
        super().__init__()
        self.rating         = rating
        self.payment_method = payment_method
        self.order_id       = order_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount_val = float(self.amount.value.replace("$", "").strip())
        except ValueError:
            amount_val = 0.0

        stars    = self.rating
        star_str = "⭐" * stars + f"  ({stars}/5)"
        img      = self.image_url.value.strip() if self.image_url.value else None

        vouch_id = f"VOUCH-{uuid.uuid4().hex[:6].upper()}"
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO vouchers (id, code, amount, used_by, rating, feedback, image_url, method) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (vouch_id, vouch_id, amount_val, interaction.user.id, stars, self.feedback.value, img, self.payment_method)
        )
        conn.commit()
        guild_id    = interaction.guild.id if interaction.guild else None
        vouch_ch_id = None
        if guild_id:
            cfg = get_config(guild_id)
            if cfg:
                vouch_ch_id = cfg["vouch_channel_id"]
        conn.close()

        e = base_embed("⭐ New Vouch", color=GOLD)
        e.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        e.add_field(name="👤 Customer",     value=interaction.user.mention,     inline=True)
        e.add_field(name="💰 Order Amount", value=f"**${amount_val:.2f}**",     inline=True)
        e.add_field(name="💳 Payment",      value=f"**{self.payment_method}**", inline=True)
        e.add_field(name="⭐ Rating",       value=star_str,                     inline=True)
        e.add_field(name="💬 Feedback",     value=f"*{self.feedback.value}*",   inline=False)
        if self.order_id:
            e.set_footer(text=f"{FOOTER_BRAND} | Order: {self.order_id}")

        wm_file = None
        if img:
            wm_file = await fetch_and_watermark(img, blur=True)
            if wm_file:
                e.set_image(url="attachment://proof.jpg")

        await interaction.response.send_message("✅ Your vouch has been submitted. Thank you!", ephemeral=True)

        if vouch_ch_id and interaction.guild:
            ch = interaction.guild.get_channel(vouch_ch_id)
            if ch:
                if wm_file:
                    await ch.send(embed=e, file=wm_file)
                else:
                    await ch.send(embed=e)


# ---------------------------------------------------------------------------
# VOUCH SELECTOR VIEW
# ---------------------------------------------------------------------------
class VouchSelectorView(ui.View):
    def __init__(self, guild_id: int, order_id: str = None):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.order_id = order_id
        self.rating   = None
        self.payment  = None

        rating_select = ui.Select(placeholder="Select your rating...", options=RATING_OPTIONS, custom_id="vouch_rating", row=0)
        rating_select.callback = self._on_rating
        self.add_item(rating_select)

        methods   = get_payment_methods(guild_id)
        pay_select = ui.Select(
            placeholder="Select payment method used...",
            options=[discord.SelectOption(label=lbl, value=lbl, emoji=emo) for lbl, emo in methods],
            custom_id="vouch_pay", row=1
        )
        pay_select.callback = self._on_pay
        self.add_item(pay_select)

        submit_btn = ui.Button(label="Continue", style=discord.ButtonStyle.success, custom_id="vouch_continue", row=2, emoji="✅")
        submit_btn.callback = self._on_submit
        self.add_item(submit_btn)

    async def _on_rating(self, interaction: discord.Interaction):
        self.rating = int(interaction.data["values"][0])
        await interaction.response.defer()

    async def _on_pay(self, interaction: discord.Interaction):
        self.payment = interaction.data["values"][0]
        await interaction.response.defer()

    async def _on_submit(self, interaction: discord.Interaction):
        missing = []
        if not self.rating:  missing.append("Rating")
        if not self.payment: missing.append("Payment Method")
        if missing:
            await interaction.response.send_message(f"❌ Please select: **{', '.join(missing)}**", ephemeral=True)
            return
        await interaction.response.send_modal(VouchDetailModal(self.rating, self.payment, self.order_id))


class TicketPanelSetupModal(ui.Modal, title="Configure Ticket Panel"):
    panel_title = ui.TextInput(label="Panel Title", placeholder="🎫 Support Center", default="🎫 Support Center", style=discord.TextStyle.short)
    panel_desc  = ui.TextInput(
        label="Panel Description",
        placeholder="Select a category below to open a ticket.",
        default="Select the category that best matches your request.\nOur team will be with you shortly.\n\n📌 Tickets are private and handled by staff only.",
        style=discord.TextStyle.long
    )

    async def on_submit(self, interaction: discord.Interaction):
        set_config(interaction.guild.id, ticket_panel_title=self.panel_title.value, ticket_panel_desc=self.panel_desc.value)
        await interaction.response.send_message("✅ Ticket panel configuration saved.", ephemeral=True)


# ---------------------------------------------------------------------------
# RANKED BOOST MODAL
# ---------------------------------------------------------------------------
class RankedOrderModal(ui.Modal, title="Ranked Boost Order"):
    notes = ui.TextInput(label="Additional Notes (Optional)", placeholder="Any special requests or information...", required=False, style=discord.TextStyle.long, max_length=500)

    def __init__(self, current_rank: str, desired_rank: str, p11: str, payment: str):
        super().__init__()
        self.current_rank = current_rank
        self.desired_rank = desired_rank
        self.p11          = p11
        self.payment      = payment

    async def on_submit(self, interaction: discord.Interaction):
        conn     = get_db()
        c        = conn.cursor()
        order_id = f"RANKED-{uuid.uuid4().hex[:6].upper()}"
        c.execute(
            "INSERT INTO orders (id, user_id, from_tier, to_tier, price, method) VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, interaction.user.id, self.current_rank, self.desired_rank, 0.0, self.payment)
        )
        conn.commit()
        conn.close()

        guild  = interaction.guild
        member = interaction.user
        cfg    = get_config(guild.id)

        # Use ranked-specific ticket channel if configured
        ranked_ticket_ch_id = cfg["ranked_ticket_channel_id"] if cfg else None

        welcome = base_embed("🔥 Ranked Boost Ticket", color=PRIMARY)
        welcome.description = (
            f"Welcome, {member.mention}! 🎮\n\n"
            f"📋 **Order:** `{order_id}`\n"
            f"📦 **Route:** `{self.current_rank}` → `{self.desired_rank}`\n"
            f"⚡ **P11 Brawlers:** {P11_EMOJI} {self.p11}\n"
            f"💳 **Payment:** {self.payment}\n"
            f"🕐 **Opened:** <t:{int(datetime.utcnow().timestamp())}:F>\n\n"
            "Our staff will contact you shortly to complete your order. "
            "Please have your payment ready!"
        )
        welcome.set_author(name=member.display_name, icon_url=member.display_avatar.url)

        ticket = await create_ticket_thread(
            guild=guild,
            member=member,
            name=f"ranked-{member.name[:12].lower()}",
            topic_embed=welcome,
            view=TicketCloseView(),
            cfg=cfg,
            override_channel_id=ranked_ticket_ch_id,
        )

        # Store ticket channel id in the order
        conn = get_db()
        c    = conn.cursor()
        c.execute("UPDATE orders SET ticket_channel_id = ? WHERE id = ?", (ticket.id, order_id))
        conn.commit()
        conn.close()

        # Post the order card inside the ticket so staff can publish it
        order_e = base_embed("🔥 New Ranked Boost Order", color=PRIMARY)
        order_e.set_author(name="BrawlCarry | Staff View", icon_url=guild.icon.url if guild.icon else discord.Embed.Empty)
        order_e.add_field(name="👤 Customer",  value=member.mention, inline=True)
        order_e.add_field(name="📦 Route",     value=f"`{self.current_rank}` → `{self.desired_rank}`", inline=True)
        order_e.add_field(name="⚡ P11",       value=f"{P11_EMOJI} {self.p11}", inline=True)
        order_e.add_field(name="💳 Payment",   value=self.payment, inline=True)
        order_e.add_field(name="🆔 Order ID",  value=f"`{order_id}`", inline=True)
        order_e.add_field(name="🕐 Placed",    value=f"<t:{int(datetime.utcnow().timestamp())}:R>", inline=True)
        order_e.set_footer(text=f"{FOOTER_BRAND} | Press 'Publish to Boosters' to release this order")

        await ticket.send(
            embed=order_e,
            view=OrderActionsView(order_id, ticket_channel_id=ticket.id, order_type="ranked")
        )

        await interaction.response.send_message(
            f"✅ Your Ranked Boost order has been placed!\n📩 Ticket opened: {ticket.mention}",
            ephemeral=True
        )


# ---------------------------------------------------------------------------
# PRESTIGE BOOST MODAL
# ---------------------------------------------------------------------------
class PrestigeOrderModal(ui.Modal, title="Prestige Boost Order"):
    notes = ui.TextInput(label="Additional Notes (Optional)", placeholder="Any special requests or information...", required=False, style=discord.TextStyle.long, max_length=500)

    def __init__(self, prestige_spec: str, payment: str):
        super().__init__()
        self.prestige_spec = prestige_spec
        self.payment       = payment

    async def on_submit(self, interaction: discord.Interaction):
        conn     = get_db()
        c        = conn.cursor()
        order_id = f"PREST-{uuid.uuid4().hex[:6].upper()}"
        c.execute(
            "INSERT INTO orders (id, user_id, from_tier, to_tier, price, method) VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, interaction.user.id, self.prestige_spec.split("->")[0].strip(),
             self.prestige_spec.split("->")[-1].strip(), 0.0, self.payment)
        )
        conn.commit()
        conn.close()

        guild  = interaction.guild
        member = interaction.user
        cfg    = get_config(guild.id)

        # Use prestige-specific ticket channel if configured
        prestige_ticket_ch_id = cfg["prestige_ticket_channel_id"] if cfg else None

        welcome = base_embed("✨ Prestige Boost Ticket", color=ACCENT)
        welcome.description = (
            f"Welcome, {member.mention}! ✨\n\n"
            f"📋 **Order:** `{order_id}`\n"
            f"🏆 **Prestige:** {self.prestige_spec}\n"
            f"💳 **Payment:** {self.payment}\n"
            f"🕐 **Opened:** <t:{int(datetime.utcnow().timestamp())}:F>\n\n"
            "Our staff will contact you shortly to complete your prestige boost. "
            "Please have your payment ready!"
        )
        welcome.set_author(name=member.display_name, icon_url=member.display_avatar.url)

        ticket = await create_ticket_thread(
            guild=guild,
            member=member,
            name=f"prestige-{member.name[:12].lower()}",
            topic_embed=welcome,
            view=TicketCloseView(),
            cfg=cfg,
            override_channel_id=prestige_ticket_ch_id,
        )

        # Store ticket channel id
        conn = get_db()
        c    = conn.cursor()
        c.execute("UPDATE orders SET ticket_channel_id = ? WHERE id = ?", (ticket.id, order_id))
        conn.commit()
        conn.close()

        # Post the order card inside the ticket so staff can publish it
        order_e = base_embed("✨ New Prestige Boost Order", color=ACCENT)
        order_e.set_author(name="BrawlCarry | Staff View", icon_url=guild.icon.url if guild.icon else discord.Embed.Empty)
        order_e.add_field(name="👤 Customer",  value=member.mention, inline=True)
        order_e.add_field(name="🏆 Prestige",  value=self.prestige_spec, inline=True)
        order_e.add_field(name="💳 Payment",   value=self.payment, inline=True)
        order_e.add_field(name="🆔 Order ID",  value=f"`{order_id}`", inline=True)
        order_e.add_field(name="🕐 Placed",    value=f"<t:{int(datetime.utcnow().timestamp())}:R>", inline=True)
        order_e.set_footer(text=f"{FOOTER_BRAND} | Press 'Publish to Boosters' to release this order")

        await ticket.send(
            embed=order_e,
            view=OrderActionsView(order_id, ticket_channel_id=ticket.id, order_type="prestige")
        )

        await interaction.response.send_message(
            f"✅ Your Prestige Boost order has been placed!\n📩 Ticket opened: {ticket.mention}",
            ephemeral=True
        )


# ---------------------------------------------------------------------------
# ORDER COMPLETE MODAL
# ---------------------------------------------------------------------------
class OrderCompleteModal(ui.Modal, title="Complete Order"):
    order_id_input = ui.TextInput(label="Order ID",                   placeholder="RANKED-XXXXXX / CARRY-XXXXXX / PREST-XXXXXX", style=discord.TextStyle.short)
    final_price    = ui.TextInput(label="Final Price Paid (USD)",      placeholder="44.99",                                        style=discord.TextStyle.short)
    payment_used   = ui.TextInput(label="Payment Method Used",         placeholder="PayPal / Bank Transfer / Crypto ...",          style=discord.TextStyle.short)
    notes          = ui.TextInput(label="Completion Notes (Optional)", placeholder="e.g. Reached Masters III, completed in 2 hours", required=False, style=discord.TextStyle.long, max_length=500)
    image_url      = ui.TextInput(label="Proof Image URL (Optional)",  placeholder="https://i.imgur.com/...",                      required=False, style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        order_id = self.order_id_input.value.strip().upper()
        conn     = get_db()
        c        = conn.cursor()
        c.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = c.fetchone()

        if not order:
            conn.close()
            await interaction.response.send_message(f"❌ Order `{order_id}` not found.", ephemeral=True)
            return

        try:
            price_val = float(self.final_price.value.replace("$", "").strip())
        except ValueError:
            price_val = order["price"]

        now = datetime.utcnow()
        c.execute(
            "UPDATE orders SET status = 'completed', price = ?, method = ?, completed_at = ? WHERE id = ?",
            (price_val, self.payment_used.value.strip(), now, order_id)
        )
        conn.commit()

        guild_id     = interaction.guild.id if interaction.guild else None
        completed_ch = None
        customer     = None
        if guild_id:
            cfg = get_config(guild_id)
            if cfg and cfg["completed_channel_id"]:
                completed_ch = interaction.guild.get_channel(cfg["completed_channel_id"])
        if order["user_id"]:
            customer = interaction.guild.get_member(order["user_id"])
        conn.close()

        img = self.image_url.value.strip() if self.image_url.value else None

        e = base_embed("✅ Order Completed", color=SUCCESS)
        e.set_author(name="BrawlCarry | Order Completed", icon_url=interaction.user.display_avatar.url)
        e.add_field(name="🆔 Order ID",     value=f"`{order_id}`",                                              inline=True)
        e.add_field(name="👤 Customer",     value=customer.mention if customer else f"<@{order['user_id']}>",   inline=True)
        e.add_field(name="💵 Amount Paid",  value=f"**${price_val:.2f}**",                                      inline=True)
        e.add_field(name="💳 Payment",      value=f"**{self.payment_used.value.strip()}**",                     inline=True)
        e.add_field(name="📦 Route",        value=f"`{order['from_tier']}` → `{order['to_tier']}`",             inline=True)
        e.add_field(name="✅ Completed By", value=interaction.user.mention,                                     inline=True)
        e.add_field(name="🕐 Completed At", value=f"<t:{int(now.timestamp())}:F>",                              inline=False)
        if self.notes.value:
            e.add_field(name="📝 Notes", value=self.notes.value, inline=False)

        wm_file = None
        if img:
            wm_file = await fetch_and_watermark(img)
            if wm_file:
                e.set_image(url="attachment://proof.jpg")

        await interaction.response.send_message("✅ Order marked as completed!", ephemeral=True)

        if completed_ch:
            if wm_file:
                await completed_ch.send(embed=e, file=wm_file)
            else:
                await completed_ch.send(embed=e)
        else:
            if wm_file:
                await interaction.channel.send(embed=e, file=wm_file)
            else:
                await interaction.channel.send(embed=e)
            await interaction.followup.send("⚠️ No completed-orders channel configured. Use `/setup` to set one.", ephemeral=True)

        if customer:
            try:
                dm_e = base_embed("✅ Your Order is Complete!", color=SUCCESS)
                dm_e.description = (
                    f"Great news! Your order **`{order_id}`** has been completed.\n\n"
                    f"📦 **Route:** `{order['from_tier']}` → `{order['to_tier']}`\n"
                    f"💵 **Amount:** ${price_val:.2f}\n"
                    f"💳 **Payment:** {self.payment_used.value.strip()}\n\n"
                    "Thank you for choosing BrawlCarry! Consider leaving a vouch ⭐"
                )
                await customer.send(embed=dm_e)
            except discord.Forbidden:
                pass


# ---------------------------------------------------------------------------
# RANKED BOOST SELECT-MENU VIEW
# ---------------------------------------------------------------------------
class RankedOrderView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.current_rank = None
        self.desired_rank = None
        self.p11          = None
        self.payment      = None

        current_options = []
        for r in CURRENT_RANKS:
            emo = rank_emoji(r)
            opt = discord.SelectOption(label=r, value=r)
            if emo:
                opt.emoji = emo
            current_options.append(opt)

        current_select = ui.Select(placeholder="Select your current rank...", options=current_options, custom_id="ranked_current", row=0)
        current_select.callback = self._on_current
        self.add_item(current_select)

        desired_options = []
        for r in DESIRED_RANKS:
            emo = rank_emoji(r)
            opt = discord.SelectOption(label=r, value=r)
            if emo:
                opt.emoji = emo
            desired_options.append(opt)

        desired_select = ui.Select(placeholder="Select your desired rank...", options=desired_options, custom_id="ranked_desired", row=1)
        desired_select.callback = self._on_desired
        self.add_item(desired_select)

        p11_select = ui.Select(
            placeholder="Select number of Power 11 brawlers...",
            options=[discord.SelectOption(label=n, value=n, emoji=P11_EMOJI) for n in P11_OPTIONS],
            custom_id="ranked_p11", row=2
        )
        p11_select.callback = self._on_p11
        self.add_item(p11_select)

        methods   = get_payment_methods(guild_id)
        pay_select = ui.Select(
            placeholder="Select payment method...",
            options=[discord.SelectOption(label=lbl, value=lbl, emoji=emo) for lbl, emo in methods],
            custom_id="ranked_pay", row=3
        )
        pay_select.callback = self._on_pay
        self.add_item(pay_select)

        submit_btn = ui.Button(label="Submit", style=discord.ButtonStyle.primary, custom_id="ranked_submit", row=4, emoji="✅")
        submit_btn.callback = self._on_submit
        self.add_item(submit_btn)

        cancel_btn = ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="ranked_cancel", row=4, emoji="✖️")
        cancel_btn.callback = self._on_cancel
        self.add_item(cancel_btn)

    async def _on_current(self, interaction): self.current_rank = interaction.data["values"][0]; await interaction.response.defer()
    async def _on_desired(self, interaction): self.desired_rank = interaction.data["values"][0]; await interaction.response.defer()
    async def _on_p11(self, interaction):     self.p11          = interaction.data["values"][0]; await interaction.response.defer()
    async def _on_pay(self, interaction):     self.payment      = interaction.data["values"][0]; await interaction.response.defer()

    async def _on_submit(self, interaction: discord.Interaction):
        missing = []
        if not self.current_rank: missing.append("Current Rank")
        if not self.desired_rank: missing.append("Desired Rank")
        if not self.p11:          missing.append("Power 11 Brawlers")
        if not self.payment:      missing.append("Payment Method")
        if missing:
            await interaction.response.send_message(f"❌ Please fill in: **{', '.join(missing)}**", ephemeral=True)
            return
        await interaction.response.send_modal(RankedOrderModal(self.current_rank, self.desired_rank, self.p11, self.payment))

    async def _on_cancel(self, interaction: discord.Interaction):
        await interaction.response.send_message("❌ Order cancelled.", ephemeral=True)
        await interaction.message.delete()


# ---------------------------------------------------------------------------
# PRESTIGE BOOST SELECT-MENU VIEW
# ---------------------------------------------------------------------------
class PrestigeOrderView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.prestige_spec = None
        self.payment       = None

        pres_options = []
        for p in PRESTIGE_OPTIONS:
            emo = prestige_emoji(p)
            opt = discord.SelectOption(label=p, value=p)
            # Only set emoji if it's a real custom emoji (not a placeholder)
            if "REPLACE_WITH" not in emo:
                opt.emoji = emo
            pres_options.append(opt)

        pres_select = ui.Select(
            placeholder="Select prestige spec...",
            options=pres_options,
            custom_id="prest_spec", row=0
        )
        pres_select.callback = self._on_spec
        self.add_item(pres_select)

        methods   = get_payment_methods(guild_id)
        pay_select = ui.Select(
            placeholder="Select payment method...",
            options=[discord.SelectOption(label=lbl, value=lbl, emoji=emo) for lbl, emo in methods],
            custom_id="prest_pay", row=1
        )
        pay_select.callback = self._on_pay
        self.add_item(pay_select)

        submit_btn = ui.Button(label="Submit", style=discord.ButtonStyle.primary, custom_id="prest_submit", row=2, emoji="✅")
        submit_btn.callback = self._on_submit
        self.add_item(submit_btn)

        cancel_btn = ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="prest_cancel", row=2, emoji="✖️")
        cancel_btn.callback = self._on_cancel
        self.add_item(cancel_btn)

    async def _on_spec(self, interaction): self.prestige_spec = interaction.data["values"][0]; await interaction.response.defer()
    async def _on_pay(self, interaction):  self.payment       = interaction.data["values"][0]; await interaction.response.defer()

    async def _on_submit(self, interaction: discord.Interaction):
        missing = []
        if not self.prestige_spec: missing.append("Prestige Spec")
        if not self.payment:       missing.append("Payment Method")
        if missing:
            await interaction.response.send_message(f"❌ Please fill in: **{', '.join(missing)}**", ephemeral=True)
            return
        await interaction.response.send_modal(PrestigeOrderModal(self.prestige_spec, self.payment))

    async def _on_cancel(self, interaction: discord.Interaction):
        await interaction.response.send_message("❌ Order cancelled.", ephemeral=True)
        await interaction.message.delete()


# ---------------------------------------------------------------------------
# PANEL BUTTON VIEWS  (persistent — posted once in the order channel)
# ---------------------------------------------------------------------------
class RankedPanelButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Ranked Boost Order", style=discord.ButtonStyle.danger, emoji="🔥", custom_id="ranked_panel_btn_v1")
    async def open_ranked(self, interaction: discord.Interaction, button: ui.Button):
        e = base_embed("🔥 Ranked Boost Order", color=PRIMARY)
        e.description = (
            "Fill in the fields below and press **Submit** to place your order.\n"
            "A private ticket will be created for you automatically."
        )
        e.add_field(name="⚠️ Notice", value="Do not share passwords or sensitive information.", inline=False)
        await interaction.response.send_message(embed=e, view=RankedOrderView(interaction.guild_id), ephemeral=True)


class PrestigePanelButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Prestige Boost Order", style=discord.ButtonStyle.primary, emoji="✨", custom_id="prestige_panel_btn_v1")
    async def open_prestige(self, interaction: discord.Interaction, button: ui.Button):
        e = base_embed("✨ Prestige Boost Order", color=ACCENT)
        e.description = (
            "Fill in the fields below and press **Submit** to place your order.\n"
            "A private ticket will be created for you automatically."
        )
        e.add_field(name="⚠️ Notice", value="Do not share passwords or sensitive information.", inline=False)
        await interaction.response.send_message(embed=e, view=PrestigeOrderView(interaction.guild_id), ephemeral=True)


# ---------------------------------------------------------------------------
# OTHER PERSISTENT VIEWS
# ---------------------------------------------------------------------------
class OrderButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Place Order", style=discord.ButtonStyle.primary, emoji="🎮", custom_id="order_btn_v2")
    async def order(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(OrderModal())


class VouchButtonView(ui.View):
    def __init__(self, order_id: str = None):
        super().__init__(timeout=None)
        self.order_id = order_id

    @ui.button(label="Submit a Vouch", style=discord.ButtonStyle.success, emoji="⭐", custom_id="vouch_btn_v2")
    async def vouch(self, interaction: discord.Interaction, button: ui.Button):
        guild_id = interaction.guild.id if interaction.guild else 0
        e = base_embed("⭐ Submit Your Vouch", color=GOLD)
        e.description = (
            "Select your **rating** and **payment method**, then click **Continue** "
            "to fill in your feedback and proof.\n\nThank you for taking the time to vouch!"
        )
        await interaction.response.send_message(embed=e, view=VouchSelectorView(guild_id, order_id=self.order_id), ephemeral=True)


class GiveawayView(ui.View):
    def __init__(self, giveaway_id: str):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @ui.button(label="Enter Giveaway", style=discord.ButtonStyle.success, emoji="🎉", custom_id="ga_enter_v2")
    async def enter(self, interaction: discord.Interaction, button: ui.Button):
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM giveaways WHERE id = ?", (self.giveaway_id,))
        ga = c.fetchone()
        if not ga:
            await interaction.response.send_message("❌ Giveaway not found.", ephemeral=True)
            conn.close()
            return
        participants = json.loads(ga["participants"]) if ga["participants"] else []
        if interaction.user.id in participants:
            await interaction.response.send_message("❌ You have already entered this giveaway.", ephemeral=True)
        else:
            participants.append(interaction.user.id)
            c.execute("UPDATE giveaways SET participants = ? WHERE id = ?", (json.dumps(participants), self.giveaway_id))
            conn.commit()
            await interaction.response.send_message("✅ You've entered! Good luck 🍀", ephemeral=True)
        conn.close()

    @ui.button(label="Participants", style=discord.ButtonStyle.blurple, emoji="👥", custom_id="ga_view_v2")
    async def view_participants(self, interaction: discord.Interaction, button: ui.Button):
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT participants FROM giveaways WHERE id = ?", (self.giveaway_id,))
        ga = c.fetchone()
        conn.close()
        count = len(json.loads(ga["participants"])) if ga and ga["participants"] else 0
        e = base_embed("👥 Giveaway Participants", color=PRIMARY)
        e.description = f"**{count:,}** participant{'s' if count != 1 else ''} have entered."
        await interaction.response.send_message(embed=e, ephemeral=True)

    @ui.button(label="Extra Entries", style=discord.ButtonStyle.secondary, emoji="🎁", custom_id="ga_extra_v2")
    async def extra(self, interaction: discord.Interaction, button: ui.Button):
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT extra_entries FROM giveaways WHERE id = ?", (self.giveaway_id,))
        ga = c.fetchone()
        conn.close()
        extra = ga["extra_entries"] if ga and ga["extra_entries"] else None
        e = base_embed("🎁 Extra Entry Methods", color=ACCENT)
        e.description = extra if extra else "No extra entry methods configured."
        await interaction.response.send_message(embed=e, ephemeral=True)


# ---------------------------------------------------------------------------
# TICKET VIEWS  (General Support only — no carry order option)
# ---------------------------------------------------------------------------
class TicketView(ui.View):
    """Single-button ticket panel — General Support only."""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="General Support", style=discord.ButtonStyle.primary, emoji="ℹ️", custom_id="ticket_general_btn_v1")
    async def open_support(self, interaction: discord.Interaction, button: ui.Button):
        guild  = interaction.guild
        member = interaction.user
        cfg    = get_config(guild.id)

        e = base_embed("ℹ️ General Support", color=SUCCESS)
        e.description = (
            f"Welcome, {member.mention}!\n\n"
            f"📋 **Category:** General Support\n"
            f"🕐 **Opened:** <t:{int(datetime.utcnow().timestamp())}:F>\n\n"
            "Staff will be with you shortly. Please describe your request in detail."
        )
        e.set_author(name=member.display_name, icon_url=member.display_avatar.url)

        ticket = await create_ticket_thread(
            guild=guild,
            member=member,
            name=f"support-{member.name[:12].lower()}",
            topic_embed=e,
            view=TicketCloseView(),
            cfg=cfg,
        )
        await interaction.response.send_message(f"✅ Support ticket created: {ticket.mention}", ephemeral=True)


class TicketCloseView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket_close_v2")
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        e = base_embed("🔒 Closing Ticket", color=DANGER)
        e.description = "This ticket will be deleted in **5 seconds**."
        await interaction.response.send_message(embed=e)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except Exception:
            pass

    @ui.button(label="Send Vouch Panel", style=discord.ButtonStyle.success, emoji="⭐", custom_id="ticket_send_vouch_v2")
    async def send_vouch(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ Staff only.", ephemeral=True)
            return
        e = base_embed("⭐ Leave a Vouch", color=GOLD)
        e.description = (
            "Thank you for your order! We'd love your feedback.\n\n"
            "📸 Attach a screenshot as proof\n"
            "⭐ Rate your experience (1-5)\n"
            "💬 Leave honest feedback\n\n"
            "Click the button below to submit."
        )
        await interaction.channel.send(embed=e, view=VouchButtonView())
        await interaction.response.send_message("✅ Vouch panel sent.", ephemeral=True)


# ---------------------------------------------------------------------------
# SLASH COMMANDS
# ---------------------------------------------------------------------------

@bot.tree.command(name="setup", description="Configure bot settings for this server")
@app_commands.describe(
    vouch_channel="Channel where vouch posts will be sent",
    ticket_channel="Fallback text channel for ticket threads (General Support)",
    ticket_category="Fallback category for ticket text-channels",
    completed_channel="Channel where completed orders will be posted",
    ranked_ticket_channel="Text channel where Ranked Boost ticket threads are created",
    prestige_ticket_channel="Text channel where Prestige Boost ticket threads are created",
    ranked_panel_channel="Channel where booster claiming cards for Ranked orders are posted",
    prestige_panel_channel="Channel where booster claiming cards for Prestige orders are posted",
    owner="The server owner/admin who manages the bot"
)
@app_commands.checks.has_permissions(administrator=True)
async def setup(
    interaction: discord.Interaction,
    vouch_channel: discord.TextChannel = None,
    ticket_channel: discord.abc.GuildChannel = None,
    ticket_category: discord.CategoryChannel = None,
    completed_channel: discord.TextChannel = None,
    ranked_ticket_channel: discord.TextChannel = None,
    prestige_ticket_channel: discord.TextChannel = None,
    ranked_panel_channel: discord.TextChannel = None,
    prestige_panel_channel: discord.TextChannel = None,
    owner: discord.Member = None,
):
    updates = {}
    if vouch_channel:            updates["vouch_channel_id"]            = vouch_channel.id
    if ticket_channel:           updates["ticket_channel_id"]           = ticket_channel.id
    if ticket_category:          updates["ticket_category_id"]          = ticket_category.id
    if completed_channel:        updates["completed_channel_id"]        = completed_channel.id
    if ranked_ticket_channel:    updates["ranked_ticket_channel_id"]    = ranked_ticket_channel.id
    if prestige_ticket_channel:  updates["prestige_ticket_channel_id"]  = prestige_ticket_channel.id
    if ranked_panel_channel:     updates["ranked_panel_channel_id"]     = ranked_panel_channel.id
    if prestige_panel_channel:   updates["prestige_panel_channel_id"]   = prestige_panel_channel.id
    if owner:                    updates["owner_id"]                    = owner.id
    if updates:
        set_config(interaction.guild.id, **updates)

    e = base_embed("⚙️ Server Configuration", color=SUCCESS)
    e.description = "Bot settings updated successfully."
    if vouch_channel:           e.add_field(name="⭐ Vouch Channel",              value=vouch_channel.mention,           inline=True)
    if ticket_channel:          e.add_field(name="🎫 Fallback Ticket Channel",    value=ticket_channel.mention,          inline=True)
    if ticket_category:         e.add_field(name="📂 Ticket Category",            value=ticket_category.mention,         inline=True)
    if completed_channel:       e.add_field(name="✅ Completed Channel",          value=completed_channel.mention,       inline=True)
    if ranked_ticket_channel:   e.add_field(name="🔥 Ranked Ticket Channel",      value=ranked_ticket_channel.mention,   inline=True)
    if prestige_ticket_channel: e.add_field(name="✨ Prestige Ticket Channel",    value=prestige_ticket_channel.mention, inline=True)
    if ranked_panel_channel:    e.add_field(name="📢 Ranked Claiming Channel",    value=ranked_panel_channel.mention,    inline=True)
    if prestige_panel_channel:  e.add_field(name="📢 Prestige Claiming Channel",  value=prestige_panel_channel.mention,  inline=True)
    if owner:                   e.add_field(name="👑 Owner",                      value=owner.mention,                   inline=True)

    e.add_field(
        name="ℹ️ Order Flow",
        value=(
            "1️⃣ Customer clicks **Ranked/Prestige Boost** button → ticket opens in the dedicated channel\n"
            "2️⃣ An order card appears inside the ticket\n"
            "3️⃣ Staff click **📢 Publish to Boosters** → set earnings → card appears in the claiming channel\n"
            "4️⃣ A booster clicks **🟠 Claim This Boost** → immediately added to the customer's ticket"
        ),
        inline=False
    )
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="order_complete", description="Mark an order as completed")
@app_commands.checks.has_permissions(manage_channels=True)
async def order_complete(interaction: discord.Interaction):
    await interaction.response.send_modal(OrderCompleteModal())


@bot.tree.command(name="add_payment_method", description="Add a payment method to the order forms")
@app_commands.describe(label="Payment method name (e.g. LTC, Revolut)", emoji="Emoji to display next to it")
@app_commands.checks.has_permissions(manage_channels=True)
async def add_payment_method_cmd(interaction: discord.Interaction, label: str, emoji: str = "💳"):
    success = add_payment_method(interaction.guild.id, label.strip(), emoji.strip())
    if success:
        e = base_embed("✅ Payment Method Added", color=SUCCESS)
        e.description = f"{emoji} **{label}** has been added to the payment options."
    else:
        e = base_embed("⚠️ Already Exists", color=GOLD)
        e.description = f"**{label}** is already a configured payment method."
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="remove_payment_method", description="Remove a payment method from the order forms")
@app_commands.describe(label="Exact name of the payment method to remove")
@app_commands.checks.has_permissions(manage_channels=True)
async def remove_payment_method_cmd(interaction: discord.Interaction, label: str):
    success = remove_payment_method(interaction.guild.id, label.strip())
    if success:
        e = base_embed("✅ Payment Method Removed", color=SUCCESS)
        e.description = f"**{label}** has been removed from the payment options."
    else:
        e = base_embed("❌ Not Found", color=DANGER)
        e.description = f"**{label}** was not found in the configured payment methods."
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="list_payment_methods", description="View all configured payment methods")
@app_commands.checks.has_permissions(manage_channels=True)
async def list_payment_methods(interaction: discord.Interaction):
    methods = get_payment_methods(interaction.guild.id)
    e = base_embed("💳 Payment Methods", color=PRIMARY)
    e.description = "\n".join(f"{emo} **{lbl}**" for lbl, emo in methods) if methods else "No payment methods configured."
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="order_panel", description="Post the generic order creation panel in this channel")
@app_commands.describe(image_url="Optional banner image URL")
@app_commands.checks.has_permissions(manage_channels=True)
async def order_panel(interaction: discord.Interaction, image_url: str = None):
    e = base_embed("🎮 Brawl Stars Boost Orders", color=PRIMARY)
    e.description = (
        "Ready to rank up? Click the button below to place your carry order.\n\n"
        "**What we offer:**\n"
        "🥇 Brawl Stars Ranked Boosting\n"
        "⚡ Fast & reliable completion\n"
        "⭐ 5-star rated service\n"
        "🔒 Secure & confidential"
    )
    if image_url:
        e.set_image(url=image_url)
    await interaction.channel.send(embed=e, view=OrderButton())
    await interaction.response.send_message("✅ Order panel posted.", ephemeral=True)


@bot.tree.command(name="ranked_panel", description="Post the Ranked Boost order panel in this channel")
@app_commands.describe(image_url="Optional banner image URL")
@app_commands.checks.has_permissions(manage_channels=True)
async def ranked_panel(interaction: discord.Interaction, image_url: str = None):
    e = base_embed("🔥 Ranked Boost", color=PRIMARY)
    e.description = (
        "Want to climb the ranked ladder? Click the button below to place your **Ranked Boost** order!\n\n"
        "**Pricing** *(depends on starting rank & P11 brawlers)*\n"
        "🏆 Legendary Boost — from **16€**\n"
        "🏆 Masters Boost — from **35€**\n"
        "🏆 Pro Rank — from **200€**\n\n"
        "⚡ Fast & reliable | 🔒 Secure | ⭐ 5-star rated"
    )
    if image_url:
        e.set_image(url=image_url)
    await interaction.channel.send(embed=e, view=RankedPanelButton())
    await interaction.response.send_message("✅ Ranked Boost panel posted.", ephemeral=True)


@bot.tree.command(name="prestige_panel", description="Post the Prestige Boost order panel in this channel")
@app_commands.describe(image_url="Optional banner image URL")
@app_commands.checks.has_permissions(manage_channels=True)
async def prestige_panel(interaction: discord.Interaction, image_url: str = None):
    e = base_embed("✨ Prestige Boost", color=ACCENT)
    e.description = (
        "Unlock your prestige! Click the button below to place your **Prestige Boost** order.\n\n"
        "**Pricing** *(depends on brawler & power level)*\n"
        "🟣 Prestige 0 → 1 — from **10€**\n"
        "🔴 Prestige 1 → 2 — from **25€**\n"
        "🟡 Prestige 2 → 3 — from **70€**\n\n"
        "⚡ Fast & reliable | 🔒 Secure | ⭐ 5-star rated"
    )
    if image_url:
        e.set_image(url=image_url)
    await interaction.channel.send(embed=e, view=PrestigePanelButton())
    await interaction.response.send_message("✅ Prestige Boost panel posted.", ephemeral=True)


@bot.tree.command(name="ticket_panel", description="Post the support ticket panel in this channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def ticket_panel(interaction: discord.Interaction):
    cfg   = get_config(interaction.guild.id)
    title = cfg["ticket_panel_title"] if cfg and cfg["ticket_panel_title"] else "🎫 Support Center"
    desc  = (cfg["ticket_panel_desc"] if cfg and cfg["ticket_panel_desc"]
             else "Need help? Click the button below to open a support ticket.\nOur team will be with you shortly.\n\n📌 Tickets are private and handled by staff only.")
    e = discord.Embed(title=title, color=PRIMARY, description=desc)
    e.set_footer(text=FOOTER_BRAND)
    e.timestamp = datetime.utcnow()
    await interaction.channel.send(embed=e, view=TicketView())
    await interaction.response.send_message("✅ Ticket panel posted.", ephemeral=True)


@bot.tree.command(name="configure_ticket_panel", description="Customise the ticket panel title and description")
@app_commands.checks.has_permissions(administrator=True)
async def configure_ticket_panel(interaction: discord.Interaction):
    cfg   = get_config(interaction.guild.id)
    modal = TicketPanelSetupModal()
    if cfg:
        if cfg["ticket_panel_title"]:
            modal.panel_title.default = cfg["ticket_panel_title"]
        if cfg["ticket_panel_desc"]:
            modal.panel_desc.default = cfg["ticket_panel_desc"]
    await interaction.response.send_modal(modal)


@bot.tree.command(name="vouch_panel", description="Send a vouch request panel to a user or in this channel")
@app_commands.describe(user="DM the vouch panel to this user", order_id="Order ID to attach")
@app_commands.checks.has_permissions(manage_channels=True)
async def vouch_panel(interaction: discord.Interaction, user: discord.User = None, order_id: str = None):
    e = base_embed("⭐ Leave a Vouch", color=GOLD)
    e.description = (
        "Thank you for your order! We'd love your feedback.\n\n"
        "📸 Attach a screenshot as proof\n"
        "⭐ Rate your experience (1-5)\n"
        "💬 Leave honest feedback\n\n"
        "Click the button below to submit."
    )
    if order_id:
        e.set_footer(text=f"{FOOTER_BRAND} | Order: {order_id}")
    view = VouchButtonView(order_id=order_id)
    if user:
        try:
            await user.send(embed=e, view=view)
            await interaction.response.send_message(f"✅ Vouch panel sent to {user.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Could not DM that user. They may have DMs disabled.", ephemeral=True)
    else:
        await interaction.channel.send(embed=e, view=view)
        await interaction.response.send_message("✅ Vouch panel posted.", ephemeral=True)


@bot.tree.command(name="giveaway", description="Start a new giveaway")
@app_commands.describe(
    prize="Prize name", hours="Duration in hours", winners="Number of winners",
    description="Giveaway description or rules",
    extra_entries="Extra entry methods shown when users click the Extra Entries button",
    ping="Who to ping: @everyone, @here, a role mention, or none",
    image_url="Optional banner image URL"
)
@app_commands.checks.has_permissions(manage_channels=True)
async def giveaway(
    interaction: discord.Interaction,
    prize: str, hours: int, winners: int, description: str,
    extra_entries: str = None, ping: str = "@everyone", image_url: str = None
):
    conn    = get_db()
    c       = conn.cursor()
    ga_id   = f"G{uuid.uuid4().hex[:8].upper()}"
    ends_at = datetime.utcnow() + timedelta(hours=hours)
    c.execute(
        "INSERT INTO giveaways (id, prize, desc, winners, hosted_by, participants, image_url, extra_entries, ping, ended_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ga_id, prize, description, winners, interaction.user.id, "[]", image_url, extra_entries, ping, ends_at)
    )
    conn.commit()
    conn.close()

    end_ts = int(ends_at.timestamp())
    e = discord.Embed(title=f"🎁 {prize}", color=PRIMARY)
    e.add_field(name="ℹ️ Description", value=description, inline=False)
    e.add_field(name="⏰ Ends",        value=f"<t:{end_ts}:F>  (<t:{end_ts}:R>)", inline=False)
    e.add_field(name="🏆 Winners",     value=f"**{winners}** winner{'s' if winners != 1 else ''}", inline=True)
    e.add_field(name="👥 Participants",value="**0** entered", inline=True)
    e.add_field(name="🎯 Hosted By",   value=interaction.user.mention, inline=True)
    if extra_entries:
        e.add_field(name="🎁 Bonus Entries", value="Click **Extra Entries** to see how to earn more!", inline=False)
    if image_url:
        e.set_image(url=image_url)
    e.set_footer(text=f"{FOOTER_BRAND} | ID: {ga_id}")
    e.timestamp = datetime.utcnow()

    ping_content = ping if (ping and ping.lower() != "none") else ""
    ping_content = (ping_content + " **🎉 NEW GIVEAWAY!**").strip() if ping_content else "**🎉 NEW GIVEAWAY!**"

    await interaction.channel.send(
        content=ping_content, embed=e, view=GiveawayView(ga_id),
        allowed_mentions=discord.AllowedMentions(everyone=True, roles=True)
    )
    await interaction.response.send_message(f"✅ Giveaway started! ID: `{ga_id}`", ephemeral=True)


@bot.tree.command(name="end_giveaway", description="End a giveaway and pick winners")
@app_commands.describe(giveaway_id="Giveaway ID (shown in the embed footer)")
@app_commands.checks.has_permissions(manage_channels=True)
async def end_giveaway(interaction: discord.Interaction, giveaway_id: str):
    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT * FROM giveaways WHERE id = ?", (giveaway_id,))
    ga = c.fetchone()
    if not ga:
        conn.close()
        await interaction.response.send_message("❌ Giveaway not found.", ephemeral=True)
        return
    participants = json.loads(ga["participants"]) if ga["participants"] else []
    if not participants:
        conn.close()
        await interaction.response.send_message("❌ No participants to draw from.", ephemeral=True)
        return
    winner_ids = random.sample(participants, min(ga["winners"], len(participants)))
    c.execute("UPDATE giveaways SET winner_ids = ? WHERE id = ?", (json.dumps(winner_ids), giveaway_id))
    conn.commit()
    conn.close()
    winner_mentions = " ".join([f"<@{w}>" for w in winner_ids])
    e = discord.Embed(title=f"🎁 {ga['prize']} — Giveaway Ended", color=SUCCESS)
    e.add_field(name="🏆 Winners",           value=winner_mentions,              inline=False)
    e.add_field(name="👥 Total Participants", value=f"**{len(participants):,}**", inline=True)
    e.add_field(name="🆔 Giveaway ID",       value=f"`{giveaway_id}`",           inline=True)
    e.set_footer(text=FOOTER_BRAND)
    e.timestamp = datetime.utcnow()
    await interaction.channel.send(
        content=f"🎉 Congratulations {winner_mentions}! You won **{ga['prize']}**!",
        embed=e,
        allowed_mentions=discord.AllowedMentions(users=True)
    )
    await interaction.response.send_message("✅ Giveaway ended.", ephemeral=True)


@bot.tree.command(name="backup_link", description="DM all members the backup server link")
@app_commands.describe(link="Backup server invite link")
@app_commands.checks.has_permissions(administrator=True)
async def backup_link(interaction: discord.Interaction, link: str):
    await interaction.response.defer(ephemeral=True)
    members = [m for m in interaction.guild.members if not m.bot]
    results = {"sent": 0, "failed": 0}
    sem = asyncio.Semaphore(20)
    async def send_dm(member):
        async with sem:
            try:
                e = base_embed("⚠️ Backup Server", color=DANGER)
                e.description = f"If the main server becomes unavailable, join our backup:\n\n> **{link}**"
                await member.send(embed=e)
                results["sent"] += 1
            except Exception:
                results["failed"] += 1
    await asyncio.gather(*[send_dm(m) for m in members])
    e = base_embed("📨 Backup Link Sent", color=SUCCESS)
    e.add_field(name="✅ Delivered", value=f"**{results['sent']}**",  inline=True)
    e.add_field(name="❌ Failed",    value=f"**{results['failed']}**", inline=True)
    await interaction.followup.send(embed=e, ephemeral=True)


@bot.tree.command(name="stats", description="View carry statistics for a user")
@app_commands.describe(user="User to look up (defaults to you)")
async def stats(interaction: discord.Interaction, user: discord.User = None):
    target = user or interaction.user
    conn   = get_db()
    c      = conn.cursor()
    c.execute("SELECT COUNT(*) as count, SUM(price) as total FROM orders WHERE user_id = ?", (target.id,))
    row = c.fetchone()
    c.execute("SELECT COUNT(*) as vc FROM vouchers WHERE used_by = ?", (target.id,))
    vc = c.fetchone()
    conn.close()
    e = base_embed(f"📊 {target.display_name}'s Stats", color=PRIMARY)
    e.set_thumbnail(url=target.display_avatar.url)
    e.add_field(name="🎮 Total Carries", value=f"**{row['count'] or 0}**", inline=True)
    e.add_field(name="💵 Total Spent",   value=f"**${row['total']:.2f}**" if row["total"] else "**$0.00**", inline=True)
    e.add_field(name="⭐ Vouches",       value=f"**{vc['vc'] or 0}**", inline=True)
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="help", description="View all available bot commands")
async def help_cmd(interaction: discord.Interaction):
    e = base_embed("📋 BrawlCarry Bot — Commands", color=PRIMARY)
    e.description = (
        "**⚙️ Admin Commands**\n"
        "`/setup` — Configure all channels, ticket categories & owner\n"
        "`/configure_ticket_panel` — Customise support ticket panel text\n"
        "`/order_panel` — Post the generic order panel\n"
        "`/ranked_panel` — Post the Ranked Boost intake panel 🔥\n"
        "`/prestige_panel` — Post the Prestige Boost intake panel ✨\n"
        "`/ticket_panel` — Post the General Support ticket panel\n"
        "`/vouch_panel` — Send vouch panel to user or channel\n"
        "`/giveaway` — Start a giveaway\n"
        "`/end_giveaway` — End a giveaway and draw winners\n"
        "`/backup_link` — DM all members the backup server link\n\n"
        "**✅ Staff Commands**\n"
        "`/order_complete` — Mark an order as completed\n"
        "`/add_payment_method` — Add a payment method to order forms\n"
        "`/remove_payment_method` — Remove a payment method from order forms\n"
        "`/list_payment_methods` — View all configured payment methods\n\n"
        "**👤 User Commands**\n"
        "`/stats` — View your carry statistics\n"
        "`/help` — Show this menu\n\n"
        "**📦 Order Flow**\n"
        "1. Customer clicks **Ranked/Prestige Boost** → ticket opens in the dedicated channel\n"
        "2. An order card appears in the ticket for staff\n"
        "3. Staff click **📢 Publish to Boosters** → enter earnings → claiming card posted\n"
        "4. Booster clicks **🟠 Claim This Boost** → instantly added to the customer's ticket\n\n"
        "**⚙️ Channel Setup Tips**\n"
        "• `ranked_ticket_channel` / `prestige_ticket_channel` — separate ticket thread channels per boost type\n"
        "• `ranked_panel_channel` / `prestige_panel_channel` — where booster claiming cards appear\n"
        "• `ticket_channel` — fallback for General Support tickets\n"
        "• `completed_channel` — where completed order receipts are posted"
    )
    await interaction.response.send_message(embed=e, ephemeral=True)


# ---------------------------------------------------------------------------
# ERROR HANDLER
# ---------------------------------------------------------------------------
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "❌ You do not have permission to use this command."
    else:
        msg = f"❌ An error occurred: `{error}`"
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


# ---------------------------------------------------------------------------
# STARTUP
# ---------------------------------------------------------------------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"[OK] {bot.user} | Slash commands synced")

    # Register all persistent views
    bot.add_view(OrderButton())
    bot.add_view(TicketView())
    bot.add_view(TicketCloseView())
    bot.add_view(VouchButtonView())
    bot.add_view(RankedPanelButton())
    bot.add_view(PrestigePanelButton())

    # Re-register active giveaway views
    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT id FROM giveaways WHERE winner_ids IS NULL OR winner_ids = ''")
    for row in c.fetchall():
        bot.add_view(GiveawayView(row["id"]))

    # Re-register active order action views (unclaimed/claimed orders — staff publish button)
    c.execute("SELECT id, ticket_channel_id FROM orders WHERE status IN ('pending', 'claimed')")
    for row in c.fetchall():
        # Re-register both ranked and prestige types; order_type stored implicitly by ID prefix
        order_type = "prestige" if row["id"].startswith("PREST") else "ranked"
        bot.add_view(OrderActionsView(row["id"], row["ticket_channel_id"], order_type))

    # Re-register booster claim views for unclaimed orders
    c.execute("SELECT id, ticket_channel_id FROM orders WHERE status = 'pending'")
    for row in c.fetchall():
        bot.add_view(BoosterClaimView(row["id"], row["ticket_channel_id"]))

    conn.close()
    print(f"[OK] Persistent views registered")


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("[ERROR] DISCORD_TOKEN not set in environment.")
        exit(1)
    bot.run(token)
