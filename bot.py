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

FOOTER_BRAND = "Powered by Brawl Carry(tm)"

intents = discord.Intents.default()
intents.message_content = True
intents.members         = True
intents.guilds          = True
intents.dm_messages     = True

bot = commands.Bot(command_prefix="\x00", intents=intents, help_command=None)
ALLOWED_GUILDS = [
    int(g.strip()) for g in os.getenv("ALLOWED_GUILDS", "").split(",") if g.strip()
]

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
        order_type TEXT,
        service_type TEXT,
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
        order_kind TEXT,
        service_type TEXT,
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
        ("orders",       "order_type TEXT"),
        ("orders",       "service_type TEXT"),
        ("guild_config", "application_channel_id INT"),
        ("guild_config", "application_review_channel_id INT"),
        ("guild_config", "account_sale_channel_id INT"),
        ("giveaways",    "bonus_role_id INT"),
        ("guild_config", "ticket_log_channel_id INT"),
        ("vouchers",     "order_kind TEXT"),
        ("vouchers",     "service_type TEXT"),
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
    "ticket_log_channel_id",
    "application_channel_id",
    "application_review_channel_id",
    "account_sale_channel_id",
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
    ("Bank Transfer", "\U0001f3e6"),
    ("Crypto",        "\U0001fa99"),
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
    view,
    cfg,
    override_channel_id: int = None,
):
    ticket_ch_id = override_channel_id or (cfg["ticket_channel_id"] if cfg else None)
    category_id  = cfg["ticket_category_id"] if cfg else None

if ticket_ch_id:
        text_ch = guild.get_channel(ticket_ch_id)
        if isinstance(text_ch, discord.TextChannel):
            try:
                thread = await text_ch.create_thread(
                    name=name,
                    type=discord.ChannelType.private_thread,
                    reason=f"Ticket opened by {member}",
                )
            except (discord.Forbidden, discord.HTTPException):
                thread = await text_ch.create_thread(
                    name=name,
                    type=discord.ChannelType.public_thread,
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
# ---------------------------------------------------------------------------
PRESTIGE_OPTIONS = [
    "Prestige 0 -> Prestige 1",
    "Prestige 1 -> Prestige 2",
    "Prestige 2 -> Prestige 3",
]

# Edit these prices freely — they are used in /prestige_panel automatically
PRESTIGE_PRICES = {
    "Prestige 0 -> Prestige 1": "10",
    "Prestige 1 -> Prestige 2": "25",
    "Prestige 2 -> Prestige 3": "70",
}

PRESTIGE_EMOJI = {
    "Prestige 0 -> Prestige 1": "<:Prestige1:1491103698116677693>",
    "Prestige 1 -> Prestige 2": "<:Prestige2:1491103696153477161>",
    "Prestige 2 -> Prestige 3": "<:Prestige3:1491103694433816688>",
}

def prestige_emoji(spec: str) -> str:
    return PRESTIGE_EMOJI.get(spec, "\u2728")

def rank_emoji(rank_name: str) -> str:
    for prefix, emoji in RANK_EMOJI.items():
        if rank_name.startswith(prefix):
            return emoji
    return ""

P11_OPTIONS = ["0-10", "11-20", "21-30", "31-40", "41-50", "51-60", "61-70", "71+"]
P11_EMOJI   = "<:P11:1491455088429109258>"

# Prestige trophy bracket options
TROPHY_OPTIONS = [
    "0 - 500",
    "501 - 1000",
    "1001 - 1500",
    "1501 - 2000",
    "2001 - 2500",
    "2501 - 3000",
    "3001+",
]

# Service type options (boost vs carry)
SERVICE_OPTIONS = [
    discord.SelectOption(label="Boost",  value="boost",  emoji="\U0001f7e2", description="Play on your account — standard price"),
    discord.SelectOption(label="Carry",  value="carry",  emoji="\U0001f534", description="Play alongside you — 2x price"),
]

RATING_OPTIONS = [
    discord.SelectOption(label="5 Stars", value="5", emoji="\u2b50", description="Excellent service"),
    discord.SelectOption(label="4 Stars", value="4", emoji="\u2b50", description="Great service"),
    discord.SelectOption(label="3 Stars", value="3", emoji="\u2b50", description="Good service"),
    discord.SelectOption(label="2 Stars", value="2", emoji="\u2b50", description="Average service"),
    discord.SelectOption(label="1 Star",  value="1", emoji="\u2b50", description="Below expectations"),
]

# ---------------------------------------------------------------------------
# DIRECT BOOSTER CLAIM VIEW
# ---------------------------------------------------------------------------
class BoosterClaimView(ui.View):
    def __init__(self, order_id: str, ticket_channel_id: int = None):
        super().__init__(timeout=None)
        self.order_id          = order_id
        self.ticket_channel_id = ticket_channel_id

    @ui.button(label="Claim This Boost", style=discord.ButtonStyle.primary, emoji="\U0001f7e0", custom_id="booster_claim_direct_v1")
    async def claim(self, interaction: discord.Interaction, button: ui.Button):
        guild   = interaction.guild
        booster = interaction.user

        # Safely resolve order_id from embed in case instance state was lost after restart
        order_id = self.order_id
        if not order_id and interaction.message and interaction.message.embeds:
            for field in interaction.message.embeds[0].fields:
                if "Order ID" in field.name:
                    order_id = field.value.strip("`").strip()
                    break
        if not order_id:
            await interaction.response.send_message("❌ Could not resolve order ID. Contact an admin.", ephemeral=True)
            return
        self.order_id = order_id

        conn = get_db()
        c    = conn.cursor()
        c.execute("SELECT * FROM orders WHERE id = ?", (self.order_id,))
        order = c.fetchone()
        conn.close()

        if not order:
            await interaction.response.send_message("\u274c Order not found.", ephemeral=True)
            return

conn_check = get_db()
        c_check = conn_check.cursor()
        c_check.execute(
            "SELECT COUNT(*) as cnt FROM orders WHERE booster_id = ? AND status = 'claimed'",
            (booster.id,)
        )
        active_count = c_check.fetchone()["cnt"]
        conn_check.close()
        if active_count >= 2:
            await interaction.response.send_message(
                "❌ You already have **2 active orders**. Please complete one before claiming another.",
                ephemeral=True
            )
            return
    
        if order["status"] == "claimed":
            await interaction.response.send_message(
                "\u274c This order has already been claimed by another booster.", ephemeral=True
            )
            return

        conn = get_db()
        c    = conn.cursor()
        c.execute(
            "UPDATE orders SET booster_id = ?, status = 'claimed' WHERE id = ?",
            (booster.id, self.order_id)
        )
        conn.commit()
        conn.close()

        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

try:
            original_embed = interaction.message.embeds[0] if interaction.message.embeds else None
            if original_embed:
                original_embed.color = SUCCESS
                original_embed.title = "✅ Order Claimed — " + (original_embed.title or "")
                original_embed.add_field(name="🟠 Claimed By", value=booster.mention, inline=True)
                original_embed.add_field(name="⏰ Claimed At", value=f"<t:{int(datetime.utcnow().timestamp())}:R>", inline=True)
                await interaction.message.edit(embed=original_embed, view=self)
        except Exception as ex:
            print(f"[WARN] Could not edit claim embed: {ex}")

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
                    notify_e = base_embed("\U0001f7e0 Booster Assigned", color=SUCCESS)
                    notify_e.description = (
                        f"{booster.mention} has claimed order `{self.order_id}` and has been added to this ticket.\n"
                        "Please coordinate here to complete the boost! \U0001f3c6"
                    )
                    await ticket_ch.send(embed=notify_e)
                except Exception as ex:
                    print(f"[WARN] Could not add booster to ticket: {ex}")

        try:
            dm_e = base_embed("\u2705 Boost Claimed!", color=SUCCESS)
            dm_e.description = (
                f"You've successfully claimed order **`{self.order_id}`**!\n\n"
                "You have been added to the customer's ticket. Good luck! \U0001f3c6"
            )
            await booster.send(embed=dm_e)
        except discord.Forbidden:
            pass

        await interaction.response.send_message(
            f"\u2705 You've claimed order `{self.order_id}`! Check the customer's ticket.",
            ephemeral=True
        )


# ---------------------------------------------------------------------------
# PUBLISH TO BOOSTERS MODAL
# ---------------------------------------------------------------------------
class PublishToBoostersModal(ui.Modal, title="Publish Order to Boosters"):
    booster_earnings = ui.TextInput(
        label="Booster Earnings (EUR)",
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

    def __init__(self, order_id: str, ticket_channel_id: int = None, panel_channel_id: int = None, order_type: str = "ranked"):
        super().__init__()
        self.order_id          = order_id
        self.ticket_channel_id = ticket_channel_id
        self.panel_channel_id  = panel_channel_id
        self.order_type        = order_type

    async def on_submit(self, interaction: discord.Interaction):
        try:
            earnings = float(self.booster_earnings.value.replace("\u20ac", "").strip())
        except ValueError:
            await interaction.response.send_message(
                "\u274c Invalid earnings amount. Please enter a number like `12.00`.", ephemeral=True
            )
            return

        conn = get_db()
        c    = conn.cursor()
        c.execute("SELECT * FROM orders WHERE id = ?", (self.order_id,))
        order = c.fetchone()
        if not order:
            conn.close()
            await interaction.response.send_message("\u274c Order not found.", ephemeral=True)
            return

        c.execute("UPDATE orders SET booster_earnings = ? WHERE id = ?", (earnings, self.order_id))
        conn.commit()
        conn.close()

        guild       = interaction.guild
        panel_ch_id = self.panel_channel_id
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
                "\u274c Panel channel not found. Make sure it is configured via `/setup`.", ephemeral=True
            )
            return

        color      = PRIMARY if self.order_type == "ranked" else ACCENT
        title_str  = "\U0001f525 Ranked Boost Available" if self.order_type == "ranked" else "\u2728 Prestige Boost Available"
        svc_type   = order["service_type"] or "boost"
        svc_label  = "Carry \U0001f534" if svc_type == "carry" else "Boost \U0001f7e2"

        # Build order details label
        from_tier  = order["from_tier"] or "?"
        to_tier    = order["to_tier"] or "?"
        if self.order_type == "ranked":
            fe = rank_emoji(from_tier)
            te = rank_emoji(to_tier)
            details = f"{fe} `{from_tier}` \u2192 {te} `{to_tier}`"
        else:
            pe = prestige_emoji(f"{from_tier} -> {to_tier}")
            details = f"{pe} `{from_tier}` \u2192 `{to_tier}`"

        pay_emoji  = _payment_emoji(order["method"], guild.id)

        claim_e = base_embed(title_str, color=color)
        claim_e.set_author(
            name="BrawlCarry | Boost Available",
            icon_url=guild.icon.url if guild.icon else discord.Embed.Empty
        )
        claim_e.add_field(name="\U0001f4e6 Order Details", value=details,                               inline=True)
        claim_e.add_field(name="\U0001f4b0 You Earn",      value=f"**\u20ac{earnings:.2f}**",          inline=True)
        claim_e.add_field(name=f"{pay_emoji} Payment",     value=order["method"] or "---",             inline=True)
        claim_e.add_field(name="\U0001f6e0 Service",       value=svc_label,                            inline=True)
        claim_e.add_field(name="\U0001f194 Order ID",      value=f"`{self.order_id}`",                 inline=True)
        claim_e.add_field(name="\U0001f550 Posted",        value=f"<t:{int(datetime.utcnow().timestamp())}:R>", inline=True)

        if self.extra_notes.value:
            claim_e.add_field(name="\U0001f4dd Notes", value=self.extra_notes.value, inline=False)

        claim_e.set_footer(text=f"{FOOTER_BRAND} | Click the button below to claim this order")

        await panel_ch.send(
            embed=claim_e,
            view=BoosterClaimView(self.order_id, ticket_channel_id=self.ticket_channel_id)
        )

        await interaction.response.send_message(
            f"\u2705 Order `{self.order_id}` published to {panel_ch.mention} with **\u20ac{earnings:.2f}** booster earnings.",
            ephemeral=True
        )


# ---------------------------------------------------------------------------
# ORDER ACTIONS VIEW
# ---------------------------------------------------------------------------
class OrderActionsView(ui.View):
    def __init__(self, order_id: str, ticket_channel_id: int = None, order_type: str = "ranked"):
        super().__init__(timeout=None)
        self.order_id          = order_id
        self.ticket_channel_id = ticket_channel_id
        self.order_type        = order_type

    @ui.button(label="Publish to Boosters", style=discord.ButtonStyle.success, emoji="\U0001f4e2", custom_id="order_publish_btn_v1")
    async def publish(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "\u274c Only staff can publish orders to boosters.", ephemeral=True
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
# HELPER: resolve payment emoji from guild config
# ---------------------------------------------------------------------------
def _payment_emoji(method_label: str, guild_id: int) -> str:
    if not method_label:
        return "\U0001f4b3"
    methods = get_payment_methods(guild_id)
    for lbl, emo in methods:
        if lbl.lower() == method_label.lower():
            return emo
    return "\U0001f4b3"


# ---------------------------------------------------------------------------
# MODALS
# ---------------------------------------------------------------------------
class OrderModal(ui.Modal, title="Create Carry Order"):
    from_tier = ui.TextInput(label="From (Current Rank / Prestige / Tier)", placeholder="e.g. Diamond III", style=discord.TextStyle.short)
    to_tier   = ui.TextInput(label="To (Target Rank / Prestige / Tier)",   placeholder="e.g. Masters I",   style=discord.TextStyle.short)
    price     = ui.TextInput(label="Agreed Price (EUR)",                    placeholder="44.99",             style=discord.TextStyle.short)
    method    = ui.TextInput(label="Payment Method",                        placeholder="PayPal / Bank Transfer / Crypto ...", style=discord.TextStyle.short)
    image_url = ui.TextInput(label="Proof Image URL (optional)", placeholder="https://i.imgur.com/...", required=False, style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price_val = float(self.price.value.replace("\u20ac", "").strip())
        except ValueError:
            await interaction.response.send_message("\u274c Invalid price. Please enter a number like `44.99`.", ephemeral=True)
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

        fe  = rank_emoji(self.from_tier.value)
        te  = rank_emoji(self.to_tier.value)
        pay_emo = _payment_emoji(self.method.value, interaction.guild_id)

        e = base_embed("\U0001f680 New Carry Order", color=PRIMARY)
        e.set_author(name="BrawlCarry | Brawl Stars Boost", icon_url=interaction.user.display_avatar.url)
        e.add_field(name="\U0001f464 Customer",       value=interaction.user.mention,                                    inline=True)
        e.add_field(name="\U0001f4b6 Amount",          value=f"**\u20ac{price_val:.2f}**",                              inline=True)
        e.add_field(name="\U0001f3ae Type",            value="Ranked Boost",                                             inline=True)
        e.add_field(name="\U0001f4e6 Order Details",   value=f"{fe} `{self.from_tier.value}` \u2192 {te} `{self.to_tier.value}`", inline=False)
        e.add_field(name=f"{pay_emo} Payment",         value=self.method.value,                                          inline=True)
        e.add_field(name="\U0001f194 Order ID",        value=f"`{order_id}`",                                            inline=True)

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
        await interaction.response.send_message("\u2705 Order submitted!", ephemeral=True)


# ---------------------------------------------------------------------------
# VOUCH DETAIL MODAL
# ---------------------------------------------------------------------------
class VouchDetailModal(ui.Modal, title="Submit Your Vouch"):
    amount   = ui.TextInput(label="Order Amount (EUR)", placeholder="44.99", style=discord.TextStyle.short)
    feedback = ui.TextInput(label="Your Feedback", placeholder="Fast service, very professional...", style=discord.TextStyle.long, max_length=500)
    image_url = ui.TextInput(label="Proof Image URL (optional)", placeholder="https://i.imgur.com/...", required=False, style=discord.TextStyle.short)

    def __init__(self, rating: int, payment_method: str, order_kind: str = "ranked", service_type: str = "boost"):
        super().__init__()
        self.rating         = rating
        self.payment_method = payment_method
        self.order_kind     = order_kind    # "ranked" or "prestige"
        self.service_type   = service_type  # "boost" or "carry"

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount_val = float(self.amount.value.replace("\u20ac", "").strip())
        except ValueError:
            amount_val = 0.0

        stars    = self.rating
        star_str = "\u2b50" * stars + f"  ({stars}/5)"
        img      = self.image_url.value.strip() if self.image_url.value else None

        vouch_id = f"VOUCH-{uuid.uuid4().hex[:6].upper()}"
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM vouchers")
        vouch_number = c.fetchone()["cnt"] + 1
        c.execute(
            "INSERT INTO vouchers (id, code, amount, used_by, rating, feedback, image_url, method, order_kind, service_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (vouch_id, vouch_id, amount_val, interaction.user.id, stars, self.feedback.value, img,
             self.payment_method, self.order_kind, self.service_type)
        )
        conn.commit()
        guild_id    = interaction.guild.id if interaction.guild else None
        vouch_ch_id = None
        if guild_id:
            cfg = get_config(guild_id)
            if cfg:
                vouch_ch_id = cfg["vouch_channel_id"]
        conn.close()

        # Build service label
        if self.order_kind == "prestige":
            svc_icon  = prestige_emoji("Prestige 0 -> Prestige 1")  # generic prestige icon
            kind_label = "Prestige Boost" if self.service_type == "boost" else "Prestige Carry"
        else:
            kind_label = "Ranked Boost" if self.service_type == "boost" else "Ranked Carry"
            svc_icon  = "\U0001f525"

        svc_color = GOLD
        pay_emoji = _payment_emoji(self.payment_method, guild_id or 0)

        # Star graphic
        filled   = "\u2b50"
        empty    = "\u2b1c"
        star_vis = filled * stars + empty * (5 - stars)

        e = discord.Embed(color=svc_color)
        e.set_author(
            name=f"{interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url
        )
        e.title = f"⭐ Vouch N°{vouch_number}  |  {star_vis}"
        e.add_field(name="\U0001f464 Customer",        value=interaction.user.mention,         inline=True)
        e.add_field(name=f"\U0001f4b0 Amount Paid",    value=f"**\u20ac{amount_val:.2f}**",   inline=True)
        e.add_field(name=f"{pay_emoji} Payment",       value=f"**{self.payment_method}**",     inline=True)
        e.add_field(name=f"{svc_icon} Service",        value=f"**{kind_label}**",              inline=True)
        e.add_field(name="\u2b50 Rating",              value=star_str,                         inline=True)
        e.add_field(name="\U0001f4ac Feedback",        value=f"> {self.feedback.value}",       inline=False)
        e.set_footer(text=FOOTER_BRAND)
        e.timestamp = datetime.utcnow()

        wm_file = None
        if img:
            wm_file = await fetch_and_watermark(img, blur=True)
            if wm_file:
                e.set_image(url="attachment://proof.jpg")

        await interaction.response.send_message("\u2705 Your vouch has been submitted. Thank you!", ephemeral=True)

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
    def __init__(self, guild_id: int, order_kind: str = "ranked"):
        super().__init__(timeout=180)
        self.guild_id    = guild_id
        self.order_kind  = order_kind
        self.rating      = None
        self.payment     = None
        self.service_type = None

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

        svc_select = ui.Select(
            placeholder="Was this a Boost or Carry?",
            options=SERVICE_OPTIONS,
            custom_id="vouch_svc", row=2
        )
        svc_select.callback = self._on_svc
        self.add_item(svc_select)

        submit_btn = ui.Button(label="Continue", style=discord.ButtonStyle.success, custom_id="vouch_continue", row=3, emoji="\u2705")
        submit_btn.callback = self._on_submit
        self.add_item(submit_btn)

    async def _on_rating(self, interaction: discord.Interaction):
        self.rating = int(interaction.data["values"][0])
        await interaction.response.defer()

    async def _on_pay(self, interaction: discord.Interaction):
        self.payment = interaction.data["values"][0]
        await interaction.response.defer()

    async def _on_svc(self, interaction: discord.Interaction):
        self.service_type = interaction.data["values"][0]
        await interaction.response.defer()

    async def _on_submit(self, interaction: discord.Interaction):
        missing = []
        if not self.rating:       missing.append("Rating")
        if not self.payment:      missing.append("Payment Method")
        if not self.service_type: missing.append("Boost or Carry")
        if missing:
            await interaction.response.send_message(f"\u274c Please select: **{', '.join(missing)}**", ephemeral=True)
            return
        await interaction.response.send_modal(
            VouchDetailModal(self.rating, self.payment, self.order_kind, self.service_type)
        )


class TicketPanelSetupModal(ui.Modal, title="Configure Ticket Panel"):
    panel_title = ui.TextInput(label="Panel Title", placeholder="\U0001f3ab Support Center", default="\U0001f3ab Support Center", style=discord.TextStyle.short)
    panel_desc  = ui.TextInput(
        label="Panel Description",
        placeholder="Select a category below to open a ticket.",
        default="Select the category that best matches your request.\nOur team will be with you shortly.\n\n\U0001f4cc Tickets are private and handled by staff only.",
        style=discord.TextStyle.long
    )

    async def on_submit(self, interaction: discord.Interaction):
        set_config(interaction.guild.id, ticket_panel_title=self.panel_title.value, ticket_panel_desc=self.panel_desc.value)
        await interaction.response.send_message("\u2705 Ticket panel configuration saved.", ephemeral=True)


# ---------------------------------------------------------------------------
# RANKED BOOST MODAL
# ---------------------------------------------------------------------------
class RankedOrderModal(ui.Modal, title="Ranked Boost Order"):
    notes = ui.TextInput(label="Additional Notes (Optional)", placeholder="Any special requests or information...", required=False, style=discord.TextStyle.long, max_length=500)

    def __init__(self, current_rank: str, desired_rank: str, p11: str, payment: str, service_type: str):
        super().__init__()
        self.current_rank = current_rank
        self.desired_rank = desired_rank
        self.p11          = p11
        self.payment      = payment
        self.service_type = service_type

    async def on_submit(self, interaction: discord.Interaction):
        conn     = get_db()
        c        = conn.cursor()
        order_id = f"RANKED-{uuid.uuid4().hex[:6].upper()}"
        c.execute(
            "INSERT INTO orders (id, user_id, from_tier, to_tier, price, method, order_type, service_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (order_id, interaction.user.id, self.current_rank, self.desired_rank, 0.0,
             self.payment, "ranked", self.service_type)
        )
        conn.commit()
        conn.close()

        guild  = interaction.guild
        member = interaction.user
        cfg    = get_config(guild.id)

        ranked_ticket_ch_id = cfg["ranked_ticket_channel_id"] if cfg else None

        fe        = rank_emoji(self.current_rank)
        te        = rank_emoji(self.desired_rank)
        pay_emoji = _payment_emoji(self.payment, guild.id)
        svc_label = "Carry \U0001f534 (2x price)" if self.service_type == "carry" else "Boost \U0001f7e2"

        welcome = base_embed("\U0001f525 Ranked Boost Ticket", color=PRIMARY)
        welcome.description = (
            f"Welcome, {member.mention}! \U0001f3ae\n\n"
            f"\U0001f4cb **Order:** `{order_id}`\n"
            f"\U0001f4e6 **Order Details:** {fe} `{self.current_rank}` \u2192 {te} `{self.desired_rank}`\n"
            f"\u26a1 **P11 Brawlers:** {P11_EMOJI} {self.p11}\n"
            f"\U0001f6e0 **Service:** {svc_label}\n"
            f"{pay_emoji} **Payment:** {self.payment}\n"
            f"\U0001f550 **Opened:** <t:{int(datetime.utcnow().timestamp())}:F>\n\n"
            "Our staff will contact you shortly to complete your order. "
            "Please have your payment ready!"
        )
        welcome.set_author(name=member.display_name, icon_url=member.display_avatar.url)

        try:
            ticket = await create_ticket_thread(
                guild=guild,
                member=member,
                name=f"ranked-{member.name[:12].lower()}",
                topic_embed=welcome,
                view=TicketCloseView(),
                cfg=cfg,
                override_channel_id=ranked_ticket_ch_id,
            )
        except Exception as ticket_err:
            await interaction.response.send_message(
                f"❌ Failed to create ticket: `{ticket_err}`\n\nAsk an admin to check `/setup` channel permissions.",
                ephemeral=True
            )
            return

        conn = get_db()
        c    = conn.cursor()
        c.execute("UPDATE orders SET ticket_channel_id = ? WHERE id = ?", (ticket.id, order_id))
        conn.commit()
        conn.close()

        order_e = base_embed("\U0001f525 New Ranked Boost Order", color=PRIMARY)
        order_e.set_author(name="BrawlCarry | Staff View", icon_url=guild.icon.url if guild.icon else discord.Embed.Empty)
        order_e.add_field(name="\U0001f464 Customer",      value=member.mention,                                          inline=True)
        order_e.add_field(name="\U0001f4e6 Order Details", value=f"{fe} `{self.current_rank}` \u2192 {te} `{self.desired_rank}`", inline=True)
        order_e.add_field(name="\u26a1 P11",               value=f"{P11_EMOJI} {self.p11}",                               inline=True)
        svc_field_name = "🔴 Carry" if self.service_type == "carry" else "🟢 Boost"
        order_e.add_field(name=svc_field_name,             value=svc_label,                                               inline=True)
        order_e.add_field(name=f"{pay_emoji} Payment",     value=self.payment,                                            inline=True)
        order_e.add_field(name="\U0001f550 Placed",        value=f"<t:{int(datetime.utcnow().timestamp())}:R>",           inline=True)
        order_e.set_footer(text=f"{FOOTER_BRAND} | Press 'Publish to Boosters' to release this order")

        await ticket.send(
            embed=order_e,
            view=OrderActionsView(order_id, ticket_channel_id=ticket.id, order_type="ranked")
        )

        await interaction.response.send_message(
            f"\u2705 Your Ranked Boost order has been placed!\n\U0001f4e9 Ticket opened: {ticket.mention}",
            ephemeral=True
        )


# ---------------------------------------------------------------------------
# PRESTIGE BOOST MODAL
# ---------------------------------------------------------------------------
class PrestigeOrderModal(ui.Modal, title="Prestige Boost Order"):
    notes = ui.TextInput(label="Additional Notes (Optional)", placeholder="Any special requests or information...", required=False, style=discord.TextStyle.long, max_length=500)

    def __init__(self, prestige_spec: str, trophy_range: str, payment: str, service_type: str):
        super().__init__()
        self.prestige_spec = prestige_spec
        self.trophy_range  = trophy_range
        self.payment       = payment
        self.service_type  = service_type

    async def on_submit(self, interaction: discord.Interaction):
        conn     = get_db()
        c        = conn.cursor()
        order_id = f"PREST-{uuid.uuid4().hex[:6].upper()}"
        from_p   = self.prestige_spec.split("->")[0].strip()
        to_p     = self.prestige_spec.split("->")[-1].strip()
        c.execute(
            "INSERT INTO orders (id, user_id, from_tier, to_tier, price, method, order_type, service_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (order_id, interaction.user.id, from_p, to_p, 0.0,
             self.payment, "prestige", self.service_type)
        )
        conn.commit()
        conn.close()

        guild  = interaction.guild
        member = interaction.user
        cfg    = get_config(guild.id)

        prestige_ticket_ch_id = cfg["prestige_ticket_channel_id"] if cfg else None

        pe        = prestige_emoji(self.prestige_spec)
        pay_emoji = _payment_emoji(self.payment, guild.id)
        svc_label = "Carry \U0001f534 (2x price)" if self.service_type == "carry" else "Boost \U0001f7e2"

        welcome = base_embed("\u2728 Prestige Boost Ticket", color=ACCENT)
        welcome.description = (
            f"Welcome, {member.mention}! \u2728\n\n"
            f"\U0001f4cb **Order:** `{order_id}`\n"
            f"{pe} **Prestige:** {self.prestige_spec}\n"
            f"\U0001f3c6 **Current Trophies:** {self.trophy_range}\n"
            f"\U0001f6e0 **Service:** {svc_label}\n"
            f"{pay_emoji} **Payment:** {self.payment}\n"
            f"\U0001f550 **Opened:** <t:{int(datetime.utcnow().timestamp())}:F>\n\n"
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

        conn = get_db()
        c    = conn.cursor()
        c.execute("UPDATE orders SET ticket_channel_id = ? WHERE id = ?", (ticket.id, order_id))
        conn.commit()
        conn.close()

        order_e = base_embed("\u2728 New Prestige Boost Order", color=ACCENT)
        order_e.set_author(name="BrawlCarry | Staff View", icon_url=guild.icon.url if guild.icon else discord.Embed.Empty)
        order_e.add_field(name="\U0001f464 Customer",     value=member.mention,        inline=True)
        order_e.add_field(name=f"{pe} Prestige",          value=self.prestige_spec,    inline=True)
        order_e.add_field(name="\U0001f3c6 Trophies",     value=self.trophy_range,     inline=True)
        svc_field_name2 = "🔴 Carry" if self.service_type == "carry" else "🟢 Boost"
        order_e.add_field(name=svc_field_name2,           value=svc_label,             inline=True)
        order_e.add_field(name=f"{pay_emoji} Payment",    value=self.payment,          inline=True)
        order_e.add_field(name="\U0001f550 Placed",       value=f"<t:{int(datetime.utcnow().timestamp())}:R>", inline=True)
        order_e.set_footer(text=f"{FOOTER_BRAND} | Press 'Publish to Boosters' to release this order")

        await ticket.send(
            embed=order_e,
            view=OrderActionsView(order_id, ticket_channel_id=ticket.id, order_type="prestige")
        )

        await interaction.response.send_message(
            f"\u2705 Your Prestige Boost order has been placed!\n\U0001f4e9 Ticket opened: {ticket.mention}",
            ephemeral=True
        )


# ---------------------------------------------------------------------------
# ORDER COMPLETE MODAL
# ---------------------------------------------------------------------------
class OrderCompleteModal(ui.Modal, title="Complete Order"):
    order_id_input = ui.TextInput(label="Order ID",                   placeholder="RANKED-XXXXXX / CARRY-XXXXXX / PREST-XXXXXX", style=discord.TextStyle.short)
    final_price    = ui.TextInput(label="Final Price Paid (EUR)",      placeholder="44.99",                                        style=discord.TextStyle.short)
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
            await interaction.response.send_message(f"\u274c Order `{order_id}` not found.", ephemeral=True)
            return

        try:
            price_val = float(self.final_price.value.replace("\u20ac", "").strip())
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

        svc_type  = order["service_type"] or "boost"
        ord_type  = order["order_type"] or "ranked"
        svc_label = "Carry \U0001f534" if svc_type == "carry" else "Boost \U0001f7e2"
        pay_emoji = _payment_emoji(self.payment_used.value.strip(), guild_id or 0)

        if ord_type == "prestige":
            pe       = prestige_emoji(f"{order['from_tier']} -> {order['to_tier']}")
            details  = f"{pe} `{order['from_tier']}` \u2192 `{order['to_tier']}`"
        else:
            fe      = rank_emoji(order["from_tier"] or "")
            te      = rank_emoji(order["to_tier"] or "")
            details = f"{fe} `{order['from_tier']}` \u2192 {te} `{order['to_tier']}`"

        conn.close()
        img = self.image_url.value.strip() if self.image_url.value else None

        e = base_embed("\u2705 Order Completed", color=SUCCESS)
        e.set_author(name="BrawlCarry | Order Completed", icon_url=interaction.user.display_avatar.url)
        e.add_field(name="\U0001f194 Order ID",     value=f"`{order_id}`",                                              inline=True)
        e.add_field(name="\U0001f464 Customer",     value=customer.mention if customer else f"<@{order['user_id']}>",   inline=True)
        e.add_field(name="\U0001f4b6 Amount Paid",  value=f"**\u20ac{price_val:.2f}**",                                 inline=True)
        e.add_field(name=f"{pay_emoji} Payment",    value=f"**{self.payment_used.value.strip()}**",                     inline=True)
        e.add_field(name="\U0001f4e6 Order Details",value=details,                                                       inline=True)
        e.add_field(name="\U0001f6e0 Service",      value=svc_label,                                                    inline=True)
        e.add_field(name="\u2705 Completed By",     value=interaction.user.mention,                                     inline=True)
        e.add_field(name="\U0001f550 Completed At", value=f"<t:{int(now.timestamp())}:F>",                              inline=False)
        if self.notes.value:
            e.add_field(name="\U0001f4dd Notes", value=self.notes.value, inline=False)

        wm_file = None
        if img:
            wm_file = await fetch_and_watermark(img)
            if wm_file:
                e.set_image(url="attachment://proof.jpg")

        await interaction.response.send_message("\u2705 Order marked as completed!", ephemeral=True)

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
            await interaction.followup.send("\u26a0\ufe0f No completed-orders channel configured. Use `/setup` to set one.", ephemeral=True)

        if customer:
            try:
                dm_e = base_embed("\u2705 Your Order is Complete!", color=SUCCESS)
                dm_e.description = (
                    f"Great news! Your order **`{order_id}`** has been completed.\n\n"
                    f"\U0001f4e6 **Order Details:** {details}\n"
                    f"\U0001f4b6 **Amount:** \u20ac{price_val:.2f}\n"
                    f"{pay_emoji} **Payment:** {self.payment_used.value.strip()}\n\n"
                    "Thank you for choosing BrawlCarry! Consider leaving a vouch \u2b50"
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
        self.service_type = None

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

        svc_select = ui.Select(
            placeholder="Boost or Carry?",
            options=SERVICE_OPTIONS,
            custom_id="ranked_svc", row=3
        )
        svc_select.callback = self._on_svc
        self.add_item(svc_select)

        # Row 4: payment + submit/cancel
        methods   = get_payment_methods(guild_id)
        pay_select = ui.Select(
            placeholder="Select payment method...",
            options=[discord.SelectOption(label=lbl, value=lbl, emoji=emo) for lbl, emo in methods],
            custom_id="ranked_pay", row=4
        )
        pay_select.callback = self._on_pay
        self.add_item(pay_select)

        # NOTE: Discord limits 5 rows (0-4). Submit/cancel added as additional
        # buttons would require row 5 which is not allowed.
        # We attach them as extra callbacks on row 4 using a second Select approach.
        # Instead, we present submit/cancel inline via a second message or handle
        # them through a final confirm modal on row 4 button (workaround: use a
        # "Confirm Order" button that fires the modal after all selections are done).
        # Since we have 5 rows of selects we use a separate confirm button view.
        # Actually we need to drop to using the modal flow directly from the last select.
        # Best approach: replace submit+cancel buttons with row-based approach below.
        # We will attach confirm as part of the last select's callback by opening modal.
        # Override: move payment to row 3, svc to row 4, add submit button on row 4.
        # Re-do the layout:

        # Clear and rebuild with correct layout
        self.clear_items()
        self.current_rank = None
        self.desired_rank = None
        self.p11          = None
        self.payment      = None
        self.service_type = None

        current_select2 = ui.Select(placeholder="Your current rank...", options=current_options, custom_id="ranked_current2", row=0)
        current_select2.callback = self._on_current
        self.add_item(current_select2)

        desired_select2 = ui.Select(placeholder="Your desired rank...", options=desired_options, custom_id="ranked_desired2", row=1)
        desired_select2.callback = self._on_desired
        self.add_item(desired_select2)

        p11_select2 = ui.Select(
            placeholder="Number of Power 11 brawlers...",
            options=[discord.SelectOption(label=n, value=n, emoji=P11_EMOJI) for n in P11_OPTIONS],
            custom_id="ranked_p112", row=2
        )
        p11_select2.callback = self._on_p11
        self.add_item(p11_select2)

        methods = get_payment_methods(guild_id)
        pay_select2 = ui.Select(
            placeholder="Payment method...",
            options=[discord.SelectOption(label=lbl, value=lbl, emoji=emo) for lbl, emo in methods],
            custom_id="ranked_pay2", row=3
        )
        pay_select2.callback = self._on_pay
        self.add_item(pay_select2)

        svc_select2 = ui.Select(
            placeholder="Boost or Carry? (Carry = 2x price)",
            options=SERVICE_OPTIONS,
            custom_id="ranked_svc2", row=4
        )
        svc_select2.callback = self._on_svc_submit
        self.add_item(svc_select2)

    async def _on_current(self, interaction): self.current_rank = interaction.data["values"][0]; await interaction.response.defer()
    async def _on_desired(self, interaction): self.desired_rank = interaction.data["values"][0]; await interaction.response.defer()
    async def _on_p11(self, interaction):     self.p11          = interaction.data["values"][0]; await interaction.response.defer()
    async def _on_pay(self, interaction):     self.payment      = interaction.data["values"][0]; await interaction.response.defer()

    async def _on_svc(self, interaction):
        self.service_type = interaction.data["values"][0]
        await interaction.response.defer()

    async def _on_svc_submit(self, interaction: discord.Interaction):
        self.service_type = interaction.data["values"][0]
        missing = []
        if not self.current_rank: missing.append("Current Rank")
        if not self.desired_rank: missing.append("Desired Rank")
        if not self.p11:          missing.append("Power 11 Brawlers")
        if not self.payment:      missing.append("Payment Method")
        if missing:
            await interaction.response.send_message(f"\u274c Please fill in: **{', '.join(missing)}**", ephemeral=True)
            return
        await interaction.response.send_modal(
            RankedOrderModal(self.current_rank, self.desired_rank, self.p11, self.payment, self.service_type)
        )


# ---------------------------------------------------------------------------
# PRESTIGE BOOST SELECT-MENU VIEW
# ---------------------------------------------------------------------------
class PrestigeOrderView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.prestige_spec = None
        self.trophy_range  = None
        self.payment       = None
        self.service_type  = None

        pres_options = []
        for p in PRESTIGE_OPTIONS:
            emo = prestige_emoji(p)
            opt = discord.SelectOption(label=p, value=p)
            if "REPLACE_WITH" not in emo:
                opt.emoji = emo
            pres_options.append(opt)

        pres_select = ui.Select(
            placeholder="Select prestige spec...",
            options=pres_options,
            custom_id="prest_spec2", row=0
        )
        pres_select.callback = self._on_spec
        self.add_item(pres_select)

        trophy_select = ui.Select(
            placeholder="Current trophy count on that brawler...",
            options=[discord.SelectOption(label=t, value=t, emoji="\U0001f3c6") for t in TROPHY_OPTIONS],
            custom_id="prest_trophy", row=1
        )
        trophy_select.callback = self._on_trophy
        self.add_item(trophy_select)

        methods = get_payment_methods(guild_id)
        pay_select = ui.Select(
            placeholder="Payment method...",
            options=[discord.SelectOption(label=lbl, value=lbl, emoji=emo) for lbl, emo in methods],
            custom_id="prest_pay2", row=2
        )
        pay_select.callback = self._on_pay
        self.add_item(pay_select)

        svc_select = ui.Select(
            placeholder="Boost or Carry? (Carry = 2x price)",
            options=SERVICE_OPTIONS,
            custom_id="prest_svc", row=3
        )
        svc_select.callback = self._on_svc_submit
        self.add_item(svc_select)

async def _on_spec(self, interaction):   self.prestige_spec = interaction.data["values"][0]; await interaction.response.defer()
    async def _on_trophy(self, interaction): self.trophy_range  = interaction.data["values"][0]; await interaction.response.defer()
    async def _on_pay(self, interaction):    self.payment       = interaction.data["values"][0]; await interaction.response.defer()

    async def _on_svc_submit(self, interaction: discord.Interaction):
        self.service_type = interaction.data["values"][0]
        missing = []
        if not self.prestige_spec: missing.append("Prestige Spec")
        if not self.trophy_range:  missing.append("Current Trophies")
        if not self.payment:       missing.append("Payment Method")
        if missing:
            await interaction.response.send_message(f"\u274c Please fill in: **{', '.join(missing)}**", ephemeral=True)
            return
        await interaction.response.send_modal(
            PrestigeOrderModal(self.prestige_spec, self.trophy_range, self.payment, self.service_type)
        )


# ---------------------------------------------------------------------------
# APPLICATION SYSTEM
# ---------------------------------------------------------------------------
APPLICATION_ROLES = ["Booster", "Admin", "Reporter"]

class ApplicationModal(ui.Modal):
    why    = ui.TextInput(label="Why do you want this role?",       style=discord.TextStyle.long,  max_length=500)
    exp    = ui.TextInput(label="Relevant experience",               style=discord.TextStyle.long,  max_length=500)
    age    = ui.TextInput(label="Your age",                          style=discord.TextStyle.short, max_length=3)
    extra  = ui.TextInput(label="Anything else to add? (Optional)",  style=discord.TextStyle.long,  max_length=300, required=False)

    def __init__(self, role: str):
        super().__init__(title=f"{role} Application")
        self.role = role

    async def on_submit(self, interaction: discord.Interaction):
        guild  = interaction.guild
        member = interaction.user
        cfg    = get_config(guild.id)

        review_ch_id = cfg["application_review_channel_id"] if cfg else None
        review_ch    = guild.get_channel(review_ch_id) if review_ch_id else None

        if not review_ch:
            await interaction.response.send_message(
                "❌ Application review channel not configured. Ask an admin to run `/setup`.", ephemeral=True
            )
            return

        e = base_embed(f"📝 New {self.role} Application", color=PRIMARY)
        e.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        e.add_field(name="👤 Applicant",    value=member.mention,     inline=True)
        e.add_field(name="🆔 User ID",      value=f"`{member.id}`",   inline=True)
        e.add_field(name="🎭 Role Applied", value=f"**{self.role}**", inline=True)
        e.add_field(name="❓ Why This Role",  value=self.why.value,  inline=False)
        e.add_field(name="📋 Experience",     value=self.exp.value,  inline=False)
        e.add_field(name="🎂 Age",            value=self.age.value,  inline=True)
        if self.extra.value:
            e.add_field(name="💬 Extra Info", value=self.extra.value, inline=False)
        e.set_footer(text=f"{FOOTER_BRAND} | Use buttons below to accept or reject")

        await review_ch.send(embed=e, view=ApplicationReviewView(member.id, self.role))
        await interaction.response.send_message(
            f"✅ Your **{self.role}** application has been submitted! Staff will review it shortly.", ephemeral=True
        )


class ApplicationReviewView(ui.View):
    def __init__(self, applicant_id: int, role: str):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
        self.role         = role

    @ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="✅", custom_id="app_accept_v1")
    async def accept(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("❌ You don't have permission to review applications.", ephemeral=True)
            return
        member = interaction.guild.get_member(self.applicant_id)
        result_text = ""
        if member:
            role_obj = discord.utils.get(interaction.guild.roles, name=self.role)
            if role_obj:
                try:
                    await member.add_roles(role_obj, reason=f"Application accepted by {interaction.user}")
                    result_text = f" Role **{self.role}** has been assigned."
                except discord.Forbidden:
                    result_text = f" ⚠️ Could not assign role (missing permissions)."
            else:
                result_text = f" ⚠️ Role **{self.role}** not found in server — create it manually."
            try:
                dm_e = base_embed("✅ Application Accepted!", color=SUCCESS)
                dm_e.description = (
                    f"Congratulations! Your **{self.role}** application in **{interaction.guild.name}** has been accepted.\n\n"
                    "Welcome to the team! 🎉"
                )
                await member.send(embed=dm_e)
            except discord.Forbidden:
                pass

        for item in self.children:
            item.disabled = True
        orig = interaction.message.embeds[0] if interaction.message.embeds else None
        if orig:
            orig.color = SUCCESS
            orig.title = "✅ ACCEPTED — " + (orig.title or "")
            orig.add_field(name="✅ Reviewed By", value=interaction.user.mention, inline=True)
        await interaction.message.edit(embed=orig, view=self)
        await interaction.response.send_message(f"✅ Application accepted.{result_text}", ephemeral=True)

    @ui.button(label="Reject", style=discord.ButtonStyle.danger, emoji="❌", custom_id="app_reject_v1")
    async def reject(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("❌ You don't have permission to review applications.", ephemeral=True)
            return
        member = interaction.guild.get_member(self.applicant_id)
        if member:
            try:
                dm_e = base_embed("❌ Application Rejected", color=DANGER)
                dm_e.description = (
                    f"Unfortunately, your **{self.role}** application in **{interaction.guild.name}** has been rejected.\n\n"
                    "You may re-apply in the future. Thank you for your interest."
                )
                await member.send(embed=dm_e)
            except discord.Forbidden:
                pass

        for item in self.children:
            item.disabled = True
        orig = interaction.message.embeds[0] if interaction.message.embeds else None
        if orig:
            orig.color = DANGER
            orig.title = "❌ REJECTED — " + (orig.title or "")
            orig.add_field(name="❌ Reviewed By", value=interaction.user.mention, inline=True)
        await interaction.message.edit(embed=orig, view=self)
        await interaction.response.send_message("❌ Application rejected and applicant notified.", ephemeral=True)


class ApplicationPanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for role in APPLICATION_ROLES:
            btn = ui.Button(
                label=f"Apply for {role}",
                style=discord.ButtonStyle.primary,
                emoji="📝",
                custom_id=f"app_btn_{role.lower()}_v1"
            )
            btn.callback = self._make_callback(role)
            self.add_item(btn)

    def _make_callback(self, role: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.send_modal(ApplicationModal(role))
        return callback

# ---------------------------------------------------------------------------
# PANEL BUTTON VIEWS  (persistent)
# ---------------------------------------------------------------------------
class RankedPanelButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Ranked Boost Order", style=discord.ButtonStyle.danger, emoji="\U0001f525", custom_id="ranked_panel_btn_v1")
    async def open_ranked(self, interaction: discord.Interaction, button: ui.Button):
        e = base_embed("\U0001f525 Ranked Boost Order", color=PRIMARY)
        e.description = (
            "Select your ranks, Power 11 count, payment method and service type, then the order form will open automatically.\n\n"
            "> \U0001f7e2 **Boost** — we play on your account (standard price)\n"
            "> \U0001f534 **Carry** — we play alongside you (2x price)\n\n"
            "\u26a0\ufe0f Do not share passwords or sensitive information."
        )
        e.add_field(name="\U0001f3c6 Rank Emojis",
                    value=" ".join(v for v in RANK_EMOJI.values()), inline=False)
        await interaction.response.send_message(embed=e, view=RankedOrderView(interaction.guild_id), ephemeral=True)


class PrestigePanelButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Prestige Boost Order", style=discord.ButtonStyle.primary, emoji="\u2728", custom_id="prestige_panel_btn_v1")
    async def open_prestige(self, interaction: discord.Interaction, button: ui.Button):
        e = base_embed("\u2728 Prestige Boost Order", color=ACCENT)
        e.description = (
            "Select your prestige spec, current trophies, payment method and service type, then the order form will open automatically.\n\n"
            "> \U0001f7e2 **Boost** — we play on your account (standard price)\n"
            "> \U0001f534 **Carry** — we play alongside you (2x price)\n\n"
            "\u26a0\ufe0f Do not share passwords or sensitive information."
        )
        pres_icons = " ".join(PRESTIGE_EMOJI.values())
        e.add_field(name="\u2728 Prestige Icons", value=pres_icons, inline=False)
        await interaction.response.send_message(embed=e, view=PrestigeOrderView(interaction.guild_id), ephemeral=True)


# ---------------------------------------------------------------------------
# OTHER PERSISTENT VIEWS
# ---------------------------------------------------------------------------
class OrderButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Place Order", style=discord.ButtonStyle.primary, emoji="\U0001f3ae", custom_id="order_btn_v2")
    async def order(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(OrderModal())


class VouchButtonView(ui.View):
    def __init__(self, order_kind: str = "ranked"):
        super().__init__(timeout=None)
        self.order_kind = order_kind

    @ui.button(label="Submit a Vouch", style=discord.ButtonStyle.success, emoji="\u2b50", custom_id="vouch_btn_v2")
    async def vouch(self, interaction: discord.Interaction, button: ui.Button):
        guild_id = interaction.guild.id if interaction.guild else 0
        e = base_embed("\u2b50 Submit Your Vouch", color=GOLD)
        e.description = (
            "Select your **rating**, **payment method** and **service type**, then click **Continue** "
            "to fill in your feedback and proof.\n\nThank you for taking the time to vouch!"
        )
        await interaction.response.send_message(embed=e, view=VouchSelectorView(guild_id, order_kind=self.order_kind), ephemeral=True)


class GiveawayView(ui.View):
    def __init__(self, giveaway_id: str):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @ui.button(label="Enter Giveaway", style=discord.ButtonStyle.success, emoji="\U0001f389", custom_id="ga_enter_v2")
    async def enter(self, interaction: discord.Interaction, button: ui.Button):
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM giveaways WHERE id = ?", (self.giveaway_id,))
        ga = c.fetchone()
        if not ga:
            await interaction.response.send_message("\u274c Giveaway not found.", ephemeral=True)
            conn.close()
            return
        participants = json.loads(ga["participants"]) if ga["participants"] else []
        if interaction.user.id in participants:
            await interaction.response.send_message("\u274c You have already entered this giveaway.", ephemeral=True)
        else:
            participants.append(interaction.user.id)
            # Bonus role = extra entry
            bonus_role_id = ga["bonus_role_id"] if "bonus_role_id" in ga.keys() else None
            bonus_msg = ""
            if bonus_role_id:
                member_roles = [r.id for r in interaction.user.roles]
                if bonus_role_id in member_roles:
                    participants.append(interaction.user.id)
                    bonus_msg = " You have a bonus role, so you got **2 entries**! 🎉"
            c.execute("UPDATE giveaways SET participants = ? WHERE id = ?", (json.dumps(participants), self.giveaway_id))
            conn.commit()
            await interaction.response.send_message(f"✅ You've entered! Good luck 🍀{bonus_msg}", ephemeral=True)
        conn.close()

    @ui.button(label="Participants", style=discord.ButtonStyle.blurple, emoji="\U0001f465", custom_id="ga_view_v2")
    async def view_participants(self, interaction: discord.Interaction, button: ui.Button):
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT participants FROM giveaways WHERE id = ?", (self.giveaway_id,))
        ga = c.fetchone()
        conn.close()
        count = len(json.loads(ga["participants"])) if ga and ga["participants"] else 0
        e = base_embed("\U0001f465 Giveaway Participants", color=PRIMARY)
        e.description = f"**{count:,}** participant{'s' if count != 1 else ''} have entered."
        await interaction.response.send_message(embed=e, ephemeral=True)

    @ui.button(label="Extra Entries", style=discord.ButtonStyle.secondary, emoji="\U0001f381", custom_id="ga_extra_v2")
    async def extra(self, interaction: discord.Interaction, button: ui.Button):
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT extra_entries FROM giveaways WHERE id = ?", (self.giveaway_id,))
        ga = c.fetchone()
        conn.close()
        extra = ga["extra_entries"] if ga and ga["extra_entries"] else None
        e = base_embed("\U0001f381 Extra Entry Methods", color=ACCENT)
        e.description = extra if extra else "No extra entry methods configured."
        await interaction.response.send_message(embed=e, ephemeral=True)


# ---------------------------------------------------------------------------
# TICKET VIEWS  (General Support only)
# ---------------------------------------------------------------------------
class TicketView(ui.View):
    """Single-button ticket panel -- General Support only."""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="General Support", style=discord.ButtonStyle.primary, emoji="\u2139\ufe0f", custom_id="ticket_general_btn_v1")
    async def open_support(self, interaction: discord.Interaction, button: ui.Button):
        guild  = interaction.guild
        member = interaction.user
        cfg    = get_config(guild.id)

        e = base_embed("\u2139\ufe0f General Support", color=SUCCESS)
        e.description = (
            f"Welcome, {member.mention}!\n\n"
            f"\U0001f4cb **Category:** General Support\n"
            f"\U0001f550 **Opened:** <t:{int(datetime.utcnow().timestamp())}:F>\n\n"
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
        await interaction.response.send_message(f"\u2705 Support ticket created: {ticket.mention}", ephemeral=True)


class TicketCloseView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="\U0001f512", custom_id="ticket_close_v2")
async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        e = base_embed("🔒 Closing Ticket", color=DANGER)
        e.description = "This ticket will be closed in **5 seconds**. Generating transcript..."
        await interaction.response.send_message(embed=e)

        channel = interaction.channel
        guild   = interaction.guild

        transcript_lines = []
        try:
            async for msg in channel.history(limit=500, oldest_first=True):
                ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                attachments = " | ".join(a.url for a in msg.attachments) if msg.attachments else ""
                line = f"[{ts}] {msg.author.display_name} ({msg.author.id}): {msg.content}"
                if attachments:
                    line += f"  [Attachments: {attachments}]"
                transcript_lines.append(line)
        except Exception as ex:
            transcript_lines.append(f"[ERROR fetching transcript: {ex}]")

        transcript_text = "\n".join(transcript_lines)
        transcript_file = discord.File(
            io.BytesIO(transcript_text.encode("utf-8")),
            filename=f"transcript-{channel.name}.txt"
        )

        conn = get_db()
        c    = conn.cursor()
        c.execute("SELECT * FROM orders WHERE ticket_channel_id = ? ORDER BY created_at DESC LIMIT 1", (channel.id,))
        order = c.fetchone()
        conn.close()

        cfg       = get_config(guild.id) if guild else None
        log_ch_id = cfg["ticket_log_channel_id"] if cfg else None
        log_ch    = guild.get_channel(log_ch_id) if (guild and log_ch_id) else None

        if log_ch:
            log_e = base_embed("📋 Ticket Closed", color=PRIMARY)
            log_e.add_field(name="📁 Channel",   value=channel.name,             inline=True)
            log_e.add_field(name="🔒 Closed By", value=interaction.user.mention, inline=True)
            log_e.add_field(name="⏰ Closed At", value=f"<t:{int(datetime.utcnow().timestamp())}:F>", inline=False)

            if order:
                booster_mention  = f"<@{order['booster_id']}>" if order["booster_id"] else "Unassigned"
                customer_mention = f"<@{order['user_id']}>"    if order["user_id"]    else "Unknown"
                if order["order_type"] == "prestige":
                    pe      = prestige_emoji(f"{order['from_tier']} -> {order['to_tier']}")
                    details = f"{pe} `{order['from_tier']}` → `{order['to_tier']}`"
                else:
                    fe      = rank_emoji(order["from_tier"] or "")
                    te      = rank_emoji(order["to_tier"]   or "")
                    details = f"{fe} `{order['from_tier']}` → {te} `{order['to_tier']}`"

                log_e.add_field(name="🧾 Order ID",     value=f"`{order['id']}`", inline=True)
                log_e.add_field(name="👤 Customer",      value=customer_mention,  inline=True)
                log_e.add_field(name="🟠 Booster",       value=booster_mention,   inline=True)
                log_e.add_field(name="📦 Order Details", value=details,           inline=True)
                log_e.add_field(name="🔖 Status",        value=order["status"],   inline=True)

            await log_ch.send(embed=log_e, file=transcript_file)

        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket closed by {interaction.user}")
        except Exception:
            pass

    @ui.button(label="Send Vouch Panel", style=discord.ButtonStyle.success, emoji="\u2b50", custom_id="ticket_send_vouch_v2")
    async def send_vouch(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("\u274c Staff only.", ephemeral=True)
            return
        # Try to infer order kind from channel name
        ch_name    = getattr(interaction.channel, "name", "") or ""
        order_kind = "prestige" if "prestige" in ch_name else "ranked"

        e = base_embed("\u2b50 Leave a Vouch", color=GOLD)
        e.description = (
            "Thank you for your order! We'd love your feedback.\n\n"
            "\U0001f4f8 Attach a screenshot as proof\n"
            "\u2b50 Rate your experience (1-5)\n"
            "\U0001f4ac Leave honest feedback\n\n"
            "Click the button below to submit."
        )
        await interaction.channel.send(embed=e, view=VouchButtonView(order_kind=order_kind))
        await interaction.response.send_message("\u2705 Vouch panel sent.", ephemeral=True)


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
    owner="The server owner/admin who manages the bot",
    ticket_log_channel="Channel where closed ticket logs and transcripts will be sent",
    application_channel="Channel where application panels are posted",
    application_review_channel="Channel where staff review submitted applications",
    account_sale_channel="Channel where account sale posts are published",
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
    ticket_log_channel: discord.TextChannel = None,
    application_channel: discord.TextChannel = None,
    application_review_channel: discord.TextChannel = None,
    account_sale_channel: discord.TextChannel = None,
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
    if ticket_log_channel:       updates["ticket_log_channel_id"]       = ticket_log_channel.id
    if application_channel:        updates["application_channel_id"]        = application_channel.id
    if application_review_channel: updates["application_review_channel_id"] = application_review_channel.id
    if account_sale_channel:       updates["account_sale_channel_id"]       = account_sale_channel.id
    if updates:
        set_config(interaction.guild.id, **updates)

    e = base_embed("\u2699\ufe0f Server Configuration", color=SUCCESS)
    e.description = "Bot settings updated successfully."
    if vouch_channel:           e.add_field(name="\u2b50 Vouch Channel",              value=vouch_channel.mention,           inline=True)
    if ticket_channel:          e.add_field(name="\U0001f3ab Fallback Ticket Channel",value=ticket_channel.mention,          inline=True)
    if ticket_category:         e.add_field(name="\U0001f4c2 Ticket Category",        value=ticket_category.mention,         inline=True)
    if completed_channel:       e.add_field(name="\u2705 Completed Channel",          value=completed_channel.mention,       inline=True)
    if ranked_ticket_channel:   e.add_field(name="\U0001f525 Ranked Ticket Channel",  value=ranked_ticket_channel.mention,   inline=True)
    if prestige_ticket_channel: e.add_field(name="\u2728 Prestige Ticket Channel",   value=prestige_ticket_channel.mention, inline=True)
    if ranked_panel_channel:    e.add_field(name="\U0001f4e2 Ranked Claiming Channel",  value=ranked_panel_channel.mention,    inline=True)
    if prestige_panel_channel:  e.add_field(name="\U0001f4e2 Prestige Claiming Channel",value=prestige_panel_channel.mention,  inline=True)
    if owner:                   e.add_field(name="\U0001f451 Owner",                  value=owner.mention,                   inline=True)
    if ticket_log_channel:      e.add_field(name="📋 Ticket Log Channel", value=ticket_log_channel.mention, inline=True)
    if application_channel:        e.add_field(name="📝 Application Channel",        value=application_channel.mention,        inline=True)
    if application_review_channel: e.add_field(name="🔍 Application Review Channel", value=application_review_channel.mention, inline=True)
    if account_sale_channel:       e.add_field(name="🛒 Account Sale Channel",        value=account_sale_channel.mention,       inline=True)

    e.add_field(
        name="\u2139\ufe0f Order Flow",
        value=(
            "1\ufe0f\u20e3 Customer clicks **Ranked/Prestige Boost** button \u2192 ticket opens in the dedicated channel\n"
            "2\ufe0f\u20e3 An order card appears inside the ticket\n"
            "3\ufe0f\u20e3 Staff click **\U0001f4e2 Publish to Boosters** \u2192 set earnings \u2192 card appears in the claiming channel\n"
            "4\ufe0f\u20e3 A booster clicks **\U0001f7e0 Claim This Boost** \u2192 immediately added to the customer's ticket"
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
async def add_payment_method_cmd(interaction: discord.Interaction, label: str, emoji: str = "\U0001f4b3"):
    success = add_payment_method(interaction.guild.id, label.strip(), emoji.strip())
    if success:
        e = base_embed("\u2705 Payment Method Added", color=SUCCESS)
        e.description = f"{emoji} **{label}** has been added to the payment options."
    else:
        e = base_embed("\u26a0\ufe0f Already Exists", color=GOLD)
        e.description = f"**{label}** is already a configured payment method."
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="remove_payment_method", description="Remove a payment method from the order forms")
@app_commands.describe(label="Exact name of the payment method to remove")
@app_commands.checks.has_permissions(manage_channels=True)
async def remove_payment_method_cmd(interaction: discord.Interaction, label: str):
    success = remove_payment_method(interaction.guild.id, label.strip())
    if success:
        e = base_embed("\u2705 Payment Method Removed", color=SUCCESS)
        e.description = f"**{label}** has been removed from the payment options."
    else:
        e = base_embed("\u274c Not Found", color=DANGER)
        e.description = f"**{label}** was not found in the configured payment methods."
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="list_payment_methods", description="View all configured payment methods")
@app_commands.checks.has_permissions(manage_channels=True)
async def list_payment_methods(interaction: discord.Interaction):
    methods = get_payment_methods(interaction.guild.id)
    e = base_embed("\U0001f4b3 Payment Methods", color=PRIMARY)
    e.description = "\n".join(f"{emo} **{lbl}**" for lbl, emo in methods) if methods else "No payment methods configured."
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="order_panel", description="Post the generic order creation panel in this channel")
@app_commands.describe(image_url="Optional banner image URL")
@app_commands.checks.has_permissions(manage_channels=True)
async def order_panel(interaction: discord.Interaction, image_url: str = None):
    e = base_embed("\U0001f3ae Brawl Stars Boost Orders", color=PRIMARY)
    e.description = (
        "Ready to rank up? Click the button below to place your carry order.\n\n"
        "**What we offer:**\n"
        "\U0001f947 Brawl Stars Ranked Boosting\n"
        "\u26a1 Fast & reliable completion\n"
        "\u2b50 5-star rated service\n"
        "\U0001f512 Secure & confidential"
    )
    if image_url:
        e.set_image(url=image_url)
    await interaction.channel.send(embed=e, view=OrderButton())
    await interaction.response.send_message("\u2705 Order panel posted.", ephemeral=True)


@bot.tree.command(name="ranked_panel", description="Post the Ranked Boost order panel in this channel")
@app_commands.describe(image_url="Image URLs separated by commas (e.g. url1,url2,url3)")
@app_commands.checks.has_permissions(manage_channels=True)
async def ranked_panel(interaction: discord.Interaction, image_url: str = None):
    rank_icons = " ".join(RANK_EMOJI.values())
    e = base_embed("\U0001f525 Ranked Boost", color=PRIMARY)
    e.description = (
        "Unlock your prestige! Click the button below to place your **Prestige Boost** order.\n\n"
        f"{pres_icons}\n\n"
        "**Pricing** *(depends on brawler & power level)*\n"
        f"{PRESTIGE_EMOJI['Prestige 0 -> Prestige 1']} Prestige 0 → 1 — from **{PRESTIGE_PRICES['Prestige 0 -> Prestige 1']}€**\n"
        f"{PRESTIGE_EMOJI['Prestige 1 -> Prestige 2']} Prestige 1 → 2 — from **{PRESTIGE_PRICES['Prestige 1 -> Prestige 2']}€**\n"
        f"{PRESTIGE_EMOJI['Prestige 2 -> Prestige 3']} Prestige 2 → 3 — from **{PRESTIGE_PRICES['Prestige 2 -> Prestige 3']}€**\n\n"
        "> 🟢 **Boost** — we play on your account\n"
        "> 🔴 **Carry** — we play alongside you (2x price)\n\n"
        "⚡ Fast & reliable | 🔒 Secure | ⭐ 5-star rated"
    )
    image_urls = [u.strip() for u in image_url.split(",")] if image_url else []
    if image_urls:
        e.set_image(url=image_urls[0])

    extra_embeds = []
    for extra_url in image_urls[1:]:
        img_e = discord.Embed(color=PRIMARY)
        img_e.set_image(url=extra_url)
        img_e.set_footer(text=FOOTER_BRAND)
        extra_embeds.append(img_e)

    all_embeds = [e] + extra_embeds
    await interaction.channel.send(embeds=all_embeds, view=RankedPanelButton())
    await interaction.response.send_message("✅ Ranked Boost panel posted.", ephemeral=True)


@bot.tree.command(name="prestige_panel", description="Post the Prestige Boost order panel in this channel")
@app_commands.describe(image_url="Image URLs separated by commas (e.g. url1,url2,url3)")
@app_commands.checks.has_permissions(manage_channels=True)
async def prestige_panel(interaction: discord.Interaction, image_url: str = None):
    pres_icons = " ".join(PRESTIGE_EMOJI.values())
    e = base_embed("\u2728 Prestige Boost", color=ACCENT)
    e.description = (
        "Unlock your prestige! Click the button below to place your **Prestige Boost** order.\n\n"
        f"{pres_icons}\n\n"
    e.description = (
        "Unlock your prestige! Click the button below to place your **Prestige Boost** order.\n\n"
        f"{pres_icons}\n\n"
        "**Pricing** *(depends on brawler & power level)*\n"
        f"{PRESTIGE_EMOJI['Prestige 0 -> Prestige 1']} Prestige 0 → 1 — from **{PRESTIGE_PRICES['Prestige 0 -> Prestige 1']}€**\n"
        f"{PRESTIGE_EMOJI['Prestige 1 -> Prestige 2']} Prestige 1 → 2 — from **{PRESTIGE_PRICES['Prestige 1 -> Prestige 2']}€**\n"
        f"{PRESTIGE_EMOJI['Prestige 2 -> Prestige 3']} Prestige 2 → 3 — from **{PRESTIGE_PRICES['Prestige 2 -> Prestige 3']}€**\n\n"
        "> 🟢 **Boost** — we play on your account\n"
        "> 🔴 **Carry** — we play alongside you (2x price)\n\n"
        "⚡ Fast & reliable | 🔒 Secure | ⭐ 5-star rated"
    )
image_urls = [u.strip() for u in image_url.split(",")] if image_url else []
    if image_urls:
        e.set_image(url=image_urls[0])

    extra_embeds = []
    for extra_url in image_urls[1:]:
        img_e = discord.Embed(color=ACCENT)
        img_e.set_image(url=extra_url)
        img_e.set_footer(text=FOOTER_BRAND)
        extra_embeds.append(img_e)

    all_embeds = [e] + extra_embeds
    await interaction.channel.send(embeds=all_embeds, view=PrestigePanelButton())
    await interaction.response.send_message("✅ Prestige Boost panel posted.", ephemeral=True)

@bot.tree.command(name="ticket_panel", description="Post the support ticket panel in this channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def ticket_panel(interaction: discord.Interaction):
    cfg   = get_config(interaction.guild.id)
    title = cfg["ticket_panel_title"] if cfg and cfg["ticket_panel_title"] else "\U0001f3ab Support Center"
    desc  = (cfg["ticket_panel_desc"] if cfg and cfg["ticket_panel_desc"]
             else "Need help? Click the button below to open a support ticket.\nOur team will be with you shortly.\n\n\U0001f4cc Tickets are private and handled by staff only.")
    e = discord.Embed(title=title, color=PRIMARY, description=desc)
    e.set_footer(text=FOOTER_BRAND)
    e.timestamp = datetime.utcnow()
    await interaction.channel.send(embed=e, view=TicketView())
    await interaction.response.send_message("\u2705 Ticket panel posted.", ephemeral=True)


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
@app_commands.describe(user="DM the vouch panel to this user", order_kind="ranked or prestige (default: ranked)")
@app_commands.checks.has_permissions(manage_channels=True)
async def vouch_panel(interaction: discord.Interaction, user: discord.User = None, order_kind: str = "ranked"):
    ok = order_kind.lower() if order_kind.lower() in ("ranked", "prestige") else "ranked"
    e = base_embed("\u2b50 Leave a Vouch", color=GOLD)
    e.description = (
        "Thank you for your order! We'd love your feedback.\n\n"
        "\U0001f4f8 Attach a screenshot as proof\n"
        "\u2b50 Rate your experience (1-5)\n"
        "\U0001f4ac Leave honest feedback\n\n"
        "Click the button below to submit."
    )
    view = VouchButtonView(order_kind=ok)
    if user:
        try:
            await user.send(embed=e, view=view)
            await interaction.response.send_message(f"\u2705 Vouch panel sent to {user.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("\u274c Could not DM that user. They may have DMs disabled.", ephemeral=True)
    else:
        await interaction.channel.send(embed=e, view=view)
        await interaction.response.send_message("\u2705 Vouch panel posted.", ephemeral=True)


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
    extra_entries: str = None, ping: str = "@everyone", image_url: str = None,
    bonus_role: discord.Role = None,
):
    conn    = get_db()
    c       = conn.cursor()
    ga_id   = f"G{uuid.uuid4().hex[:8].upper()}"
    ends_at = datetime.utcnow() + timedelta(hours=hours)
    c.execute(
        "INSERT INTO giveaways (id, prize, desc, winners, hosted_by, participants, image_url, extra_entries, ping, ended_at, bonus_role_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ga_id, prize, description, winners, interaction.user.id, "[]", image_url, extra_entries, ping, ends_at,
         bonus_role.id if bonus_role else None)
    )
    conn.commit()
    conn.close()

    end_ts = int(ends_at.timestamp())
    e = discord.Embed(title=f"\U0001f381 {prize}", color=PRIMARY)
    e.add_field(name="\u2139\ufe0f Description", value=description, inline=False)
    e.add_field(name="\u23f0 Ends",        value=f"<t:{end_ts}:F>  (<t:{end_ts}:R>)", inline=False)
    e.add_field(name="\U0001f3c6 Winners",  value=f"**{winners}** winner{'s' if winners != 1 else ''}", inline=True)
    e.add_field(name="\U0001f465 Participants", value="**0** entered", inline=True)
    e.add_field(name="\U0001f3af Hosted By",value=interaction.user.mention, inline=True)
    if extra_entries:
        e.add_field(name="\U0001f381 Bonus Entries", value="Click **Extra Entries** to see how to earn more!", inline=False)
    if image_url:
        e.set_image(url=image_url)
    e.set_footer(text=f"{FOOTER_BRAND} | ID: {ga_id}")
    e.timestamp = datetime.utcnow()

    ping_content = ping if (ping and ping.lower() != "none") else ""
    ping_content = (ping_content + " **\U0001f389 NEW GIVEAWAY!**").strip() if ping_content else "**\U0001f389 NEW GIVEAWAY!**"

    await interaction.channel.send(
        content=ping_content, embed=e, view=GiveawayView(ga_id),
        allowed_mentions=discord.AllowedMentions(everyone=True, roles=True)
    )
    await interaction.response.send_message(f"\u2705 Giveaway started! ID: `{ga_id}`", ephemeral=True)


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
        await interaction.response.send_message("\u274c Giveaway not found.", ephemeral=True)
        return
    participants = json.loads(ga["participants"]) if ga["participants"] else []
    if not participants:
        conn.close()
        await interaction.response.send_message("\u274c No participants to draw from.", ephemeral=True)
        return
    winner_ids = random.sample(participants, min(ga["winners"], len(participants)))
    c.execute("UPDATE giveaways SET winner_ids = ? WHERE id = ?", (json.dumps(winner_ids), giveaway_id))
    conn.commit()
    conn.close()
    winner_mentions = " ".join([f"<@{w}>" for w in winner_ids])
    e = discord.Embed(title=f"\U0001f381 {ga['prize']} \u2014 Giveaway Ended", color=SUCCESS)
    e.add_field(name="\U0001f3c6 Winners",            value=winner_mentions,              inline=False)
    e.add_field(name="\U0001f465 Total Participants", value=f"**{len(participants):,}**", inline=True)
    e.add_field(name="\U0001f194 Giveaway ID",        value=f"`{giveaway_id}`",           inline=True)
    e.set_footer(text=FOOTER_BRAND)
    e.timestamp = datetime.utcnow()
    await interaction.channel.send(
        content=f"\U0001f389 Congratulations {winner_mentions}! You won **{ga['prize']}**!",
        embed=e,
        allowed_mentions=discord.AllowedMentions(users=True)
    )
    await interaction.response.send_message("\u2705 Giveaway ended.", ephemeral=True)


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
                e = base_embed("\u26a0\ufe0f Backup Server", color=DANGER)
                e.description = f"If the main server becomes unavailable, join our backup:\n\n> **{link}**"
                await member.send(embed=e)
                results["sent"] += 1
            except Exception:
                results["failed"] += 1
    await asyncio.gather(*[send_dm(m) for m in members])
    e = base_embed("\U0001f4e8 Backup Link Sent", color=SUCCESS)
    e.add_field(name="\u2705 Delivered", value=f"**{results['sent']}**",  inline=True)
    e.add_field(name="\u274c Failed",    value=f"**{results['failed']}**", inline=True)
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
    e = base_embed(f"\U0001f4ca {target.display_name}'s Stats", color=PRIMARY)
    e.set_thumbnail(url=target.display_avatar.url)
    e.add_field(name="\U0001f3ae Total Carries", value=f"**{row['count'] or 0}**", inline=True)
    e.add_field(name="\U0001f4b6 Total Spent",   value=f"**\u20ac{row['total']:.2f}**" if row["total"] else "**\u20ac0.00**", inline=True)
    e.add_field(name="\u2b50 Vouches",           value=f"**{vc['vc'] or 0}**", inline=True)
    await interaction.response.send_message(embed=e, ephemeral=True)

class AccountSaleModal(ui.Modal, title="Post Account For Sale"):
    game        = ui.TextInput(label="Game / Account Type",          placeholder="Brawl Stars",                       style=discord.TextStyle.short)
    description = ui.TextInput(label="Account Description",          placeholder="Masters rank, 50 maxed brawlers...", style=discord.TextStyle.long, max_length=600)
    price       = ui.TextInput(label="Price (EUR)",                  placeholder="49.99",                              style=discord.TextStyle.short)
    image_url   = ui.TextInput(label="Screenshot URL",               placeholder="https://i.imgur.com/...",            style=discord.TextStyle.short)
    contact     = ui.TextInput(label="Contact / Purchase Method",    placeholder="DM this account / open a ticket",    style=discord.TextStyle.short, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price_val = float(self.price.value.replace("€", "").strip())
        except ValueError:
            await interaction.response.send_message("❌ Invalid price. Enter a number like `49.99`.", ephemeral=True)
            return

        guild = interaction.guild
        cfg   = get_config(guild.id)
        sale_ch_id = cfg["account_sale_channel_id"] if cfg else None
        sale_ch    = guild.get_channel(sale_ch_id) if sale_ch_id else interaction.channel

        e = base_embed(f"🛒 Account For Sale — {self.game.value}", color=GOLD)
        e.set_author(name="BrawlCarry | Account Shop", icon_url=guild.icon.url if guild.icon else discord.Embed.Empty)
        e.description = self.description.value
        e.add_field(name="🎮 Game",         value=self.game.value,             inline=True)
        e.add_field(name="💰 Price",        value=f"**€{price_val:.2f}**",     inline=True)
        e.add_field(name="📩 To Purchase",  value=self.contact.value or "Open a ticket or DM staff", inline=True)
        e.set_footer(text=f"{FOOTER_BRAND} | React or DM to purchase")

        wm_file = None
        img = self.image_url.value.strip()
        if img:
            wm_file = await fetch_and_watermark(img)
            if wm_file:
                e.set_image(url="attachment://proof.jpg")

        if wm_file:
            await sale_ch.send(embed=e, file=wm_file)
        else:
            await sale_ch.send(embed=e)

        await interaction.response.send_message(f"✅ Account posted in {sale_ch.mention}.", ephemeral=True)
OAUTH_AUTHORIZE_URL  = os.getenv("OAUTH_AUTHORIZE_URL", "https://yourdomain.up.railway.app/authorize")
OAUTH_BACKEND_URL    = os.getenv("OAUTH_BACKEND_URL",   "https://yourdomain.up.railway.app")
RESTORE_SECRET       = os.getenv("RESTORE_SECRET", "")

class BackupPanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ui.Button(
            label="🛡️ Secure Backup Access",
            style=discord.ButtonStyle.link,
            url=OAUTH_AUTHORIZE_URL,
            emoji="🔒"
        ))

@bot.tree.command(name="backup_panel", description="Post the backup access panel so members can authorize")
@app_commands.checks.has_permissions(administrator=True)
async def backup_panel(interaction: discord.Interaction):
    try:
        import requests as req
        r = req.get(f"{OAUTH_BACKEND_URL}/count", timeout=5)
        count = r.json().get("authorized_users", "?")
    except Exception:
        count = "?"
    e = base_embed("🛡️ Secure Your Backup Access", color=DANGER)
    e.description = (
        "If the main server is ever deleted, raided or banned, we will automatically add you to our backup server.\n\n"
        "**Click the button below and authorize with Discord.**\n\n"
        "🔒 We only request:\n"
        "> `identify` — to know who you are\n"
        "> `guilds.join` — to add you to the backup server if needed\n\n"
        "⚠️ You only need to do this once."
    )
    e.add_field(name="✅ Members Secured", value=f"**{count}**", inline=True)
    await interaction.channel.send(embed=e, view=BackupPanelView())
    await interaction.response.send_message("✅ Backup panel posted.", ephemeral=True)

@bot.tree.command(name="restore_backup", description="Trigger restore — adds all authorized members to backup server")
@app_commands.describe(backup_server_id="The ID of the backup server to add members to")
@app_commands.checks.has_permissions(administrator=True)
async def restore_backup(interaction: discord.Interaction, backup_server_id: str):
    cfg = get_config(interaction.guild.id)
    owner_id = cfg["owner_id"] if cfg else None
    if owner_id and interaction.user.id != owner_id:
        await interaction.response.send_message("❌ Only the server owner can trigger a restore.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        import requests as req
        r = req.post(
            f"{OAUTH_BACKEND_URL}/restore",
            json={"secret": RESTORE_SECRET, "guild_id": backup_server_id},
            timeout=60
        )
        data = r.json()
        e = base_embed("🛡️ Restore Complete", color=SUCCESS)
        e.add_field(name="✅ Added",     value=f"**{data.get('success', 0)}**",   inline=True)
        e.add_field(name="🔄 Refreshed", value=f"**{data.get('refreshed', 0)}**", inline=True)
        e.add_field(name="❌ Failed",    value=f"**{data.get('failed', 0)}**",    inline=True)
        e.description = "All authorized members have been added to the backup server."
        await interaction.followup.send(embed=e, ephemeral=True)
    except Exception as ex:
        await interaction.followup.send(f"❌ Restore failed: `{ex}`", ephemeral=True)
    
@bot.tree.command(name="assign_role", description="Assign or remove a role from a member")
@app_commands.describe(
    member="The member to assign/remove the role to",
    role="The role to assign or remove",
    action="assign or remove"
)
@app_commands.checks.has_permissions(manage_roles=True)
async def assign_role(interaction: discord.Interaction, member: discord.Member, role: discord.Role, action: str = "assign"):
    action = action.lower()
    if action not in ("assign", "remove"):
        await interaction.response.send_message("❌ Action must be `assign` or `remove`.", ephemeral=True)
        return
    try:
        if action == "assign":
            await member.add_roles(role, reason=f"Assigned by {interaction.user}")
            e = base_embed("✅ Role Assigned", color=SUCCESS)
            e.description = f"{role.mention} has been assigned to {member.mention}."
        else:
            await member.remove_roles(role, reason=f"Removed by {interaction.user}")
            e = base_embed("✅ Role Removed", color=DANGER)
            e.description = f"{role.mention} has been removed from {member.mention}."
        await interaction.response.send_message(embed=e, ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don't have permission to manage that role.", ephemeral=True)
        
@bot.tree.command(name="set_prestige_price", description="Update a prestige boost price")
@app_commands.describe(
    spec="Which prestige (e.g. Prestige 0 -> Prestige 1)",
    price="New price in EUR (e.g. 15)"
)
@app_commands.checks.has_permissions(manage_channels=True)
async def set_prestige_price(interaction: discord.Interaction, spec: str, price: str):
    matched = None
    for key in PRESTIGE_PRICES:
        if key.lower().replace(" ", "") == spec.lower().replace(" ", ""):
            matched = key
            break
    if not matched:
        await interaction.response.send_message(
            f"❌ Unknown spec. Valid options:\n" + "\n".join(f"`{k}`" for k in PRESTIGE_PRICES),
            ephemeral=True
        )
        return
    PRESTIGE_PRICES[matched] = price
    e = base_embed("✅ Prestige Price Updated", color=SUCCESS)
    e.description = f"**{matched}** is now **€{price}**\n\n⚠️ Re-post `/prestige_panel` to show the new price."
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="post_account", description="Post an account for sale in the account-selling channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def post_account(interaction: discord.Interaction):
    await interaction.response.send_modal(AccountSaleModal())
    
@bot.tree.command(name="application_panel", description="Post the staff application panel in this channel")
@app_commands.describe(image_url="Optional banner image URL")
@app_commands.checks.has_permissions(manage_channels=True)
async def application_panel(interaction: discord.Interaction, image_url: str = None):
    e = base_embed("📝 Staff Applications", color=PRIMARY)
    e.description = (
        "Interested in joining the BrawlCarry team? Click a button below to submit your application.\n\n"
        "**Available Positions:**\n"
        "🟠 **Booster** — Play for customers and earn money\n"
        "🛡️ **Admin** — Manage the server and support customers\n"
        "📰 **Reporter** — Report issues, moderate and assist staff\n\n"
        "Applications are reviewed by staff within 48 hours."
    )
    if image_url:
        e.set_image(url=image_url)
    await interaction.channel.send(embed=e, view=ApplicationPanelView())
    await interaction.response.send_message("✅ Application panel posted.", ephemeral=True)
    
@bot.tree.command(name="help", description="View all available bot commands")
async def help_cmd(interaction: discord.Interaction):
    rank_icons   = " ".join(RANK_EMOJI.values())
    pres_icons   = " ".join(PRESTIGE_EMOJI.values())
    e = base_embed("\U0001f4cb BrawlCarry Bot \u2014 Commands", color=PRIMARY)
    e.description = (
        f"**Rank Icons:** {rank_icons}\n"
        f"**Prestige Icons:** {pres_icons}\n\n"
        "**\u2699\ufe0f Admin Commands**\n"
        "`/setup` \u2014 Configure all channels, ticket categories & owner\n"
        "`/configure_ticket_panel` \u2014 Customise support ticket panel text\n"
        "`/order_panel` \u2014 Post the generic order panel\n"
        "`/ranked_panel` \u2014 Post the Ranked Boost intake panel \U0001f525\n"
        "`/prestige_panel` \u2014 Post the Prestige Boost intake panel \u2728\n"
        "`/ticket_panel` \u2014 Post the General Support ticket panel\n"
        "`/vouch_panel` \u2014 Send vouch panel to user or channel\n"
        "`/giveaway` \u2014 Start a giveaway\n"
        "`/end_giveaway` \u2014 End a giveaway and draw winners\n"
        "`/backup_link` \u2014 DM all members the backup server link\n\n"
        "**\u2705 Staff Commands**\n"
        "`/order_complete` \u2014 Mark an order as completed\n"
        "`/add_payment_method` \u2014 Add a payment method to order forms\n"
        "`/remove_payment_method` \u2014 Remove a payment method from order forms\n"
        "`/list_payment_methods` \u2014 View all configured payment methods\n\n"
        "**\U0001f464 User Commands**\n"
        "`/stats` \u2014 View your carry statistics\n"
        "`/help` \u2014 Show this menu\n\n"
        "**\U0001f4e6 Order Flow**\n"
        "1. Customer clicks **Ranked/Prestige Boost** \u2192 ticket opens in the dedicated channel\n"
        "2. An order card appears in the ticket for staff\n"
        "3. Staff click **\U0001f4e2 Publish to Boosters** \u2192 enter earnings \u2192 claiming card posted\n"
        "4. Booster clicks **\U0001f7e0 Claim This Boost** \u2192 instantly added to the customer's ticket\n\n"
        "**\U0001f6e0 Service Types**\n"
        "> \U0001f7e2 **Boost** \u2014 staff play on customer's account (standard price)\n"
        "> \U0001f534 **Carry** \u2014 staff play alongside customer (2x price)\n\n"
        "**\u2699\ufe0f Channel Setup Tips**\n"
        "- `ranked_ticket_channel` / `prestige_ticket_channel` \u2014 separate ticket thread channels per boost type\n"
        "- `ranked_panel_channel` / `prestige_panel_channel` \u2014 where booster claiming cards appear\n"
        "- `ticket_channel` \u2014 fallback for General Support tickets\n"
        "- `completed_channel` \u2014 where completed order receipts are posted"
    )
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if ALLOWED_GUILDS and interaction.guild_id not in ALLOWED_GUILDS:
        try:
            await interaction.response.send_message(
                "❌ This bot is not authorized to operate in this server.", ephemeral=True
            )
        except Exception:
            pass
    
# ---------------------------------------------------------------------------
# ERROR HANDLER
# ---------------------------------------------------------------------------
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "\u274c You do not have permission to use this command."
    else:
        msg = f"\u274c An error occurred: `{error}`"
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)

async def giveaway_reminder_loop():
    await bot.wait_until_ready()
    reminded_12h = set()
    reminded_24h = set()
    while not bot.is_closed():
        try:
            conn = get_db()
            c    = conn.cursor()
            c.execute("SELECT * FROM giveaways WHERE (winner_ids IS NULL OR winner_ids = '') AND ended_at IS NOT NULL")
            giveaways = c.fetchall()
            conn.close()
            now = datetime.utcnow()
            for ga in giveaways:
                ends_at = datetime.strptime(ga["ended_at"], "%Y-%m-%d %H:%M:%S.%f") if "." in ga["ended_at"] else datetime.strptime(ga["ended_at"], "%Y-%m-%d %H:%M:%S")
                remaining = (ends_at - now).total_seconds()
                if remaining <= 0:
                    continue
                for guild in bot.guilds:
                    # Try to find the giveaway message channel from guild channels
                    pass  # Reminders are sent as new messages; channel tracking not stored — see note below
                if 86400 >= remaining > 82800 and ga["id"] not in reminded_24h:
                    reminded_24h.add(ga["id"])
                    for guild in bot.guilds:
                        for ch in guild.text_channels:
                            try:
                                async for msg in ch.history(limit=50):
                                    if msg.embeds and msg.author == guild.me:
                                        if any(ga["id"] in (f.value or "") for f in msg.embeds[0].fields):
                                            e = base_embed("⏰ Giveaway Reminder", color=GOLD)
                                            e.description = f"🎁 **{ga['prize']}** giveaway ends in **24 hours**!\n<t:{int(ends_at.timestamp())}:R>"
                                            await ch.send(embed=e)
                                            raise StopIteration
                            except StopIteration:
                                break
                            except Exception:
                                continue
                if 43200 >= remaining > 39600 and ga["id"] not in reminded_12h:
                    reminded_12h.add(ga["id"])
                    for guild in bot.guilds:
                        for ch in guild.text_channels:
                            try:
                                async for msg in ch.history(limit=50):
                                    if msg.embeds and msg.author == guild.me:
                                        if any(ga["id"] in (f.value or "") for f in msg.embeds[0].fields):
                                            e = base_embed("⏰ Giveaway Reminder", color=GOLD)
                                            e.description = f"🎁 **{ga['prize']}** giveaway ends in **12 hours**!\n<t:{int(ends_at.timestamp())}:R>"
                                            await ch.send(embed=e)
                                            raise StopIteration
                            except StopIteration:
                                break
                            except Exception:
                                continue
        except Exception as ex:
            print(f"[WARN] Giveaway reminder loop error: {ex}")
        await asyncio.sleep(3600)

# ---------------------------------------------------------------------------
# STARTUP
# ---------------------------------------------------------------------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"[OK] {bot.user} | Slash commands synced")

    bot.add_view(OrderButton())
    bot.add_view(TicketView())
    bot.add_view(TicketCloseView())
    bot.add_view(VouchButtonView())
    bot.add_view(VouchButtonView(order_kind="prestige"))
    bot.add_view(RankedPanelButton())
    bot.add_view(PrestigePanelButton())
    bot.add_view(ApplicationPanelView())

    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT id FROM giveaways WHERE winner_ids IS NULL OR winner_ids = ''")
    for row in c.fetchall():
        bot.add_view(GiveawayView(row["id"]))

    c.execute("SELECT id, ticket_channel_id FROM orders WHERE status IN ('pending', 'claimed')")
    for row in c.fetchall():
        order_type = "prestige" if row["id"].startswith("PREST") else "ranked"
        bot.add_view(OrderActionsView(row["id"], row["ticket_channel_id"], order_type))

    c.execute("SELECT id, ticket_channel_id FROM orders WHERE status = 'pending'")
    for row in c.fetchall():
        bot.add_view(BoosterClaimView(row["id"], row["ticket_channel_id"]))

    conn.close()
    print(f"[OK] Persistent views registered")

    bot.loop.create_task(giveaway_reminder_loop())
    print(f"[OK] Giveaway reminder loop started")


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("[ERROR] DISCORD_TOKEN not set in environment.")
        exit(1)
    bot.run(token)
