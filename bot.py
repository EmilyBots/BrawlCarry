import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import json, os, uuid, random, io, aiohttp, asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:zZrBWjYglZfFzAvmFzKBMhphniaMywYQ@postgres.railway.internal:5432/railway")
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn
def get_config(guild_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM guild_config WHERE guild_id = %s", (guild_id,))
    row = c.fetchone()
    conn.close()
    return row

def set_config(guild_id: int, **kwargs):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT guild_id FROM guild_config WHERE guild_id = %s", (guild_id,))
    if c.fetchone():
        if kwargs:
            set_clause = ", ".join(f"{k} = %s" for k in kwargs)
            c.execute(
                f"UPDATE guild_config SET {set_clause} WHERE guild_id = %s",
                (*kwargs.values(), guild_id)
            )
    else:
        c.execute("INSERT INTO guild_config (guild_id) VALUES (%s)", (guild_id,))
        if kwargs:
            set_clause = ", ".join(f"{k} = %s" for k in kwargs)
            c.execute(
                f"UPDATE guild_config SET {set_clause} WHERE guild_id = %s",
                (*kwargs.values(), guild_id)
            )
    conn.commit()
    conn.close()
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

HARDCODED_SUPPORT_ROLES = [1491447093078921267, 1355262062124859600, 1479079737052762205]  # Replace with your role IDs

FOOTER_BRAND = "Powered by Brawl Carry (TM)"

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
    conn = get_db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        user_id BIGINT,
        from_tier TEXT,
        to_tier TEXT,
        price FLOAT,
        method TEXT,
        status TEXT DEFAULT 'pending',
        image_url TEXT,
        ticket_channel_id BIGINT,
        booster_id BIGINT,
        booster_earnings FLOAT,
        order_type TEXT,
        service_type TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        claimed_at TIMESTAMP,
        estimated_price FLOAT,
        p11_count TEXT,
        booster_rating INT,
        completion_time_seconds INT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS vouchers (
        id TEXT PRIMARY KEY,
        code TEXT UNIQUE,
        amount FLOAT,
        used_by BIGINT,
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
        description TEXT,
        winners INT,
        hosted_by BIGINT,
        participants TEXT,
        winner_ids TEXT,
        image_url TEXT,
        extra_entries TEXT,
        ping TEXT,
        bonus_role_id BIGINT,
        ended_at TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS guild_config (
        guild_id BIGINT PRIMARY KEY,
        vouch_channel_id BIGINT,
        ticket_channel_id BIGINT,
        completed_channel_id BIGINT,
        ticket_category_id BIGINT,
        ticket_panel_title TEXT,
        ticket_panel_desc TEXT,
        ranked_panel_channel_id BIGINT,
        prestige_panel_channel_id BIGINT,
        ranked_ticket_channel_id BIGINT,
        prestige_ticket_channel_id BIGINT,
        owner_id BIGINT,
        ticket_log_channel_id BIGINT,
        application_channel_id BIGINT,
        application_review_channel_id BIGINT,
        account_sale_channel_id BIGINT,
        booster_role_id BIGINT,
        proof_channel_id BIGINT,
        inactive_ticket_hours INT DEFAULT 24,
        application_ticket_channel_id BIGINT,
        carrier_role_id BIGINT,
        ticket_support_roles TEXT,
        reviewer_roles TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS payment_methods (
        id SERIAL PRIMARY KEY,
        guild_id BIGINT,
        label TEXT,
        emoji TEXT,
        UNIQUE(guild_id, label)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS account_listings (
        id SERIAL PRIMARY KEY,
        guild_id BIGINT,
        seller_id BIGINT,
        game TEXT,
        description TEXT,
        price FLOAT,
        contact TEXT,
        image_url TEXT,
        status TEXT DEFAULT 'available',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS booster_availability (
        user_id BIGINT PRIMARY KEY,
        guild_id BIGINT,
        status TEXT DEFAULT 'available',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS rank_prices (
        id SERIAL PRIMARY KEY,
        guild_id BIGINT,
        from_rank TEXT,
        to_rank TEXT,
        base_price FLOAT,
        UNIQUE(guild_id, from_rank, to_rank)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS ticket_activity (
        channel_id BIGINT PRIMARY KEY,
        guild_id BIGINT,
        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        warned INT DEFAULT 0
    )""")

    conn.commit()
    migrations = [
        ("giveaways",    "extra_entries TEXT"),
        ("giveaways",    "ping TEXT"),
        ("giveaways",    "bonus_role_id BIGINT"),
        ("guild_config", "completed_channel_id BIGINT"),
        ("guild_config", "ticket_category_id BIGINT"),
        ("vouchers",     "method TEXT"),
        ("guild_config", "ranked_panel_channel_id BIGINT"),
        ("guild_config", "prestige_panel_channel_id BIGINT"),
        ("guild_config", "ranked_ticket_channel_id BIGINT"),
        ("guild_config", "prestige_ticket_channel_id BIGINT"),
        ("guild_config", "owner_id BIGINT"),
        ("orders",       "ticket_channel_id BIGINT"),
        ("orders",       "booster_id BIGINT"),
        ("orders",       "booster_earnings FLOAT"),
        ("orders",       "order_type TEXT"),
        ("orders",       "service_type TEXT"),
        ("guild_config", "application_channel_id BIGINT"),
        ("guild_config", "application_review_channel_id BIGINT"),
        ("guild_config", "account_sale_channel_id BIGINT"),
        ("guild_config", "ticket_log_channel_id BIGINT"),
        ("vouchers",     "order_kind TEXT"),
        ("vouchers",     "service_type TEXT"),
        ("orders",       "claimed_at TIMESTAMP"),
        ("orders",       "estimated_price FLOAT"),
        ("orders",       "p11_count TEXT"),
        ("orders",       "booster_rating INT"),
        ("orders",       "completion_time_seconds INT"),
        ("guild_config", "booster_role_id BIGINT"),
        ("guild_config", "proof_channel_id BIGINT"),
        ("guild_config", "inactive_ticket_hours INT DEFAULT 24"),
        ("guild_config", "application_ticket_channel_id BIGINT"),
        ("orders", "brawler_name TEXT"),
        ("guild_config", "account_sale_ticket_channel_id BIGINT"),
        ("orders", "trophy_val INT"),
        ("guild_config", "carrier_role_id BIGINT"),
        ("guild_config", "ticket_support_roles TEXT"),
        ("guild_config", "reviewer_roles TEXT"),
    ]

    for table, col_def in migrations:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
            conn.commit()
        except Exception:
            conn.rollback()

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
    c.execute("SELECT label, emoji FROM payment_methods WHERE guild_id = %s ORDER BY id", (guild_id,))
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
            "INSERT INTO payment_methods (guild_id, label, emoji) VALUES (%s, %s, %s)",
            (guild_id, label, emoji)
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.rollback()
        conn.close()
        return False

def remove_payment_method(guild_id: int, label: str) -> bool:
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM payment_methods WHERE guild_id = %s AND label = %s", (guild_id, label))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

# ---------------------------------------------------------------------------
# PRICE ESTIMATION SYSTEM
# ---------------------------------------------------------------------------
# Base prices: (from_rank_index, to_rank_index) => base EUR price
# Rank indices correspond to ALL_RANKS list below
ALL_RANKS = [
    "Bronze I", "Bronze II", "Bronze III",
    "Silver I", "Silver II", "Silver III",
    "Gold I", "Gold II", "Gold III",
    "Diamond I", "Diamond II", "Diamond III",
    "Mythic I", "Mythic II", "Mythic III",
    "Legendary I", "Legendary II", "Legendary III",
    "Masters I", "Masters II", "Masters III",
]

# Price per rank tier jump (base price per division crossed)
# Tier-based prices per single division step (e.g. Bronze I -> Bronze II)
TIER_DIVISION_PRICES = {
    "Bronze":    0.80,
    "Silver":    0.80,
    "Gold":      1.00,
    "Diamond":   1.00,
    "Mythic":    2.00,
    "Legendary": 4.00,
    "Masters":   10.00,
}

# Explicit multi-division / cross-tier prices from price chart
EXPLICIT_RANK_PRICES = {
    ("Silver I",    "Gold I"):       2.60,
    ("Gold I",      "Diamond I"):    4.00,
    ("Diamond I",   "Mythic I"):     10.00,
    ("Mythic I",    "Legendary I"):  15.00,  # M1->L1 (Legendary boost M1-L1)
    ("Legendary I", "Masters I"):    35.00,  # L1->M1 (Master boost L1-M1); note: m1-m3 in legendary boost = Mythic
    ("Masters I",   "Pro"):          210.00,
    # Legendary boost single steps (from_mythic to legendary)
    ("Mythic I",    "Mythic II"):    4.00,
    ("Mythic II",   "Mythic III"):   5.00,
    ("Mythic III",  "Legendary I"):  6.00,
    # Master boost single steps
    ("Legendary I",  "Legendary II"):  10.00,
    ("Legendary II", "Legendary III"): 10.00,
    ("Legendary III","Masters I"):     15.00,
    # Pro boost single steps
    ("Masters I",   "Masters II"):   35.00,
    ("Masters II",  "Masters III"):  80.00,
    ("Masters III", "Pro"):          95.00,
}

def calculate_rank_price(from_rank: str, to_rank: str, p11_str: str, service_type: str, guild_id: int) -> float:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT base_price FROM rank_prices WHERE guild_id = %s AND from_rank = %s AND to_rank = %s",
        (guild_id, from_rank, to_rank)
    )
    custom = c.fetchone()
    conn.close()

    if custom:
        base = float(custom["base_price"])
    else:
        # Check explicit price table first
        if (from_rank, to_rank) in EXPLICIT_RANK_PRICES:
            base = EXPLICIT_RANK_PRICES[(from_rank, to_rank)]
        else:
            try:
                fi = ALL_RANKS.index(from_rank)
                ti = ALL_RANKS.index(to_rank) if to_rank != "Pro" else len(ALL_RANKS)
            except ValueError:
                return 0.0
            if ti <= fi:
                return 0.0
            # Sum division-by-division using tier prices
            base = 0.0
            for i in range(fi, min(ti, len(ALL_RANKS) - 1)):
                tier = ALL_RANKS[i].split()[0]
                base += TIER_DIVISION_PRICES.get(tier, 0.80)
            if to_rank == "Pro" and ALL_RANKS[-1].startswith("Masters"):
                base += TIER_DIVISION_PRICES.get("Masters", 10.00)

    # P11 adjustment
    p11_num = 0
    if p11_str:
        try:
            if "-" in p11_str:
                parts = p11_str.split("-")
                p11_num = (int(parts[0]) + int(parts[1])) // 2
            elif "+" in p11_str:
                p11_num = int(p11_str.replace("+", "")) + 5
            else:
                p11_num = int(p11_str)
        except Exception:
            p11_num = 45

    if p11_num < 40:
        multiplier = 1.0 + min((40 - p11_num) * 0.005, 0.25)
    elif p11_num > 50:
        multiplier = 1.0 - min((p11_num - 50) * 0.004, 0.20)
    else:
        multiplier = 1.0

    base *= multiplier
    if service_type == "carry":
        base *= 2.0
    return round(base, 2)

# ---------------------------------------------------------------------------
# BOOSTER AVAILABILITY HELPERS
# ---------------------------------------------------------------------------
AVAILABILITY_STATUSES = ["available", "busy", "offline"]

def get_booster_status(user_id: int) -> str:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT status FROM booster_availability WHERE user_id = %s", (user_id,))
    row = c.fetchone()
    conn.close()
    return row["status"] if row else "available"

def set_booster_status(user_id: int, guild_id: int, status: str):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """INSERT INTO booster_availability (user_id, guild_id, status, updated_at) VALUES (%s, %s, %s, %s)
           ON CONFLICT (user_id) DO UPDATE SET guild_id = EXCLUDED.guild_id, status = EXCLUDED.status, updated_at = EXCLUDED.updated_at""",
        (user_id, guild_id, status, datetime.utcnow())
    )
    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# TICKET ACTIVITY HELPERS
# ---------------------------------------------------------------------------
def update_ticket_activity(channel_id: int, guild_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """INSERT INTO ticket_activity (channel_id, guild_id, last_activity, warned) VALUES (%s, %s, %s, 0)
           ON CONFLICT (channel_id) DO UPDATE SET guild_id = EXCLUDED.guild_id, last_activity = EXCLUDED.last_activity, warned = 0""",
        (channel_id, guild_id, datetime.utcnow())
    )
    conn.commit()
    conn.close()

def remove_ticket_activity(channel_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM ticket_activity WHERE channel_id = %s", (channel_id,))
    conn.commit()
    conn.close()

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
                await text_ch.set_permissions(member, view_channel=True, read_message_history=True, send_messages=True, reason="Temporary ticket access")
            except Exception:
                pass
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
            pings = [f"<@&{rid}>" for rid in HARDCODED_SUPPORT_ROLES]
            if pings:
                await thread.send(" ".join(pings), allowed_mentions=discord.AllowedMentions(roles=True))
            update_ticket_activity(thread.id, guild.id)
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
    for rid in HARDCODED_SUPPORT_ROLES:
        support_role = guild.get_role(rid)
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    ch = await guild.create_text_channel(
        name=name,
        overwrites=overwrites,
        category=category,
        topic=f"Opened by {member} | {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
    )
    await ch.send(content=member.mention, embed=topic_embed, view=view)
    update_ticket_activity(ch.id, guild.id)
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

def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        m = seconds // 60
        s = seconds % 60
        return f"{m}m {s}s"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m"

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

# Minimum desired rank is Diamond I
DESIRED_RANKS = [
    "Diamond I", "Diamond II", "Diamond III",
    "Mythic I", "Mythic II", "Mythic III",
    "Legendary I", "Legendary II", "Legendary III",
    "Masters I", "Masters II", "Masters III",
    "Pro",
]

RANK_EMOJI = {
    "Bronze":    "<:Bronze:1493263821375279135>",
    "Silver":    "<:Silver:1493263822906196039>",
    "Gold":      "<:Gold:1493263820318052473>",
    "Diamond":   "<:Diamond:1493263818275426314>",
    "Mythic":    "<:Mythic:1493263816069218544>",
    "Legendary": "<:Legendary:1493263814802542796>",
    "Masters":   "<:Masters:1493263813519343647>",
    "Pro":       "<:Pro:1493263812109795459>",
}

# ---------------------------------------------------------------------------
# PRESTIGE OPTIONS & EMOJIS
# ---------------------------------------------------------------------------
PRESTIGE_OPTIONS = [
    "Prestige 0 -> Prestige 1",
    "Prestige 1 -> Prestige 2",
    "Prestige 2 -> Prestige 3",
]

PRESTIGE_PRICES = {
    "Prestige 0 -> Prestige 1": "8",
    "Prestige 1 -> Prestige 2": "20",
    "Prestige 2 -> Prestige 3": "65",
}

PRESTIGE_BASE_TROPHIES = {
    "Prestige 0 -> Prestige 1": 0,
    "Prestige 1 -> Prestige 2": 1000,
    "Prestige 2 -> Prestige 3": 2000,
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
TROPHY_OPTIONS = [
    "0 - 500",
    "501 - 1000",
    "1001 - 1500",
    "1501 - 2000",
    "2001 - 2500",
    "2501 - 3000",
    "3001+",
]

def apply_trophy_discount(price: float, trophy_range: str, trophy_val: int = 0, prestige_spec: str = None) -> float:
    """Half price in first 500 relative trophies of a prestige; 2% per 50 trophies above that."""
    base = PRESTIGE_BASE_TROPHIES.get(prestige_spec, 0) if prestige_spec else 0
    relative_trophies = max(0, trophy_val - base)
    if relative_trophies <= 500:
        price *= 0.5
    bands = relative_trophies // 50
    discount = min(bands * 0.02, 0.20)
    price *= (1.0 - discount)
    return round(price, 2)

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

def _build_order_details_str(order_type: str, from_tier: str, to_tier: str, service_type: str) -> str:
    svc = "Carry" if service_type == "carry" else "Boost"
    if order_type == "prestige":
        spec = f"{from_tier} -> {to_tier}"
        pe   = prestige_emoji(spec)
        return f"{svc} {pe} `{from_tier}` → `{to_tier}`"
    else:
        fe = rank_emoji(from_tier or "")
        te = rank_emoji(to_tier or "")
        return f"{svc} {fe} `{from_tier}` → {te} `{to_tier}`"

# ---------------------------------------------------------------------------
# BOOSTER RATING VIEW (sent after order completion)
# ---------------------------------------------------------------------------
class BoosterRatingView(ui.View):
    def __init__(self, order_id: str, booster_id: int):
        super().__init__(timeout=None)
        self.order_id   = order_id
        self.booster_id = booster_id

        select = ui.Select(
            placeholder="Rate your booster...",
            options=RATING_OPTIONS,
            custom_id=f"booster_rate_{order_id}"
        )
        select.callback = self._on_rate
        self.add_item(select)

    async def _on_rate(self, interaction: discord.Interaction):
        rating = int(interaction.data["values"][0])
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE orders SET booster_rating = %s WHERE id = %s", (rating, self.order_id))
        conn.commit()
        conn.close()

        stars = "⭐" * rating + f" ({rating}/5)"
        e = base_embed("⭐ Rating Submitted", color=GOLD)
        e.description = f"You rated your booster **{stars}**.\n\nThank you for your feedback!"

        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message(embed=e, ephemeral=True)

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

        # Check booster availability
        status = get_booster_status(booster.id)
        if status != "available":
            await interaction.response.send_message(
                f"❌ Your availability is set to **{status}**. Set it to `available` with `/availability` before claiming.",
                ephemeral=True
            )
            return

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

        # Check carrier role for carry orders
        cfg = get_config(guild.id)
        carrier_role_id = cfg["carrier_role_id"] if cfg else None
        if carrier_role_id:
            conn_pre = get_db()
            c_pre    = conn_pre.cursor()
            c_pre.execute("SELECT service_type FROM orders WHERE id = %s", (self.order_id,))
            pre_row = c_pre.fetchone()
            conn_pre.close()
            if pre_row and pre_row["service_type"] == "carry":
                member_role_ids = {r.id for r in booster.roles}
                if carrier_role_id not in member_role_ids:
                    await interaction.response.send_message(
                        "❌ You need the **Carrier** role to claim carry orders.", ephemeral=True
                    )
                    return

        conn = get_db()
        c    = conn.cursor()

        # Anti-double-claim: lock with UPDATE and check rowcount

        c.execute(
            "UPDATE orders SET booster_id = %s, status = 'claimed', claimed_at = %s WHERE id = %s AND status = 'pending'",
            (booster.id, datetime.utcnow(), self.order_id)
        )
        affected = c.rowcount
        conn.commit()

        if affected == 0:
            # Either already claimed or not found — check which
            c.execute("SELECT status, booster_id FROM orders WHERE id = %s", (self.order_id,))
            order_check = c.fetchone()
            conn.close()
            if not order_check:
                await interaction.response.send_message("❌ Order not found.", ephemeral=True)
            else:
                await interaction.response.send_message(
                    "❌ This order has already been claimed by another booster.", ephemeral=True
                )
            return

# Check active orders cap
        c.execute(
            "SELECT COUNT(*) as cnt FROM orders WHERE booster_id = %s AND status = 'claimed'",
            (booster.id,)
        )
        active_count = c.fetchone()["cnt"]

        if active_count > 2:
            # Revert the claim
            c.execute(
                "UPDATE orders SET booster_id = NULL, status = 'pending', claimed_at = NULL WHERE id = %s",
                (self.order_id,)
            )
            conn.commit()
            conn.close()
            await interaction.response.send_message(
                "❌ You already have **2 active orders**. Please complete one before claiming another.",
                ephemeral=True
            )
            return

        c.execute("SELECT * FROM orders WHERE id = %s", (self.order_id,))
        order = c.fetchone()
        conn.close()

        for item in self.children:
            item.disabled = True

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

        ticket_ch_id = self.ticket_channel_id or (order["ticket_channel_id"] if order else None)

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
                    update_ticket_activity(ticket_ch_id, guild.id)
                except Exception as ex:
                    print(f"[WARN] Could not add booster to ticket: {ex}")

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
        await interaction.response.defer(ephemeral=True)

        try:
            earnings = float(self.booster_earnings.value.replace("€", "").strip())
        except ValueError:
            await interaction.followup.send(
                "❌ Invalid earnings amount. Please enter a number like `12.00`.", ephemeral=True
            )
            return

        conn = get_db()
        c    = conn.cursor()
        c.execute("SELECT * FROM orders WHERE id = %s", (self.order_id,))
        order = c.fetchone()
        if not order:
            conn.close()
            await interaction.followup.send("❌ Order not found.", ephemeral=True)
            return

        c.execute("UPDATE orders SET booster_earnings = %s WHERE id = %s", (earnings, self.order_id))
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
            # fallback: try fetching as a thread
            if panel_ch_id:
                try:
                    panel_ch = await guild.fetch_channel(panel_ch_id)
                except Exception:
                    panel_ch = None
        if not panel_ch:
            await interaction.followup.send(
                f"❌ Panel channel not found (id={panel_ch_id}). Make sure it is configured via `/setup`.", ephemeral=True
            )
            return

        color      = PRIMARY if self.order_type == "ranked" else ACCENT
        title_str  = "🔥 Ranked Boost Available" if self.order_type == "ranked" else "✨ Prestige Boost Available"
        svc_type   = order["service_type"] or "boost"
        svc_label  = "Carry 🔴" if svc_type == "carry" else "Boost 🟢"

        from_tier  = order["from_tier"] or "?"
        to_tier    = order["to_tier"] or "?"
        details    = _build_order_details_str(self.order_type, from_tier, to_tier, svc_type)

        pay_emoji  = _payment_emoji(order["method"], guild.id)
        p11        = order["p11_count"] or "—"

        claim_e = base_embed(title_str, color=color)
        claim_e.set_author(
            name="BrawlCarry | Boost Available",
            icon_url=guild.icon.url if guild.icon else discord.Embed.Empty
        )
        claim_e.add_field(name="📦 Order Details",   value=details,                                        inline=False)
        if order["brawler_name"]:
            claim_e.add_field(name="🎮 Brawler",     value=order["brawler_name"],                         inline=True)
        if order["trophy_val"]:
            claim_e.add_field(name="🏆 Trophies",    value=f"{order['trophy_val']:,}",                    inline=True)
        claim_e.add_field(name="💰 You Earn",         value=f"**€{earnings:.2f}**",                        inline=True)
        claim_e.add_field(name="🛠 Service",           value=svc_label,                                    inline=True)
        claim_e.add_field(name=f"{P11_EMOJI} P11",    value=p11,                                          inline=True)
        claim_e.add_field(name="🆔 Order ID",          value=f"`{self.order_id}`",                         inline=True)
        claim_e.add_field(name="🕐 Posted",            value=f"<t:{int(datetime.utcnow().timestamp())}:R>", inline=True)

        if self.extra_notes.value:
            claim_e.add_field(name="📝 Notes", value=self.extra_notes.value, inline=False)

        claim_e.set_footer(text=f"{FOOTER_BRAND} | Click the button below to claim this order")

        await panel_ch.send(
            embed=claim_e,
            view=BoosterClaimView(self.order_id, ticket_channel_id=self.ticket_channel_id)
        )

        await interaction.followup.send(
            f"✅ Order `{self.order_id}` published to {panel_ch.mention} with **€{earnings:.2f}** booster earnings.",
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

    @ui.button(label="Publish to Boosters", style=discord.ButtonStyle.success, emoji="📢", custom_id="order_publish_btn_v1")
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
class VouchDetailModal(ui.Modal, title="Submit Your Vouch"):
    amount   = ui.TextInput(label="Order Amount (EUR)", placeholder="44.99", style=discord.TextStyle.short)
    feedback = ui.TextInput(label="Your Feedback", placeholder="Fast service, very professional...", style=discord.TextStyle.long, max_length=500)
    image_url = ui.TextInput(label="Proof Image URL (optional)", placeholder="https://i.imgur.com/...", required=False, style=discord.TextStyle.short)

    def __init__(self, rating: int, payment_method: str, order_kind: str = "ranked", service_type: str = "boost"):
        super().__init__()
        self.rating         = rating
        self.payment_method = payment_method
        self.order_kind     = order_kind
        self.service_type   = service_type

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount_val = float(self.amount.value.replace("€", "").strip())
        except ValueError:
            amount_val = 0.0

        stars    = self.rating
        star_str = "⭐" * stars + f"  ({stars}/5)"
        img      = self.image_url.value.strip() if self.image_url.value else None

        vouch_id = f"VOUCH-{uuid.uuid4().hex[:6].upper()}"
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM vouchers")
        vouch_number = c.fetchone()["cnt"] + 1
        c.execute(
            "INSERT INTO vouchers (id, code, amount, used_by, rating, feedback, image_url, method, order_kind, service_type) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
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

        if self.order_kind == "prestige":
            svc_icon   = prestige_emoji("Prestige 0 -> Prestige 1")
            kind_label = "Prestige Boost" if self.service_type == "boost" else "Prestige Carry"
        else:
            kind_label = "Ranked Boost" if self.service_type == "boost" else "Ranked Carry"
            svc_icon   = "🔥"

        pay_emoji = _payment_emoji(self.payment_method, guild_id or 0)

        filled   = "⭐"
        empty    = "⬜"
        star_vis = filled * stars + empty * (5 - stars)

        e = discord.Embed(color=GOLD)
        e.set_author(
            name=f"{interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url
        )
        e.title = f"⭐ Vouch N°{vouch_number}  |  {star_vis}"
        e.add_field(name="👤 Customer",         value=interaction.user.mention,       inline=True)
        e.add_field(name="💰 Amount Paid",       value=f"**€{amount_val:.2f}**",       inline=True)
        e.add_field(name=f"{pay_emoji} Payment", value=f"**{self.payment_method}**",   inline=True)
        e.add_field(name=f"{svc_icon} Service",  value=f"**{kind_label}**",            inline=True)
        e.add_field(name="⭐ Rating",            value=star_str,                       inline=True)
        e.add_field(name="💬 Feedback",          value=f"> {self.feedback.value}",     inline=False)
        e.set_footer(text=FOOTER_BRAND)
        e.timestamp = datetime.utcnow()

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
    def __init__(self, guild_id: int, order_kind: str = "ranked"):
        super().__init__(timeout=180)
        self.guild_id     = guild_id
        self.order_kind   = order_kind
        self.rating       = None
        self.payment      = None
        self.service_type = None

        rating_select = ui.Select(placeholder="Select your rating...", options=RATING_OPTIONS, custom_id="vouch_rating", row=0)
        rating_select.callback = self._on_rating
        self.add_item(rating_select)

        methods    = get_payment_methods(guild_id)
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

        submit_btn = ui.Button(label="Continue", style=discord.ButtonStyle.success, custom_id="vouch_continue", row=3, emoji="✅")
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
            await interaction.response.send_message(f"❌ Please select: **{', '.join(missing)}**", ephemeral=True)
            return
        await interaction.response.send_modal(
            VouchDetailModal(self.rating, self.payment, self.order_kind, self.service_type)
        )


# ---------------------------------------------------------------------------
# TICKET PANEL SETUP MODAL
# ---------------------------------------------------------------------------
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
    notes = ui.TextInput(label="Additional Notes (Optional)", placeholder="Any special requests...", required=False, style=discord.TextStyle.long, max_length=500)

    def __init__(self, current_rank: str, desired_rank: str, p11: str, payment: str, service_type: str, estimated_price: float):
        super().__init__()
        self.current_rank    = current_rank
        self.desired_rank    = desired_rank
        self.p11             = p11
        self.payment         = payment
        self.service_type    = service_type
        self.estimated_price = estimated_price

    async def on_submit(self, interaction: discord.Interaction):
        conn     = get_db()
        c        = conn.cursor()
        order_id = f"RANKED-{uuid.uuid4().hex[:6].upper()}"
        c.execute(
            "INSERT INTO orders (id, user_id, from_tier, to_tier, price, method, order_type, service_type, p11_count) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (order_id, interaction.user.id, self.current_rank, self.desired_rank, 0.0,
             self.payment, "ranked", self.service_type, self.p11)
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
        svc_label = "Carry 🔴 (2x price)" if self.service_type == "carry" else "Boost 🟢"

        welcome = base_embed("🔥 Ranked Boost Ticket", color=PRIMARY)
        welcome.description = (
            f"Welcome, {member.mention}! 🎮\n\n"
            f"📋 **Order:** `{order_id}`\n"
            f"📦 **Order Details:** {fe} `{self.current_rank}` → {te} `{self.desired_rank}`\n"
            f"⚡ **P11 Brawlers:** {P11_EMOJI} {self.p11}\n"
            f"🛠 **Service:** {svc_label}\n"
            f"{pay_emoji} **Payment:** {self.payment}\n"
            f"🕐 **Opened:** <t:{int(datetime.utcnow().timestamp())}:F>\n\n"
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

        conn2 = get_db()
        c2 = conn2.cursor()
        c2.execute("UPDATE orders SET ticket_channel_id = %s WHERE id = %s", (ticket.id, order_id))
        conn2.commit()
        conn2.close()

        order_e = base_embed("🔥 New Ranked Boost Order", color=PRIMARY)
        order_e.set_author(name="BrawlCarry | Staff View", icon_url=guild.icon.url if guild.icon else discord.Embed.Empty)
        order_e.add_field(name="👤 Customer",       value=member.mention,                                               inline=True)
        order_e.add_field(name="📦 Order Details",  value=f"{fe} `{self.current_rank}` → {te} `{self.desired_rank}`",  inline=True)
        order_e.add_field(name=f"⚡ P11",            value=f"{P11_EMOJI} {self.p11}",                                   inline=True)                          
        svc_field_name = "🔴 Carry" if self.service_type == "carry" else "🟢 Boost"
        order_e.add_field(name=svc_field_name,      value=svc_label,                                                    inline=True)
        order_e.add_field(name=f"{pay_emoji} Payment", value=self.payment,                                             inline=True)
        order_e.add_field(name="🕐 Placed",         value=f"<t:{int(datetime.utcnow().timestamp())}:R>",               inline=True)
        if self.notes.value:
            order_e.add_field(name="📝 Notes", value=self.notes.value, inline=False)
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
    notes = ui.TextInput(label="Additional Notes (Optional)", placeholder="Any special requests...", required=False, style=discord.TextStyle.long, max_length=500)

    def __init__(self, prestige_spec: str, trophy_range: str, trophy_val: int, brawler_name: str, payment: str, service_type: str):
        super().__init__()
        self.prestige_spec = prestige_spec
        self.trophy_range  = trophy_range
        self.trophy_val    = trophy_val
        self.brawler_name  = brawler_name
        self.payment       = payment
        self.service_type  = service_type

    async def on_submit(self, interaction: discord.Interaction):
        conn     = get_db()
        c        = conn.cursor()
        order_id = f"PREST-{uuid.uuid4().hex[:6].upper()}"
        from_p   = self.prestige_spec.split("->")[0].strip()
        to_p     = self.prestige_spec.split("->")[-1].strip()

        c.execute(
            "INSERT INTO orders (id, user_id, from_tier, to_tier, price, method, order_type, service_type, brawler_name, trophy_val) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (order_id, interaction.user.id, from_p, to_p, 0.0,
             self.payment, "prestige", self.service_type, self.brawler_name, self.trophy_val)
        )

        conn.commit()
        conn.close()

        guild  = interaction.guild
        member = interaction.user
        cfg    = get_config(guild.id)

        prestige_ticket_ch_id = cfg["prestige_ticket_channel_id"] if cfg else None

        pe        = prestige_emoji(self.prestige_spec)
        pay_emoji = _payment_emoji(self.payment, guild.id)
        svc_label = "Carry 🔴 (2x price)" if self.service_type == "carry" else "Boost 🟢"

        welcome = base_embed("✨ Prestige Boost Ticket", color=ACCENT)
        welcome.description = (
            f"Welcome, {member.mention}! ✨\n\n"
            f"📋 **Order:** `{order_id}`\n"
            f"{pe} **Prestige:** {self.prestige_spec}\n"
            f"🎮 **Brawler:** {self.brawler_name}\n"
            f"🏆 **Current Trophies:** {self.trophy_val:,}\n"
            f"🛠 **Service:** {svc_label}\n"
            f"{pay_emoji} **Payment:** {self.payment}\n"
            f"🕐 **Opened:** <t:{int(datetime.utcnow().timestamp())}:F>\n\n"
            "Our staff will contact you shortly to complete your prestige boost. "
            "Please have your payment ready!"
        )
        welcome.set_author(name=member.display_name, icon_url=member.display_avatar.url)

        try:
            ticket = await create_ticket_thread(
                guild=guild,
                member=member,
                name=f"prestige-{member.name[:12].lower()}",
                topic_embed=welcome,
                view=TicketCloseView(),
                cfg=cfg,
                override_channel_id=prestige_ticket_ch_id,
            )
        except Exception as ticket_err:
            await interaction.response.send_message(
                f"❌ Failed to create ticket: `{ticket_err}`\n\nAsk an admin to check `/setup` channel permissions.",
                ephemeral=True
            )
            return

        conn2 = get_db()
        c2    = conn2.cursor()
        c2.execute("UPDATE orders SET ticket_channel_id = %s WHERE id = %s", (ticket.id, order_id))
        conn2.commit()
        conn2.close()

        order_e = base_embed("✨ New Prestige Boost Order", color=ACCENT)
        order_e.set_author(name="BrawlCarry | Staff View", icon_url=guild.icon.url if guild.icon else discord.Embed.Empty)
        order_e.add_field(name="👤 Customer",          value=member.mention,      inline=True)
        order_e.add_field(name=f"{pe} Prestige",       value=self.prestige_spec,  inline=True)
        order_e.add_field(name="🎮 Brawler",            value=self.brawler_name,      inline=True)
        order_e.add_field(name="🏆 Trophies",           value=f"{self.trophy_val:,}", inline=True)
        svc_field_name2 = "🔴 Carry" if self.service_type == "carry" else "🟢 Boost"
        order_e.add_field(name=svc_field_name2,        value=svc_label,           inline=True)
        order_e.add_field(name=f"{pay_emoji} Payment", value=self.payment,        inline=True)
        order_e.add_field(name="🕐 Placed",            value=f"<t:{int(datetime.utcnow().timestamp())}:R>", inline=True)
        if self.notes.value:
            order_e.add_field(name="📝 Notes", value=self.notes.value, inline=False)
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
    order_id_input = ui.TextInput(label="Order ID",                   placeholder="RANKED-XXXXXX / PREST-XXXXXX", style=discord.TextStyle.short)
    final_price    = ui.TextInput(label="Final Price Paid (EUR)",      placeholder="44.99",                        style=discord.TextStyle.short)
    payment_used   = ui.TextInput(label="Payment Method Used",         placeholder="PayPal / Bank Transfer / Crypto", style=discord.TextStyle.short)
    notes          = ui.TextInput(label="Completion Notes (Optional)", placeholder="e.g. Reached Masters III",     required=False, style=discord.TextStyle.long, max_length=500)
    image_url      = ui.TextInput(label="Proof Image URL (Optional)",  placeholder="https://i.imgur.com/...",      required=False, style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        order_id = self.order_id_input.value.strip().upper()
        conn     = get_db()
        c        = conn.cursor()
        c.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
        order = c.fetchone()

        if not order:
            conn.close()
            await interaction.followup.send(f"❌ Order `{order_id}` not found.", ephemeral=True)
            return

        try:
            price_val = float(self.final_price.value.replace("€", "").strip())
        except ValueError:
            price_val = order["price"] or 0.0

        now = datetime.utcnow()

        # Calculate completion time
        completion_secs = None
        if order["claimed_at"]:
            claimed_dt = order["claimed_at"] if isinstance(order["claimed_at"], datetime) else None
            if claimed_dt:
                completion_secs = int((now - claimed_dt).total_seconds())
        c.execute(
            "UPDATE orders SET status = 'completed', price = %s, method = %s, completed_at = %s, completion_time_seconds = %s WHERE id = %s",
            (price_val, self.payment_used.value.strip(), now, completion_secs, order_id)
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
            customer = interaction.guild.get_member(order["user_id"]) if interaction.guild else None

        svc_type   = order["service_type"] or "boost"
        ord_type   = order["order_type"] or "ranked"
        details    = _build_order_details_str(ord_type, order["from_tier"] or "", order["to_tier"] or "", svc_type)
        svc_label  = "Carry 🔴" if svc_type == "carry" else "Boost 🟢"
        pay_emoji  = _payment_emoji(self.payment_used.value.strip(), guild_id or 0)
        booster_mention = f"<@{order['booster_id']}>" if order["booster_id"] else "Unassigned"

        conn.close()

        img = self.image_url.value.strip() if self.image_url.value else None

        # Order Summary Embed
        e = base_embed("✅ Order Completed — Summary", color=SUCCESS)
        e.set_author(name="BrawlCarry | Order Summary", icon_url=interaction.user.display_avatar.url)
        e.add_field(name="🆔 Order ID",      value=f"`{order_id}`",                                               inline=True)
        e.add_field(name="👤 Customer",      value=customer.mention if customer else f"<@{order['user_id']}>",    inline=True)
        e.add_field(name="🟠 Booster",       value=booster_mention,                                               inline=True)
        e.add_field(name="💰 Amount Paid",   value=f"**€{price_val:.2f}**",                                       inline=True)
        e.add_field(name=f"{pay_emoji} Payment", value=f"**{self.payment_used.value.strip()}**",                  inline=True)
        e.add_field(name="📦 Result",        value=details,                                                        inline=True)
        e.add_field(name="🛠 Service",       value=svc_label,                                                     inline=True)
        e.add_field(name="✅ Completed By",  value=interaction.user.mention,                                      inline=True)
        if completion_secs is not None:
            e.add_field(name="⏱ Time Taken",  value=format_duration(completion_secs),                            inline=True)
        e.add_field(name="🕐 Completed At",  value=f"<t:{int(now.timestamp())}:F>",                              inline=False)
        if self.notes.value:
            e.add_field(name="📝 Notes", value=self.notes.value, inline=False)

        wm_file = None
        if img:
            wm_file = await fetch_and_watermark(img)
            if wm_file:
                e.set_image(url="attachment://proof.jpg")

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

        # DM customer with rating request
        if customer and order["booster_id"]:
            try:
                dm_e = base_embed("✅ Your Order is Complete!", color=SUCCESS)
                dm_e.description = (
                    f"Great news! Your order **`{order_id}`** has been completed.\n\n"
                    f"📦 **Result:** {details}\n"
                    f"💰 **Amount:** €{price_val:.2f}\n"
                    f"{pay_emoji} **Payment:** {self.payment_used.value.strip()}\n"
                    f"⏱ **Time taken:** {format_duration(completion_secs) if completion_secs else 'N/A'}\n\n"
                    "Please rate your booster below! ⭐"
                )
                await customer.send(embed=dm_e, view=BoosterRatingView(order_id, order["booster_id"]))
            except discord.Forbidden:
                pass
        elif customer:
            try:
                dm_e = base_embed("✅ Your Order is Complete!", color=SUCCESS)
                dm_e.description = (
                    f"Great news! Your order **`{order_id}`** has been completed.\n\n"
                    f"📦 **Result:** {details}\n"
                    f"💰 **Amount:** €{price_val:.2f}\n\n"
                    "Thank you for choosing BrawlCarry! Consider leaving a vouch ⭐"
                )
                await customer.send(embed=dm_e)
            except discord.Forbidden:
                pass

        await interaction.followup.send("✅ Order marked as completed!", ephemeral=True)


# ---------------------------------------------------------------------------
# RANKED BOOST SELECT-MENU VIEW
# ---------------------------------------------------------------------------
class RankedOrderView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id     = guild_id
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

        desired_options = []
        for r in DESIRED_RANKS:
            emo = rank_emoji(r)
            opt = discord.SelectOption(label=r, value=r)
            if emo:
                opt.emoji = emo
            desired_options.append(opt)

        self.clear_items()

        current_select = ui.Select(placeholder="Your current rank...", options=current_options, custom_id="ranked_current2", row=0)
        current_select.callback = self._on_current
        self.add_item(current_select)

        desired_select = ui.Select(placeholder="Your desired rank (min Diamond I)...", options=desired_options, custom_id="ranked_desired2", row=1)
        desired_select.callback = self._on_desired
        self.add_item(desired_select)

        p11_select = ui.Select(
            placeholder="Number of Power 11 brawlers...",
            options=[discord.SelectOption(label=n, value=n, emoji=P11_EMOJI) for n in P11_OPTIONS],
            custom_id="ranked_p112", row=2
        )
        p11_select.callback = self._on_p11
        self.add_item(p11_select)

        methods    = get_payment_methods(guild_id)
        pay_select = ui.Select(
            placeholder="Payment method...",
            options=[discord.SelectOption(label=lbl, value=lbl, emoji=emo) for lbl, emo in methods],
            custom_id="ranked_pay2", row=3
        )
        pay_select.callback = self._on_pay
        self.add_item(pay_select)

        svc_select = ui.Select(
            placeholder="Boost or Carry? (Carry = 2x price)",
            options=SERVICE_OPTIONS,
            custom_id="ranked_svc2", row=4
        )
        svc_select.callback = self._on_svc_submit
        self.add_item(svc_select)

    async def _on_current(self, interaction: discord.Interaction): self.current_rank = interaction.data["values"][0]; await interaction.response.defer()
    async def _on_desired(self, interaction: discord.Interaction): self.desired_rank = interaction.data["values"][0]; await interaction.response.defer()
    async def _on_p11(self,     interaction: discord.Interaction): self.p11          = interaction.data["values"][0]; await interaction.response.defer()
    async def _on_pay(self,     interaction: discord.Interaction): self.payment      = interaction.data["values"][0]; await interaction.response.defer()

    async def _on_svc_submit(self, interaction: discord.Interaction):
        self.service_type = interaction.data["values"][0]
        missing = []
        if not self.current_rank: missing.append("Current Rank")
        if not self.desired_rank: missing.append("Desired Rank")
        if not self.p11:          missing.append("Power 11 Brawlers")
        if not self.payment:      missing.append("Payment Method")
        if missing:
            await interaction.response.send_message(f"❌ Please fill in: **{', '.join(missing)}**", ephemeral=True)
            return

        # Validate rank ordering
        try:
            current_idx = ALL_RANKS.index(self.current_rank)
        except ValueError:
            current_idx = -1

        # Desired rank validation — must be higher than current and at least Diamond I
        DIAMOND_I_IDX = ALL_RANKS.index("Diamond I")
        try:
            desired_idx = ALL_RANKS.index(self.desired_rank)
        except ValueError:
            desired_idx = len(ALL_RANKS)  # "Pro" is above all

        if self.desired_rank != "Pro" and desired_idx <= current_idx:
            await interaction.response.send_message(
                f"❌ Your desired rank **{self.desired_rank}** must be **higher** than your current rank **{self.current_rank}**.",
                ephemeral=True
            )
            return

        fe = rank_emoji(self.current_rank)
        te = rank_emoji(self.desired_rank)
        e = base_embed("📋 Order Summary", color=PRIMARY)
        e.description = (
            f"**Please confirm your order:**\n\n"
            f"📦 **Boost:** {fe} `{self.current_rank}` → {te} `{self.desired_rank}`\n"
            f"{P11_EMOJI} **P11 Brawlers:** {self.p11}\n"
            f"🛠 **Service:** {'Carry 🔴 (2x price)' if self.service_type == 'carry' else 'Boost 🟢'}\n"
            f"💰 **Payment:** {self.payment}\n\n"
            "Click **Confirm & Continue** to open your ticket."
        )

        await interaction.response.send_message(
            embed=e,
            view=_RankedConfirmView(self.current_rank, self.desired_rank, self.p11, self.payment, self.service_type, 0.0),
            ephemeral=True
        )


class _RankedConfirmView(ui.View):
    def __init__(self, current_rank, desired_rank, p11, payment, service_type, estimated_price):
        super().__init__(timeout=120)
        self.current_rank    = current_rank
        self.desired_rank    = desired_rank
        self.p11             = p11
        self.payment         = payment
        self.service_type    = service_type
        self.estimated_price = estimated_price

    @ui.button(label="Confirm & Continue", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(
            RankedOrderModal(self.current_rank, self.desired_rank, self.p11, self.payment, self.service_type, self.estimated_price)
        )


# ---------------------------------------------------------------------------
# PRESTIGE BOOST SELECT-MENU VIEW
# ---------------------------------------------------------------------------
class PrestigeTrophyModal(ui.Modal, title="Enter Trophy Count"):
    trophy_input = ui.TextInput(
        label="Current Trophies on the Brawler",
        placeholder="e.g. 750 or 1200",
        style=discord.TextStyle.short,
        max_length=10
    )
    brawler_name = ui.TextInput(
        label="Brawler Name",
        placeholder="e.g. Shelly, Bull, Crow...",
        style=discord.TextStyle.short,
        max_length=50
    )

    def __init__(self, prestige_spec: str, payment: str, service_type: str):
        super().__init__()
        self.prestige_spec = prestige_spec
        self.payment       = payment
        self.service_type  = service_type

    async def on_submit(self, interaction: discord.Interaction):
        trophy_raw = self.trophy_input.value.strip()
        try:
            trophy_val = int(trophy_raw.replace(",", "").replace(".", ""))
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number like `750`.", ephemeral=True)
            return

        if trophy_val <= 500:
            trophy_range = "0 - 500"
        elif trophy_val <= 1000:
            trophy_range = "501 - 1000"
        elif trophy_val <= 1500:
            trophy_range = "1001 - 1500"
        elif trophy_val <= 2000:
            trophy_range = "1501 - 2000"
        elif trophy_val <= 2500:
            trophy_range = "2001 - 2500"
        elif trophy_val <= 3000:
            trophy_range = "2501 - 3000"
        else:
            trophy_range = "3001+"

        brawler = self.brawler_name.value.strip()

        pe = prestige_emoji(self.prestige_spec)
        e = base_embed("📋 Order Summary", color=ACCENT)
        e.description = (
            f"**Please confirm your order:**\n\n"
            f"{pe} **Prestige:** {self.prestige_spec}\n"
            f"🎮 **Brawler:** {brawler}\n"
            f"🏆 **Current Trophies:** {trophy_val:,}\n"
            f"🛠 **Service:** {'Carry 🔴 (2x price)' if self.service_type == 'carry' else 'Boost 🟢'}\n"
            f"💰 **Payment:** {self.payment}\n\n"
            "Click **Confirm & Continue** to open your ticket."
        )
        await interaction.response.send_message(
            embed=e,
            view=_PrestigeConfirmView(self.prestige_spec, trophy_range, trophy_val, brawler, self.payment, self.service_type),
            ephemeral=True
        )

class PrestigeOrderView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.prestige_spec = None
        self.trophy_range  = None
        self.payment       = None
        self.service_type  = None

        pres_options = []
        for p in PRESTIGE_OPTIONS:
            emo = PRESTIGE_EMOJI.get(p)
            opt = discord.SelectOption(label=p, value=p, emoji=emo) if emo else discord.SelectOption(label=p, value=p)
            pres_options.append(opt)

        pres_select = ui.Select(placeholder="Select prestige spec...", options=pres_options, custom_id="prest_spec2", row=0)
        pres_select.callback = self._on_spec
        self.add_item(pres_select)

        methods    = get_payment_methods(guild_id)
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

    async def _on_spec(self,   interaction: discord.Interaction): self.prestige_spec = interaction.data["values"][0]; await interaction.response.defer()
    async def _on_pay(self,    interaction: discord.Interaction): self.payment       = interaction.data["values"][0]; await interaction.response.defer()

    async def _on_svc_submit(self, interaction: discord.Interaction):
        self.service_type = interaction.data["values"][0]
        missing = []
        if not self.prestige_spec: missing.append("Prestige Spec")
        if not self.payment:       missing.append("Payment Method")
        if missing:
            await interaction.response.send_message(f"❌ Please fill in: **{', '.join(missing)}**", ephemeral=True)
            return
        await interaction.response.send_modal(
            PrestigeTrophyModal(self.prestige_spec, self.payment, self.service_type)
        )


class _PrestigeConfirmView(ui.View):
    def __init__(self, prestige_spec, trophy_range, trophy_val, brawler_name, payment, service_type):
        super().__init__(timeout=120)
        self.prestige_spec = prestige_spec
        self.trophy_range  = trophy_range
        self.trophy_val    = trophy_val
        self.brawler_name  = brawler_name
        self.payment       = payment
        self.service_type  = service_type

    @ui.button(label="Confirm & Continue", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(
            PrestigeOrderModal(self.prestige_spec, self.trophy_range, self.trophy_val, self.brawler_name, self.payment, self.service_type)
        )


# ---------------------------------------------------------------------------
# APPLICATION SYSTEM
# ---------------------------------------------------------------------------
APPLICATION_ROLES = ["Booster", "Admin", "Reporter"]

APPLICATION_REQUIREMENTS = {
    "Booster":  "**Requirement:** Masters III rank minimum.\nYou must be able to provide proof of your rank.",
    "Admin":    "**Requirement:** Active server member, trustworthy, and fluent in English.",
    "Reporter": "**Requirement:** Active member willing to help moderate and report issues.",
}

class ApplicationModal(ui.Modal):
    why   = ui.TextInput(label="Why do you want this role?",      style=discord.TextStyle.long,  max_length=500)
    exp   = ui.TextInput(label="Relevant experience",              style=discord.TextStyle.long,  max_length=500)
    age   = ui.TextInput(label="Your age",                         style=discord.TextStyle.short, max_length=3)
    extra = ui.TextInput(label="Anything else? (Optional)",        style=discord.TextStyle.long,  max_length=300, required=False)

    def __init__(self, role: str):
        super().__init__(title=f"{role} Application")
        self.role = role
        if role == "Booster":
            self.rank_proof = ui.TextInput(
                label="Current Rank + Proof URL (Masters III min.)",
                placeholder="Masters III — https://i.imgur.com/...",
                style=discord.TextStyle.short,
                max_length=300
            )
            self.add_item(self.rank_proof)
        else:
            self.rank_proof = None

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
        e.add_field(name="👤 Applicant",      value=member.mention,      inline=True)
        e.add_field(name="🆔 User ID",        value=f"`{member.id}`",    inline=True)
        e.add_field(name="🎭 Role Applied",   value=f"**{self.role}**",  inline=True)
        e.add_field(name="❓ Why This Role",   value=self.why.value,     inline=False)
        e.add_field(name="📋 Experience",     value=self.exp.value,      inline=False)
        e.add_field(name="🎂 Age",            value=self.age.value,      inline=True)
        if self.rank_proof and self.rank_proof.value:
            e.add_field(name="🏆 Rank Proof", value=self.rank_proof.value, inline=False)
        if self.extra.value:
            e.add_field(name="💬 Extra Info", value=self.extra.value,    inline=False)
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
        cfg = get_config(interaction.guild.id)
        reviewer_role_ids = set()
        if cfg and cfg.get("reviewer_roles"):
            for rid in cfg["reviewer_roles"].split(","):
                rid = rid.strip().strip("<@&>")
                try:
                    reviewer_role_ids.add(int(rid))
                except ValueError:
                    pass
        member_role_ids = {r.id for r in interaction.user.roles}
        if not interaction.user.guild_permissions.manage_roles and not (reviewer_role_ids & member_role_ids):
            await interaction.response.send_message("❌ You don't have permission to review applications.", ephemeral=True)
            return

        member      = interaction.guild.get_member(self.applicant_id)
        result_text = ""
        if member:
            role_obj = discord.utils.get(interaction.guild.roles, name=self.role)
            if role_obj:
                try:
                    await member.add_roles(role_obj, reason=f"Application accepted by {interaction.user}")
                    result_text = f" Role **{self.role}** has been assigned."
                except discord.Forbidden:
                    result_text = " ⚠️ Could not assign role (missing permissions)."
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
        cfg = get_config(interaction.guild.id)
        reviewer_role_ids = set()
        if cfg and cfg.get("reviewer_roles"):
            for rid in cfg["reviewer_roles"].split(","):
                rid = rid.strip().strip("<@&>")
                try:
                    reviewer_role_ids.add(int(rid))
                except ValueError:
                    pass
        member_role_ids = {r.id for r in interaction.user.roles}
        if not interaction.user.guild_permissions.manage_roles and not (reviewer_role_ids & member_role_ids):
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
        styles = {
            "Booster":  discord.ButtonStyle.danger,
            "Admin":    discord.ButtonStyle.primary,
            "Reporter": discord.ButtonStyle.secondary,
        }
        emojis = {"Booster": "🟠", "Admin": "🛡️", "Reporter": "📰"}
        for role in APPLICATION_ROLES:
            btn = ui.Button(
                label=f"Apply for {role}",
                style=styles.get(role, discord.ButtonStyle.primary),
                emoji=emojis.get(role, "📝"),
                custom_id=f"app_btn_{role.lower()}_v1"
            )
            btn.callback = self._make_callback(role)
            self.add_item(btn)

    def _make_callback(self, role: str):
        async def callback(interaction: discord.Interaction):
            req = APPLICATION_REQUIREMENTS.get(role, "")
            e = base_embed(f"📝 {role} Application", color=PRIMARY, description=req)
            await interaction.response.send_message(embed=e, view=_AppConfirmView(role), ephemeral=True)
        return callback


class _AppConfirmView(ui.View):
    def __init__(self, role: str):
        super().__init__(timeout=120)
        self.role = role

    @ui.button(label="I meet the requirements — Apply", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ApplicationModal(self.role))

# ---------------------------------------------------------------------------
# COMBINED TICKET + APPLICATION PANEL VIEW
# ---------------------------------------------------------------------------
class CombinedPanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="General Support", style=discord.ButtonStyle.primary, emoji="ℹ️", custom_id="combined_support_v1")
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

    @ui.button(label="Apply for a Role", style=discord.ButtonStyle.secondary, emoji="📝", custom_id="combined_apply_v1")
    async def apply_role(self, interaction: discord.Interaction, button: ui.Button):
        guild  = interaction.guild
        member = interaction.user
        cfg    = get_config(guild.id)

        e = base_embed("📝 Role Application", color=PRIMARY)
        e.description = (
            f"Welcome, {member.mention}!\n\n"
            f"📋 **Category:** Role Application\n"
            f"🕐 **Opened:** <t:{int(datetime.utcnow().timestamp())}:F>\n\n"
            "Please select the role you'd like to apply for below."
        )
        e.set_author(name=member.display_name, icon_url=member.display_avatar.url)

        ticket = await create_ticket_thread(
            guild=guild,
            member=member,
            name=f"apply-{member.name[:12].lower()}",
            topic_embed=e,
            view=TicketCloseView(),
            cfg=cfg,
        )

        role_e = base_embed("📝 Select a Role to Apply For", color=PRIMARY)
        role_e.description = (
            "🟠 **Booster** — Masters III rank minimum\n"
            "🛡️ **Admin** — Trustworthy & fluent in English\n"
            "📰 **Reporter** — Active moderator & issue reporter\n\n"
            "Click a button below to begin your application."
        )
        await ticket.send(embed=role_e, view=ApplicationPanelView())
        await interaction.response.send_message(f"✅ Application ticket created: {ticket.mention}", ephemeral=True)

# ---------------------------------------------------------------------------
# PANEL BUTTON VIEWS  (persistent)
# ---------------------------------------------------------------------------
class RankedPanelButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Ranked Boost Order", style=discord.ButtonStyle.danger, emoji="🔥", custom_id="ranked_panel_btn_v1")
    async def open_ranked(self, interaction: discord.Interaction, button: ui.Button):
        e = base_embed("🔥 Ranked Boost Order", color=PRIMARY)
        e.description = (
            "Select your ranks, Power 11 count, payment method and service type.\n"
            "The bot will show you a **price estimate** before you confirm.\n\n"
            "> 🟢 **Boost** — we play on your account (standard price)\n"
            "> 🔴 **Carry** — we play alongside you (2x price)\n\n"
            "⚠️ Minimum desired rank is **Diamond I**. Desired rank must be higher than current rank."
        )
        e.add_field(name="🏆 Rank Emojis",
                    value=" ".join(v for v in RANK_EMOJI.values()), inline=False)
        await interaction.response.send_message(embed=e, view=RankedOrderView(interaction.guild_id), ephemeral=True)


class PrestigePanelButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Prestige Boost Order", style=discord.ButtonStyle.primary, emoji="✨", custom_id="prestige_panel_btn_v1")
    async def open_prestige(self, interaction: discord.Interaction, button: ui.Button):
        e = base_embed("✨ Prestige Boost Order", color=ACCENT)
        e.description = (
            "Select your prestige spec, current trophies, payment method and service type.\n"
            "The bot will show you a **price estimate** before you confirm.\n\n"
            "> 🟢 **Boost** — we play on your account (standard price)\n"
            "> 🔴 **Carry** — we play alongside you (2x price)\n\n"
            "⚠️ Do not share passwords or sensitive information."
        )
        pres_icons = " ".join(PRESTIGE_EMOJI.values())
        e.add_field(name="✨ Prestige Icons", value=pres_icons, inline=False)
        await interaction.response.send_message(embed=e, view=PrestigeOrderView(interaction.guild_id), ephemeral=True)


# ---------------------------------------------------------------------------
# VOUCH BUTTON VIEW
# ---------------------------------------------------------------------------
class VouchButtonView(ui.View):
    def __init__(self, order_kind: str = "ranked"):
        super().__init__(timeout=None)
        self.order_kind = order_kind

    @ui.button(label="Submit a Vouch", style=discord.ButtonStyle.success, emoji="⭐", custom_id="vouch_btn_v2")
    async def vouch(self, interaction: discord.Interaction, button: ui.Button):
        guild_id = interaction.guild.id if interaction.guild else 0
        e = base_embed("⭐ Submit Your Vouch", color=GOLD)
        e.description = (
            "Select your **rating**, **payment method** and **service type**, then click **Continue** "
            "to fill in your feedback and proof.\n\nThank you for taking the time to vouch!"
        )
        await interaction.response.send_message(embed=e, view=VouchSelectorView(guild_id, order_kind=self.order_kind), ephemeral=True)


# ---------------------------------------------------------------------------
# GIVEAWAY VIEW
# ---------------------------------------------------------------------------
class GiveawayView(ui.View):
    def __init__(self, giveaway_id: str):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @ui.button(label="Enter Giveaway", style=discord.ButtonStyle.success, emoji="🎉", custom_id="ga_enter_v2")
    async def enter(self, interaction: discord.Interaction, button: ui.Button):
        conn = get_db()
        c    = conn.cursor()
        c.execute("SELECT * FROM giveaways WHERE id = %s", (self.giveaway_id,))
        ga = c.fetchone()
        if not ga:
            conn.close()
            await interaction.response.send_message("❌ Giveaway not found.", ephemeral=True)
            return
        participants = json.loads(ga["participants"]) if ga["participants"] else []
        if interaction.user.id in set(participants):
            conn.close()
            await interaction.response.send_message("❌ You have already entered this giveaway.", ephemeral=True)
            return

        extra_entries_data = json.loads(ga["extra_entries"]) if ga["extra_entries"] else []
        member_role_ids = {r.id for r in interaction.user.roles}

        total_entries = 1
        for entry_role in extra_entries_data:
            if entry_role["role_id"] in member_role_ids:
                total_entries += entry_role["count"]

        for _ in range(total_entries):
            participants.append(interaction.user.id)

        c.execute("UPDATE giveaways SET participants = %s WHERE id = %s", (json.dumps(participants), self.giveaway_id))
        conn.commit()
        conn.close()

        bonus_msg = f" You qualified for bonus roles and got **{total_entries} entries** total! 🎉" if total_entries > 1 else ""
        await interaction.response.send_message(f"✅ You've entered! Good luck 🍀{bonus_msg}", ephemeral=True)

    @ui.button(label="Participants", style=discord.ButtonStyle.blurple, emoji="👥", custom_id="ga_view_v2")
    async def view_participants(self, interaction: discord.Interaction, button: ui.Button):
        conn = get_db()
        c    = conn.cursor()
        c.execute("SELECT participants FROM giveaways WHERE id = %s", (self.giveaway_id,))
        ga = c.fetchone()
        conn.close()
        raw   = json.loads(ga["participants"]) if ga and ga["participants"] else []
        count = len(set(raw))
        e = base_embed("👥 Giveaway Participants", color=PRIMARY)
        e.description = f"**{count:,}** participant{'s' if count != 1 else ''} have entered."
        await interaction.response.send_message(embed=e, ephemeral=True)

    @ui.button(label="Extra Entries", style=discord.ButtonStyle.secondary, emoji="🎁", custom_id="ga_extra_v2")
    async def extra(self, interaction: discord.Interaction, button: ui.Button):
        conn = get_db()
        c    = conn.cursor()
        c.execute("SELECT extra_entries FROM giveaways WHERE id = %s", (self.giveaway_id,))
        ga = c.fetchone()
        conn.close()
        extra_entries_data = json.loads(ga["extra_entries"]) if ga and ga["extra_entries"] else []
        e = base_embed("🎁 Bonus Entry Roles", color=ACCENT)
        if not extra_entries_data:
            e.description = "No bonus roles configured for this giveaway.\nEveryone gets **1 entry**."
        else:
            lines = ["**Base:** 1 entry (everyone)\n"]
            for ed in extra_entries_data:
                lines.append(f"<@&{ed['role_id']}> → **+{ed['count']} extra entries**")
            lines.append("\n*Bonuses stack! Having multiple roles gives you all their extra entries combined.*")
            e.description = "\n".join(lines)
        await interaction.response.send_message(embed=e, ephemeral=True)


# ---------------------------------------------------------------------------
# TICKET VIEWS
# ---------------------------------------------------------------------------
class TicketView(ui.View):
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

        app_ticket_ch_id = cfg["application_ticket_channel_id"] if cfg else None
        ticket = await create_ticket_thread(
            guild=guild,
            member=member,
            name=f"apply-{member.name[:12].lower()}",
            topic_embed=e,
            view=TicketCloseView(),
            cfg=cfg,
            override_channel_id=app_ticket_ch_id,
        )
        await interaction.response.send_message(f"✅ Support ticket created: {ticket.mention}", ephemeral=True)


class TicketCloseView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket_close_v2")
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        e = base_embed("🔒 Closing Ticket", color=DANGER)
        e.description = "This ticket will be closed in **5 seconds**. Generating transcript..."
        await interaction.response.send_message(embed=e)

        channel = interaction.channel
        guild   = interaction.guild

        transcript_lines = []
        try:
            async for msg in channel.history(limit=500, oldest_first=True):
                ts          = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
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
        c.execute("SELECT * FROM orders WHERE ticket_channel_id = %s ORDER BY created_at DESC LIMIT 1", (channel.id,))
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
                details          = _build_order_details_str(
                    order["order_type"] or "ranked",
                    order["from_tier"] or "",
                    order["to_tier"] or "",
                    order["service_type"] or "boost"
                )
                log_e.add_field(name="🧾 Order ID",     value=f"`{order['id']}`", inline=True)
                log_e.add_field(name="👤 Customer",      value=customer_mention,  inline=True)
                log_e.add_field(name="🟠 Booster",       value=booster_mention,   inline=True)
                log_e.add_field(name="📦 Order Details", value=details,           inline=True)
                log_e.add_field(name="🔖 Status",        value=order["status"],   inline=True)

            await log_ch.send(embed=log_e, file=transcript_file)

        # Remove from activity tracking
        remove_ticket_activity(channel.id)

        button.disabled = True
        await asyncio.sleep(5)
        try:
            if isinstance(channel, discord.Thread):
                if channel.archived:
                    await channel.edit(archived=False)
            await channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.Forbidden:
            await channel.send("❌ Bot is missing **Manage Threads** permission.")
        except Exception as ex:
            await channel.send(f"❌ Failed to delete: `{ex}`")

    @ui.button(label="Send Vouch Panel", style=discord.ButtonStyle.success, emoji="⭐", custom_id="ticket_send_vouch_v2")
    async def send_vouch(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ Staff only.", ephemeral=True)
            return
        ch_name    = getattr(interaction.channel, "name", "") or ""
        order_kind = "prestige" if "prestige" in ch_name else "ranked"

        e = base_embed("⭐ Leave a Vouch", color=GOLD)
        e.description = (
            "Thank you for your order! We'd love your feedback.\n\n"
            "📸 Attach a screenshot as proof\n"
            "⭐ Rate your experience (1-5)\n"
            "💬 Leave honest feedback\n\n"
            "Click the button below to submit."
        )
        await interaction.channel.send(embed=e, view=VouchButtonView(order_kind=order_kind))
        await interaction.response.send_message("✅ Vouch panel sent.", ephemeral=True)


# ---------------------------------------------------------------------------
# ACCOUNT SALE MODAL
# ---------------------------------------------------------------------------
class AccountSaleModal(ui.Modal, title="Post Account For Sale"):
    game        = ui.TextInput(label="Game / Account Type",       placeholder="Brawl Stars",                        style=discord.TextStyle.short)
    description = ui.TextInput(label="Account Description",       placeholder="Masters rank, 50 maxed brawlers...", style=discord.TextStyle.long, max_length=600)
    price       = ui.TextInput(label="Price (EUR)",               placeholder="49.99",                              style=discord.TextStyle.short)
    image_url   = ui.TextInput(label="Screenshot URL",            placeholder="https://i.imgur.com/...",            style=discord.TextStyle.short)
    contact     = ui.TextInput(label="Contact / Purchase Method", placeholder="DM this account / open a ticket",   style=discord.TextStyle.short, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            price_val = float(self.price.value.replace("€", "").strip())
        except ValueError:
            await interaction.followup.send("❌ Invalid price. Please enter a number like `49.99`.", ephemeral=True)
            return

        guild = interaction.guild
        cfg   = get_config(guild.id)
        sale_ch_id        = cfg["account_sale_channel_id"] if cfg else None
        acct_ticket_ch_id = cfg["account_sale_ticket_channel_id"] if cfg else None
        sale_ch           = guild.get_channel(sale_ch_id) if sale_ch_id else interaction.channel

        conn = get_db()
        c    = conn.cursor()
        c.execute(
            "INSERT INTO account_listings (guild_id, seller_id, game, description, price, contact, image_url) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (guild.id, interaction.user.id, self.game.value, self.description.value,
             price_val, self.contact.value or "Open a ticket or DM staff", self.image_url.value.strip())
        )
        listing_number = c.fetchone()["id"]
        conn.commit()
        conn.close()

        e = base_embed(f"🛒 Account For Sale — {self.game.value}", color=GOLD)
        e.set_author(name=f"Account #{listing_number}", icon_url=guild.icon.url if guild.icon else discord.Embed.Empty)
        e.description = self.description.value
        e.add_field(name="🎮 Game",        value=self.game.value,                                    inline=True)
        e.add_field(name="💰 Price",       value=f"**€{price_val:.2f}**",                           inline=True)
        e.add_field(name="🆔 Listing #",   value=f"**#{listing_number}**",                          inline=True)
        e.add_field(name="📩 To Purchase", value=self.contact.value or "Open a ticket or DM staff", inline=True)
        e.set_footer(text=f"{FOOTER_BRAND} | Account #{listing_number}")

        wm_file = None
        img = self.image_url.value.strip()
        if img:
            wm_file = await fetch_and_watermark(img)
            if wm_file:
                e.set_image(url="attachment://proof.jpg")

        buy_view = AccountBuyView(listing_number)
        if wm_file:
            await sale_ch.send(embed=e, file=wm_file, view=buy_view)
        else:
            await sale_ch.send(embed=e, view=buy_view)

        await interaction.followup.send(f"✅ Account **#{listing_number}** posted in {sale_ch.mention}.", ephemeral=True)

class AccountBuyView(ui.View):
    def __init__(self, listing_id: int):
        super().__init__(timeout=None)
        self.listing_id = listing_id

    @ui.button(label="Buy This Account", style=discord.ButtonStyle.success, emoji="🛒", custom_id="acct_buy_btn_v1")
    async def buy(self, interaction: discord.Interaction, button: ui.Button):
        # Build unique custom_id per listing at runtime — see on_ready registration
        guild  = interaction.guild
        member = interaction.user
        cfg    = get_config(guild.id)

        conn = get_db()
        c    = conn.cursor()
        c.execute("SELECT * FROM account_listings WHERE id = %s", (self.listing_id,))
        listing = c.fetchone()
        conn.close()

        if not listing or listing["status"] != "available":
            await interaction.response.send_message("❌ This account is no longer available.", ephemeral=True)
            return

        sale_ch_id = cfg["account_sale_channel_id"] if cfg else None
        sale_ch    = guild.get_channel(sale_ch_id) if sale_ch_id else interaction.channel

        e = base_embed(f"🛒 Account Purchase — {listing['game']}", color=GOLD)
        e.description = (
            f"Welcome, {member.mention}!\n\n"
            f"You're interested in purchasing this account:\n\n"
            f"🎮 **Game:** {listing['game']}\n"
            f"💰 **Price:** **€{listing['price']:.2f}**\n"
            f"📋 **Description:** {listing['description']}\n"
            f"🆔 **Listing #:** {listing['id']}\n\n"
            "Staff will be with you shortly to finalize the purchase.\n"
            "Please have your payment ready!"
        )
        e.set_author(name=member.display_name, icon_url=member.display_avatar.url)

        try:
            thread = await create_ticket_thread(
                guild=guild,
                member=member,
                name=f"purchase-{listing['game'][:20].lower().replace(' ', '-')}-{member.name[:10].lower()}",
                topic_embed=e,
                view=TicketCloseView(),
                cfg=cfg,
                override_channel_id=acct_ticket_ch_id or sale_ch_id,
            )
        except Exception as err:
            await interaction.response.send_message(
                f"❌ Could not create purchase thread: `{err}`", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✅ Purchase thread created: {thread.mention}", ephemeral=True
        )

# ---------------------------------------------------------------------------
# BACKUP SYSTEM
# ---------------------------------------------------------------------------
OAUTH_AUTHORIZE_URL = os.getenv("OAUTH_AUTHORIZE_URL", "https://worker-production-e219.up.railway.app/authorize")
OAUTH_BACKEND_URL   = os.getenv("OAUTH_BACKEND_URL",   "https://worker-production-e219.up.railway.app")
RESTORE_SECRET      = os.getenv("RESTORE_SECRET", "MySecret999")

class BackupPanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ui.Button(
            label="🛡️ Secure Backup Access",
            style=discord.ButtonStyle.link,
            url=OAUTH_AUTHORIZE_URL,
            emoji="🔒"
        ))


# ---------------------------------------------------------------------------
# BOOSTER AVAILABILITY VIEW
# ---------------------------------------------------------------------------
class AvailabilityView(ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @ui.button(label="🟢 Available", style=discord.ButtonStyle.success, custom_id="avail_available")
    async def set_available(self, interaction: discord.Interaction, button: ui.Button):
        set_booster_status(interaction.user.id, interaction.guild_id, "available")
        e = base_embed("✅ Status Updated", color=SUCCESS)
        e.description = "Your status is now set to **🟢 Available**.\nYou can now claim new boost orders."
        await interaction.response.edit_message(embed=e, view=None)

    @ui.button(label="🟡 Busy", style=discord.ButtonStyle.secondary, custom_id="avail_busy")
    async def set_busy(self, interaction: discord.Interaction, button: ui.Button):
        set_booster_status(interaction.user.id, interaction.guild_id, "busy")
        e = base_embed("🟡 Status Updated", color=GOLD)
        e.description = "Your status is now set to **🟡 Busy**.\nYou won't be able to claim new orders until you set yourself as Available."
        await interaction.response.edit_message(embed=e, view=None)

    @ui.button(label="🔴 Offline", style=discord.ButtonStyle.danger, custom_id="avail_offline")
    async def set_offline(self, interaction: discord.Interaction, button: ui.Button):
        set_booster_status(interaction.user.id, interaction.guild_id, "offline")
        e = base_embed("🔴 Status Updated", color=DANGER)
        e.description = "Your status is now set to **🔴 Offline**.\nYou won't be able to claim orders until you change your status."
        await interaction.response.edit_message(embed=e, view=None)


# ---------------------------------------------------------------------------
# MESSAGE LISTENER — update ticket activity
# ---------------------------------------------------------------------------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.guild and message.channel:
        update_ticket_activity(message.channel.id, message.guild.id)
    await bot.process_commands(message)


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
    account_sale_ticket_channel="Channel where account purchase ticket threads are created",
    booster_role="Role given to boosters (used for leaderboard filtering)",
    proof_channel="Channel where proof screenshots are posted",
    inactive_ticket_hours="Hours of inactivity before ticket warning (default: 24)",
    application_ticket_channel="Channel where application ticket threads are created",
    carrier_role="Role given to carriers",
    ticket_support_roles="Up to 6 support roles for tickets, separated by commas (role IDs or mentions)",
    reviewer_roles="Roles allowed to review applications, separated by commas",
)

@app_commands.checks.has_permissions(administrator=True)
async def setup(
    interaction: discord.Interaction,
    vouch_channel: discord.abc.GuildChannel = None,
    ticket_channel: discord.abc.GuildChannel = None,
    ticket_category: discord.CategoryChannel = None,
    completed_channel: discord.abc.GuildChannel = None,
    ranked_ticket_channel: discord.abc.GuildChannel = None,
    prestige_ticket_channel: discord.abc.GuildChannel = None,
    ranked_panel_channel: discord.abc.GuildChannel = None,
    prestige_panel_channel: discord.abc.GuildChannel = None,
    owner: discord.Member = None,
    ticket_log_channel: discord.abc.GuildChannel = None,
    application_channel: discord.abc.GuildChannel = None,
    application_review_channel: discord.abc.GuildChannel = None,
    account_sale_channel: discord.abc.GuildChannel = None,
    account_sale_ticket_channel: discord.abc.GuildChannel = None,
    booster_role: discord.Role = None,
    proof_channel: discord.abc.GuildChannel = None,
    inactive_ticket_hours: int = None,
    application_ticket_channel: discord.abc.GuildChannel = None,
    carrier_role: discord.Role = None,
    ticket_support_roles: str = None,
    reviewer_roles: str = None,
):

    updates = {}
    if vouch_channel:              updates["vouch_channel_id"]              = vouch_channel.id
    if ticket_channel:             updates["ticket_channel_id"]             = ticket_channel.id
    if ticket_category:            updates["ticket_category_id"]            = ticket_category.id
    if completed_channel:          updates["completed_channel_id"]          = completed_channel.id
    if ranked_ticket_channel:      updates["ranked_ticket_channel_id"]      = ranked_ticket_channel.id
    if prestige_ticket_channel:    updates["prestige_ticket_channel_id"]    = prestige_ticket_channel.id
    if ranked_panel_channel:       updates["ranked_panel_channel_id"]       = ranked_panel_channel.id
    if prestige_panel_channel:     updates["prestige_panel_channel_id"]     = prestige_panel_channel.id
    if owner:                      updates["owner_id"]                      = owner.id
    if ticket_log_channel:         updates["ticket_log_channel_id"]         = ticket_log_channel.id
    if application_channel:        updates["application_channel_id"]        = application_channel.id
    if application_review_channel: updates["application_review_channel_id"] = application_review_channel.id
    if account_sale_channel:       updates["account_sale_channel_id"]       = account_sale_channel.id
    if account_sale_ticket_channel: updates["account_sale_ticket_channel_id"] = account_sale_ticket_channel.id
    if booster_role:               updates["booster_role_id"]               = booster_role.id
    if proof_channel:              updates["proof_channel_id"]              = proof_channel.id
    if inactive_ticket_hours is not None: updates["inactive_ticket_hours"]  = inactive_ticket_hours
    if application_ticket_channel: updates["application_ticket_channel_id"] = application_ticket_channel.id
    if carrier_role:               updates["carrier_role_id"]               = carrier_role.id
    if ticket_support_roles:
        roles_list = [r.strip() for r in ticket_support_roles.split(",") if r.strip()]
        if len(roles_list) > 6:
            await interaction.response.send_message("❌ You can only set up to 6 ticket support roles.", ephemeral=True)
            return
        updates["ticket_support_roles"] = ticket_support_roles

    if reviewer_roles:             updates["reviewer_roles"]                = reviewer_roles
    if updates:
        set_config(interaction.guild.id, **updates)

    e = base_embed("⚙️ Server Configuration", color=SUCCESS)
    e.description = "Bot settings updated successfully."
    if vouch_channel:              e.add_field(name="⭐ Vouch Channel",                value=vouch_channel.mention,              inline=True)
    if ticket_channel:             e.add_field(name="🎫 Fallback Ticket Channel",      value=ticket_channel.mention,             inline=True)
    if ticket_category:            e.add_field(name="📂 Ticket Category",              value=ticket_category.mention,            inline=True)
    if completed_channel:          e.add_field(name="✅ Completed Channel",            value=completed_channel.mention,          inline=True)
    if ranked_ticket_channel:      e.add_field(name="🔥 Ranked Ticket Channel",        value=ranked_ticket_channel.mention,      inline=True)
    if prestige_ticket_channel:    e.add_field(name="✨ Prestige Ticket Channel",      value=prestige_ticket_channel.mention,    inline=True)
    if ranked_panel_channel:       e.add_field(name="📢 Ranked Claiming Channel",      value=ranked_panel_channel.mention,       inline=True)
    if prestige_panel_channel:     e.add_field(name="📢 Prestige Claiming Channel",    value=prestige_panel_channel.mention,     inline=True)
    if owner:                      e.add_field(name="👑 Owner",                        value=owner.mention,                      inline=True)
    if ticket_log_channel:         e.add_field(name="📋 Ticket Log Channel",           value=ticket_log_channel.mention,         inline=True)
    if application_channel:        e.add_field(name="📝 Application Channel",          value=application_channel.mention,        inline=True)
    if application_review_channel: e.add_field(name="🔍 Application Review Channel",  value=application_review_channel.mention, inline=True)
    if account_sale_channel:       e.add_field(name="🛒 Account Sale Channel",         value=account_sale_channel.mention,       inline=True)
    if account_sale_ticket_channel: e.add_field(name="🛒 Account Ticket Channel", value=account_sale_ticket_channel.mention, inline=True)
    if booster_role:               e.add_field(name="🟠 Booster Role",                value=booster_role.mention,               inline=True)
    if proof_channel:              e.add_field(name="📸 Proof Channel",               value=proof_channel.mention,              inline=True)
    if inactive_ticket_hours:      e.add_field(name="⏰ Inactive Ticket Hours",        value=str(inactive_ticket_hours),         inline=True)
    if application_ticket_channel:     e.add_field(name="📝 Application Ticket Channel",  value=application_ticket_channel.mention,      inline=True)
    if carrier_role:               e.add_field(name="🚗 Carrier Role",            value=carrier_role.mention,      inline=True)
    if ticket_support_roles:       e.add_field(name="🎫 Ticket Support Roles",    value=ticket_support_roles,      inline=True)
    if reviewer_roles:             e.add_field(name="🔍 Reviewer Roles",          value=reviewer_roles,            inline=True)

    e.add_field(
        name="ℹ️ Order Flow",
        value=(
            "1️⃣ Customer clicks **Ranked/Prestige Boost** → price estimate shown → ticket opens\n"
            "2️⃣ Staff click **📢 Publish to Boosters** → set earnings → card appears in claiming channel\n"
            "3️⃣ Booster clicks **🟠 Claim This Boost** → instantly added to the customer's ticket\n"
            "4️⃣ On completion, customer receives a DM to rate the booster"
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


@bot.tree.command(name="ranked_panel", description="Post the Ranked Boost order panel in this channel")
@app_commands.describe(image_url="Image URLs separated by commas")
@app_commands.checks.has_permissions(manage_channels=True)
async def ranked_panel(interaction: discord.Interaction, image_url: str = None):
    rank_icons = " ".join(RANK_EMOJI.values())
    e = base_embed("🔥 Ranked Boost", color=PRIMARY)
    e.description = (
        "Climb the ranks! Click the button below to place your **Ranked Boost** order.\n\n"
        f"{rank_icons}\n\n"
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

    await interaction.channel.send(embeds=[e] + extra_embeds, view=RankedPanelButton())
    await interaction.response.send_message("✅ Ranked Boost panel posted.", ephemeral=True)


@bot.tree.command(name="prestige_panel", description="Post the Prestige Boost order panel in this channel")
@app_commands.describe(image_url="Image URLs separated by commas")
@app_commands.checks.has_permissions(manage_channels=True)
async def prestige_panel(interaction: discord.Interaction, image_url: str = None):
    pres_icons = " ".join(PRESTIGE_EMOJI.values())
    e = base_embed("✨ Prestige Boost", color=ACCENT)
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

    await interaction.channel.send(embeds=[e] + extra_embeds, view=PrestigePanelButton())
    await interaction.response.send_message("✅ Prestige Boost panel posted.", ephemeral=True)


@bot.tree.command(name="ticket_panel", description="Post the combined support & application panel in this channel")
@app_commands.describe(image_url="Optional banner image URL")
@app_commands.checks.has_permissions(manage_channels=True)
async def ticket_panel(interaction: discord.Interaction, image_url: str = None):
    cfg   = get_config(interaction.guild.id)
    title = cfg["ticket_panel_title"] if cfg and cfg["ticket_panel_title"] else "🎫 Support Center"
    desc  = (cfg["ticket_panel_desc"] if cfg and cfg["ticket_panel_desc"]
             else "Need help or want to join the team? Use the buttons below.\n\n📌 Tickets are private and handled by staff only.")
    e = discord.Embed(title=title, color=PRIMARY, description=desc)
    e.add_field(
        name="🎫 Support",
        value="Click **General Support** to open a ticket with our staff.",
        inline=False
    )
    e.add_field(
        name="📝 Applications",
        value=(
            "🟠 **Booster** — Masters III minimum\n"
            "🛡️ **Admin** — Trustworthy & fluent in English\n"
            "📰 **Reporter** — Active moderator & issue reporter"
        ),
        inline=False
    )
    if image_url:
        e.set_image(url=image_url)
    e.set_footer(text=FOOTER_BRAND)
    e.timestamp = datetime.utcnow()
    await interaction.channel.send(embed=e, view=CombinedPanelView())
    await interaction.response.send_message("✅ Combined panel posted.", ephemeral=True)

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
    e = base_embed("⭐ Leave a Vouch", color=GOLD)
    e.description = (
        "Thank you for your order! We'd love your feedback.\n\n"
        "📸 Attach a screenshot as proof\n"
        "⭐ Rate your experience (1-5)\n"
        "💬 Leave honest feedback\n\n"
        "Click the button below to submit."
    )
    view = VouchButtonView(order_kind=ok)
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
    prize="Prize name",
    hours="Duration in hours",
    winners="Number of winners",
    description="Giveaway description or rules",
    ping="Who to ping: @everyone, @here, a role mention, or none",
    image_url="Optional banner image URL",
    role_1="Bonus role 1", entries_1="Extra entries for role 1 (e.g. 2 = 3 total with base)",
    role_2="Bonus role 2", entries_2="Extra entries for role 2 (e.g. 2 = 3 total with base)",
    role_3="Bonus role 3", entries_3="Extra entries for role 3 (e.g. 2 = 3 total with base)",
    role_4="Bonus role 4", entries_4="Extra entries for role 4 (e.g. 2 = 3 total with base)",
    role_5="Bonus role 5", entries_5="Extra entries for role 5 (e.g. 2 = 3 total with base)",
    role_6="Bonus role 6", entries_6="Extra entries for role 6 (e.g. 2 = 3 total with base)",
    role_7="Bonus role 7", entries_7="Extra entries for role 7 (e.g. 2 = 3 total with base)",
    role_8="Bonus role 8", entries_8="Extra entries for role 8 (e.g. 2 = 3 total with base)",
)
@app_commands.checks.has_permissions(manage_channels=True)
async def giveaway(
    interaction: discord.Interaction,
    prize: str,
    hours: int,
    winners: int,
    description: str,
    ping: str = "@everyone",
    image_url: str = None,
    role_1: discord.Role = None, entries_1: int = 1,
    role_2: discord.Role = None, entries_2: int = 1,
    role_3: discord.Role = None, entries_3: int = 1,
    role_4: discord.Role = None, entries_4: int = 1,
    role_5: discord.Role = None, entries_5: int = 1,
    role_6: discord.Role = None, entries_6: int = 1,
    role_7: discord.Role = None, entries_7: int = 1,
    role_8: discord.Role = None, entries_8: int = 1,
):
    role_pairs = [
        (role_1, entries_1), (role_2, entries_2), (role_3, entries_3),
        (role_4, entries_4), (role_5, entries_5), (role_6, entries_6),
        (role_7, entries_7), (role_8, entries_8),
    ]
    extra_entries_data = [
        {"role_id": r.id, "count": max(1, e)}
        for r, e in role_pairs if r is not None
    ]
    extra_entries_json = json.dumps(extra_entries_data) if extra_entries_data else None

    conn    = get_db()
    c       = conn.cursor()
    ga_id   = f"G{uuid.uuid4().hex[:8].upper()}"
    ends_at = datetime.utcnow() + timedelta(hours=hours)
    c.execute(
"INSERT INTO giveaways (id, prize, description, winners, hosted_by, participants, image_url, extra_entries, ping, bonus_role_id, ended_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",        (ga_id, prize, description, winners, interaction.user.id, "[]", image_url, extra_entries_json, ping, None, ends_at)
    )
    conn.commit()
    conn.close()

    end_ts = int(ends_at.timestamp())
    e = discord.Embed(title=f"🎁 {prize}", color=PRIMARY)
    e.add_field(name="ℹ️ Description", value=description, inline=False)
    e.add_field(name="⏰ Ends",        value=f"<t:{end_ts}:F>  (<t:{end_ts}:R>)", inline=False)
    e.add_field(name="🏆 Winners",     value=f"**{winners}** winner{'s' if winners != 1 else ''}", inline=True)
    e.add_field(name="👥 Participants", value="**0** entered", inline=True)
    e.add_field(name="🎯 Hosted By",   value=interaction.user.mention, inline=True)
    if extra_entries_data:
        bonus_lines = "\n".join(f"<@&{ed['role_id']}> → **+{ed['count']} extra entries**" for ed in extra_entries_data)
        e.add_field(name="🎁 Bonus Entries", value=bonus_lines, inline=False)
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
    c.execute("SELECT * FROM giveaways WHERE id = %s", (giveaway_id,))
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
    c.execute("UPDATE giveaways SET winner_ids = %s WHERE id = %s", (json.dumps(winner_ids), giveaway_id))
    conn.commit()
    conn.close()
    winner_mentions = " ".join([f"<@{w}>" for w in winner_ids])
    e = discord.Embed(title=f"🎁 {ga['prize']} — Giveaway Ended", color=SUCCESS)
    e.add_field(name="🏆 Winners",            value=winner_mentions,               inline=False)
    e.add_field(name="👥 Total Participants", value=f"**{len(set(participants)):,}**", inline=True)
    e.add_field(name="🆔 Giveaway ID",        value=f"`{giveaway_id}`",            inline=True)
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
    c.execute("SELECT COUNT(*) as count, SUM(price) as total FROM orders WHERE user_id = %s", (target.id,))
    row = c.fetchone()
    c.execute("SELECT COUNT(*) as vc FROM vouchers WHERE used_by = %s", (target.id,))
    vc = c.fetchone()
    conn.close()
    e = base_embed(f"📊 {target.display_name}'s Stats", color=PRIMARY)
    e.set_thumbnail(url=target.display_avatar.url)
    e.add_field(name="🎮 Total Orders", value=f"**{row['count'] or 0}**", inline=True)
    e.add_field(name="💰 Total Spent",  value=f"**€{row['total']:.2f}**" if row["total"] else "**€0.00**", inline=True)
    e.add_field(name="⭐ Vouches",      value=f"**{vc['vc'] or 0}**", inline=True)
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="booster_stats", description="View booster statistics for a user")
@app_commands.describe(user="Booster to look up (defaults to you)")
async def booster_stats(interaction: discord.Interaction, user: discord.User = None):
    target = user or interaction.user
    conn   = get_db()
    c      = conn.cursor()
    c.execute(
        "SELECT COUNT(*) as completed, SUM(booster_earnings) as total_earnings, AVG(booster_rating) as avg_rating FROM orders WHERE booster_id = %s AND status = 'completed'",
        (target.id,)
    )
    row = c.fetchone()
    c.execute(
        "SELECT COUNT(*) as active FROM orders WHERE booster_id = %s AND status = 'claimed'",
        (target.id,)
    )
    active_row = c.fetchone()
    c.execute(
        "SELECT AVG(completion_time_seconds) as avg_time FROM orders WHERE booster_id = %s AND status = 'completed' AND completion_time_seconds IS NOT NULL",
        (target.id,)
    )
    time_row = c.fetchone()
    conn.close()

    completed      = row["completed"] or 0
    total_earnings = row["total_earnings"] or 0.0
    active         = active_row["active"] or 0
    avg_rating     = row["avg_rating"]
    avg_time       = time_row["avg_time"]

    status_icon = {"available": "🟢", "busy": "🟡", "offline": "🔴"}.get(get_booster_status(target.id), "⚪")

    e = base_embed(f"📊 Booster Stats — {target.display_name}", color=ACCENT)
    e.set_thumbnail(url=target.display_avatar.url)
    e.add_field(name="✅ Completed Orders",  value=f"**{completed}**",                                  inline=True)
    e.add_field(name="💰 Total Earnings",    value=f"**€{total_earnings:.2f}**",                        inline=True)
    e.add_field(name="🔄 Active Orders",     value=f"**{active}**",                                    inline=True)
    e.add_field(name="⭐ Avg Rating",        value=f"**{avg_rating:.1f}/5**" if avg_rating else "N/A", inline=True)
    e.add_field(name="⏱ Avg Order Time",    value=format_duration(int(avg_time)) if avg_time else "N/A", inline=True)
    e.add_field(name=f"{status_icon} Status", value=get_booster_status(target.id).capitalize(),        inline=True)
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="leaderboard", description="View the booster leaderboard")
@app_commands.describe(sort_by="Sort by: orders, earnings, or rating (default: earnings)")
async def leaderboard(interaction: discord.Interaction, sort_by: str = "earnings"):
    sort_by = sort_by.lower()
    if sort_by not in ("orders", "earnings", "rating"):
        sort_by = "earnings"

    order_by_map = {
        "orders":   "completed DESC",
        "earnings": "total_earnings DESC",
        "rating":   "avg_rating DESC",
    }

    conn = get_db()
    c    = conn.cursor()
    c.execute(f"""
        SELECT
            booster_id,
            COUNT(*) as completed,
            SUM(booster_earnings) as total_earnings,
            AVG(booster_rating) as avg_rating
        FROM orders
        WHERE status = 'completed' AND booster_id IS NOT NULL
        GROUP BY booster_id
        ORDER BY {order_by_map[sort_by]}
        LIMIT 10
    """)
    rows = c.fetchall()
    conn.close()

    medals = ["🥇", "🥈", "🥉"]
    lines  = []
    for i, row in enumerate(rows):
        medal    = medals[i] if i < 3 else f"**#{i+1}**"
        member   = interaction.guild.get_member(row["booster_id"])
        name     = member.display_name if member else f"User {row['booster_id']}"
        earnings = row["total_earnings"] or 0.0
        rating   = f" | ⭐ {row['avg_rating']:.1f}" if row["avg_rating"] else ""
        status_icon = {"available": "🟢", "busy": "🟡", "offline": "🔴"}.get(get_booster_status(row["booster_id"]), "⚪")
        lines.append(
            f"{medal} {status_icon} **{name}** — {row['completed']} orders — €{earnings:.2f}{rating}"
        )

    e = base_embed("🏆 Booster Leaderboard", color=GOLD)
    e.description = "\n".join(lines) if lines else "No completed orders yet."
    e.set_footer(text=f"{FOOTER_BRAND} | Sorted by {sort_by}")
    await interaction.response.send_message(embed=e)


@bot.tree.command(name="availability", description="Set your booster availability status")
async def availability(interaction: discord.Interaction):
    current = get_booster_status(interaction.user.id)
    status_map = {"available": "🟢 Available", "busy": "🟡 Busy", "offline": "🔴 Offline"}
    e = base_embed("🔄 Set Availability", color=PRIMARY)
    e.description = (
        f"Your current status: **{status_map.get(current, current)}**\n\n"
        "Select your new availability status below."
    )
    await interaction.response.send_message(embed=e, view=AvailabilityView(), ephemeral=True)


@bot.tree.command(name="my_orders", description="View your order history as a booster")
@app_commands.describe(filter_by="all, active, or completed (default: all)")
async def my_orders(interaction: discord.Interaction, filter_by: str = "all"):
    filter_by = filter_by.lower()
    conn = get_db()
    c    = conn.cursor()

    if filter_by == "active":
        c.execute("SELECT * FROM orders WHERE booster_id = %s AND status = 'claimed' ORDER BY claimed_at DESC", (interaction.user.id,))
    elif filter_by == "completed":
        c.execute("SELECT * FROM orders WHERE booster_id = %s AND status = 'completed' ORDER BY completed_at DESC LIMIT 20", (interaction.user.id,))
    else:
        c.execute("SELECT * FROM orders WHERE booster_id = %s ORDER BY created_at DESC LIMIT 20", (interaction.user.id,))

    orders = c.fetchall()
    c.execute("SELECT SUM(booster_earnings) as total FROM orders WHERE booster_id = %s AND status = 'completed'", (interaction.user.id,))
    total_row = c.fetchone()
    conn.close()

    total_earnings = total_row["total"] or 0.0

    e = base_embed(f"📋 My Orders — {interaction.user.display_name}", color=ACCENT)

    if not orders:
        e.description = "No orders found."
    else:
        lines = []
        for o in orders:
            status_icon = {"pending": "🕐", "claimed": "🟡", "completed": "✅"}.get(o["status"], "❓")
            details = _build_order_details_str(
                o["order_type"] or "ranked", o["from_tier"] or "", o["to_tier"] or "", o["service_type"] or "boost"
            )
            earnings = f" | €{o['booster_earnings']:.2f}" if o["booster_earnings"] else ""
            time_str = ""
            if o["completion_time_seconds"]:
                time_str = f" | ⏱ {format_duration(o['completion_time_seconds'])}"
            lines.append(f"{status_icon} `{o['id']}` — {details}{earnings}{time_str}")

        e.description = "\n".join(lines)

    e.add_field(name="💰 Total Earned", value=f"**€{total_earnings:.2f}**", inline=True)
    e.add_field(name="📊 Shown",        value=f"**{len(orders)}** orders",  inline=True)
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="price_estimate", description="Get a price estimate for a ranked boost order")
@app_commands.describe(
    from_rank="Starting rank",
    to_rank="Desired rank (minimum Diamond I)",
    p11="Number of Power 11 brawlers",
    service_type="boost or carry"
)
async def price_estimate(
    interaction: discord.Interaction,
    from_rank: str,
    to_rank: str,
    p11: str = "41-50",
    service_type: str = "boost"
):
    # Validate ranks
    if from_rank not in ALL_RANKS:
        opts = ", ".join(ALL_RANKS)
        await interaction.response.send_message(f"❌ Invalid from_rank. Valid options: {opts}", ephemeral=True)
        return

    valid_desired = DESIRED_RANKS + ["Pro"]
    if to_rank not in valid_desired:
        await interaction.response.send_message(
            f"❌ Invalid to_rank. Must be Diamond I or higher.", ephemeral=True
        )
        return

    try:
        fi = ALL_RANKS.index(from_rank)
    except ValueError:
        fi = -1

    try:
        ti = ALL_RANKS.index(to_rank)
    except ValueError:
        ti = len(ALL_RANKS)  # Pro

    if to_rank != "Pro" and ti <= fi:
        await interaction.response.send_message(
            f"❌ Desired rank **{to_rank}** must be higher than current rank **{from_rank}**.", ephemeral=True
        )
        return

    service_type = service_type.lower()
    if service_type not in ("boost", "carry"):
        service_type = "boost"

    est = calculate_rank_price(from_rank, to_rank, p11, service_type, interaction.guild_id)
    fe  = rank_emoji(from_rank)
    te  = rank_emoji(to_rank)

    e = base_embed("💡 Price Estimate", color=GOLD)
    e.description = (
        f"**Estimated price for your boost:**\n\n"
        f"📦 **Route:** {fe} `{from_rank}` → {te} `{to_rank}`\n"
        f"{P11_EMOJI} **P11 Brawlers:** {p11}\n"
        f"🛠 **Service:** {'Carry 🔴 (2x)' if service_type == 'carry' else 'Boost 🟢'}\n\n"
        f"💰 **Estimated Price: €{est:.2f}**\n\n"
        "*Note: Final price is set by staff after reviewing your account.*"
    )
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="set_rank_price", description="Set a custom price for a specific rank boost route")
@app_commands.describe(
    from_rank="Starting rank",
    to_rank="Desired rank",
    price="Base price in EUR"
)
@app_commands.checks.has_permissions(manage_channels=True)
async def set_rank_price(interaction: discord.Interaction, from_rank: str, to_rank: str, price: float):
    conn = get_db()
    c    = conn.cursor()
    c.execute(
        """INSERT INTO rank_prices (guild_id, from_rank, to_rank, base_price) VALUES (%s, %s, %s, %s)
           ON CONFLICT (guild_id, from_rank, to_rank) DO UPDATE SET base_price = EXCLUDED.base_price""",
        (interaction.guild.id, from_rank, to_rank, price)
    )
    conn.commit()
    conn.close()
    e = base_embed("✅ Rank Price Set", color=SUCCESS)
    e.description = f"**{from_rank}** → **{to_rank}** base price set to **€{price:.2f}**."
    await interaction.response.send_message(embed=e, ephemeral=True)


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

@bot.tree.command(name="backup_panel", description="Post the backup access panel so members can authorize")
@app_commands.checks.has_permissions(administrator=True)
async def backup_panel(interaction: discord.Interaction):
    e = base_embed("🛡️ Secure Your Backup Access", color=DANGER)
    e.description = (
        "If the main server is ever deleted, raided or banned, we will automatically add you to our backup server.\n\n"
        "**Click the button below and authorize with Discord.**\n\n"
        "🔒 We only request:\n"
        "> `identify` — to know who you are\n"
        "> `guilds.join` — to add you to the backup server if needed\n\n"
        "⚠️ You only need to do this once."
    )
    await interaction.channel.send(embed=e, view=BackupPanelView())
    await interaction.response.send_message("✅ Backup panel posted.", ephemeral=True)


@bot.tree.command(name="restore_backup", description="Trigger restore — adds all authorized members to backup server")
@app_commands.describe(backup_server_id="The ID of the backup server to add members to")
@app_commands.checks.has_permissions(administrator=True)
async def restore_backup(interaction: discord.Interaction, backup_server_id: str):
    cfg      = get_config(interaction.guild.id)
    owner_id = cfg["owner_id"] if cfg else None
    if owner_id and interaction.user.id != owner_id:
        await interaction.response.send_message("❌ Only the server owner can trigger a restore.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        import requests as req
        r    = req.post(
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


@bot.tree.command(name="help", description="View all available bot commands")
async def help_cmd(interaction: discord.Interaction):
    rank_icons = " ".join(RANK_EMOJI.values())
    pres_icons = " ".join(PRESTIGE_EMOJI.values())
    e = base_embed("📋 BrawlCarry Bot — Commands", color=PRIMARY)
    e.description = (
        f"**Rank Icons:** {rank_icons}\n"
        f"**Prestige Icons:** {pres_icons}\n\n"
        "**⚙️ Admin Commands**\n"
        "`/setup` — Configure all channels, ticket categories, booster role & owner\n"
        "`/configure_ticket_panel` — Customise support ticket panel text\n"
        "`/ranked_panel` — Post the Ranked Boost intake panel 🔥\n"
        "`/prestige_panel` — Post the Prestige Boost intake panel ✨\n"
        "`/ticket_panel` — Post the General Support ticket panel\n"
        "`/application_panel` — Post the staff application panel\n"
        "`/backup_panel` — Post the backup access panel\n"
        "`/restore_backup` — Trigger backup server restore\n"
        "`/giveaway` — Start a giveaway\n"
        "`/end_giveaway` — End a giveaway and draw winners\n"
        "`/backup_link` — DM all members the backup server link\n\n"
        "**✅ Staff Commands**\n"
        "`/order_complete` — Mark an order as completed\n"
        "`/vouch_panel` — Send vouch panel to user or channel\n"
        "`/post_account` — Post an account for sale\n"
        "`/add_payment_method` — Add a payment method to order forms\n"
        "`/remove_payment_method` — Remove a payment method from order forms\n"
        "`/list_payment_methods` — View all configured payment methods\n"
        "`/set_prestige_price` — Update a prestige boost price\n"
        "`/set_rank_price` — Set a custom price for a rank boost route\n"
        "`/assign_role` — Assign or remove a role from a member\n\n"
        "**👤 User & Booster Commands**\n"
        "`/stats` — View your order statistics\n"
        "`/booster_stats` — View booster completed orders, earnings & rating\n"
        "`/leaderboard` — View the booster leaderboard (sort by orders/earnings/rating)\n"
        "`/availability` — Set your booster availability (Available / Busy / Offline)\n"
        "`/my_orders` — View your order history as a booster\n"
        "`/price_estimate` — Get a price estimate for a ranked boost\n"
        "`/help` — Show this menu\n\n"
        "**📦 Order Flow**\n"
        "1. Customer clicks **Ranked/Prestige Boost** → sees **price estimate** → confirms → ticket opens\n"
        "2. Staff click **📢 Publish to Boosters** → enter booster earnings → claiming card posted\n"
        "3. Booster sets status to **Available** then clicks **🟠 Claim This Boost** → added to ticket\n"
        "4. Staff mark complete → customer receives **rating request** for booster\n\n"
        "**💡 Price Estimation Rules**\n"
        "> 40-50 P11 = baseline price\n"
        "> <40 P11 = slightly higher price (harder boost)\n"
        "> >50 P11 = slightly lower price (easier boost)\n"
        "> Carry = 2x the boost price\n"
        "> Minimum desired rank: **Diamond I**\n\n"
        "**🛠 Service Types**\n"
        "> 🟢 **Boost** — staff play on customer's account (standard price)\n"
        "> 🔴 **Carry** — staff play alongside customer (2x price)"
    )
    await interaction.response.send_message(embed=e, ephemeral=True)


# ---------------------------------------------------------------------------
# GUILD GUARD
# ---------------------------------------------------------------------------
class GuardedTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if ALLOWED_GUILDS and interaction.guild_id not in ALLOWED_GUILDS:
            try:
                await interaction.response.send_message(
                    "❌ This bot is not authorized to operate in this server.", ephemeral=True
                )
            except Exception:
                pass
            return False
        return True

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
# BACKGROUND TASKS
# ---------------------------------------------------------------------------
async def giveaway_reminder_loop():
    await bot.wait_until_ready()
    reminded = {}  # ga_id -> set of labels already sent

    while not bot.is_closed():
        try:
            conn = get_db()
            c    = conn.cursor()
            c.execute("SELECT * FROM giveaways WHERE (winner_ids IS NULL OR winner_ids = '') AND ended_at IS NOT NULL")
            giveaways = c.fetchall()
            conn.close()

            now = datetime.utcnow()
            for ga in giveaways:
                ends_at = ga["ended_at"]
                if not isinstance(ends_at, datetime):
                    continue
                remaining = (ends_at - now).total_seconds()
                if remaining <= 0:
                    continue

                ga_id = ga["id"]
                if ga_id not in reminded:
                    reminded[ga_id] = set()

                reminders = [
                    (86400, 82800, "24h",  "24 hours"),
                    (43200, 39600, "12h",  "12 hours"),
                    (3600,  2400,  "1h",   "1 hour"),
                ]

                triggered_key = None
                triggered_label = None
                for upper, lower, key, label in reminders:
                    if upper >= remaining > lower and key not in reminded[ga_id]:
                        triggered_key = key
                        triggered_label = label
                        break

                if not triggered_key:
                    continue

                # Mark as reminded BEFORE sending to prevent duplicates
                reminded[ga_id].add(triggered_key)

                # Find the giveaway message across all guilds — send ONE reminder only
                sent = False
                for guild in bot.guilds:
                    if sent:
                        break
                    for ch in guild.text_channels:
                        if sent:
                            break
                        try:
                            async for msg in ch.history(limit=100):
                                if (msg.author == guild.me and msg.embeds
                                        and ga_id in (msg.embeds[0].footer.text or "")):
                                    reminder_e = base_embed("⏰ Giveaway Reminder", color=GOLD)
                                    reminder_e.description = (
                                        f"🎁 **{ga['prize']}** giveaway ends in **{triggered_label}**!\n"
                                        f"<t:{int(ends_at.timestamp())}:R>"
                                    )
                                    ping = ga.get("ping", "")
                                    ping_content = ping if (ping and ping.lower() != "none") else ""
                                    await ch.send(
                                        content=ping_content or None,
                                        embed=reminder_e,
                                        allowed_mentions=discord.AllowedMentions(everyone=True, roles=True)
                                    )
                                    sent = True
                                    break
                        except Exception:
                            pass

        except Exception as ex:
            print(f"[WARN] Giveaway reminder loop error: {ex}")

        await asyncio.sleep(300)


async def inactive_ticket_loop():
    """Auto-close tickets that have been inactive past the configured threshold."""
    await bot.wait_until_ready()

    while not bot.is_closed():
        try:
            conn = get_db()
            c    = conn.cursor()
            c.execute("SELECT * FROM ticket_activity")
            tickets = c.fetchall()
            conn.close()

            now = datetime.utcnow()

            for row in tickets:
                guild = bot.get_guild(row["guild_id"])
                if not guild:
                    continue

                cfg = get_config(guild.id)
                threshold_hours = (cfg["inactive_ticket_hours"] if cfg and cfg["inactive_ticket_hours"] else 24)

                last_activity = row["last_activity"]
                if not isinstance(last_activity, datetime):
                    continue

                hours_inactive = (now - last_activity).total_seconds() / 3600
                channel = guild.get_channel(row["channel_id"])
                if not channel:
                    remove_ticket_activity(row["channel_id"])
                    continue

                if hours_inactive >= threshold_hours and not row["warned"]:
                    # Send warning
                    try:
                        warn_e = base_embed("⚠️ Ticket Inactivity Warning", color=GOLD)
                        warn_e.description = (
                            f"This ticket has been inactive for **{int(hours_inactive)}** hours.\n\n"
                            f"If there is no activity within **1 hour**, this ticket will be automatically closed."
                        )
                        await channel.send(embed=warn_e)
                        # Mark as warned
                        conn2 = get_db()
                        c2 = conn2.cursor()
                        c2.execute("UPDATE ticket_activity SET warned = 1 WHERE channel_id = %s", (row["channel_id"],))
                        conn2.commit()
                        conn2.close()
                    except Exception as ex:
                        print(f"[WARN] Could not warn ticket {row['channel_id']}: {ex}")

                elif hours_inactive >= (threshold_hours + 1) and row["warned"]:
                    # Auto-close
                    try:
                        close_e = base_embed("🔒 Ticket Auto-Closed", color=DANGER)
                        close_e.description = "This ticket has been automatically closed due to inactivity."
                        await channel.send(embed=close_e)
                        remove_ticket_activity(row["channel_id"])
                        await asyncio.sleep(3)
                        await channel.delete(reason="Auto-closed due to inactivity")
                    except Exception as ex:
                        print(f"[WARN] Could not auto-close ticket {row['channel_id']}: {ex}")
                        remove_ticket_activity(row["channel_id"])

        except Exception as ex:
            print(f"[WARN] Inactive ticket loop error: {ex}")

        await asyncio.sleep(1800)  # Check every 30 minutes


# ---------------------------------------------------------------------------
# STARTUP
# ---------------------------------------------------------------------------
@bot.event
async def on_ready():
    init_db()
    await bot.tree.sync()
    print(f"[OK] {bot.user} | Slash commands synced")

    bot.add_view(TicketView())
    bot.add_view(TicketCloseView())
    bot.add_view(VouchButtonView())
    bot.add_view(VouchButtonView(order_kind="prestige"))
    bot.add_view(RankedPanelButton())
    bot.add_view(PrestigePanelButton())
    bot.add_view(ApplicationPanelView())
    bot.add_view(CombinedPanelView())
    bot.add_view(BackupPanelView())

    conn = get_db()
    c    = conn.cursor()

    c.execute("SELECT id FROM giveaways WHERE winner_ids IS NULL OR winner_ids = ''")
    for row in c.fetchall():
        bot.add_view(GiveawayView(row["id"]))

    c.execute("SELECT id, ticket_channel_id, order_type FROM orders WHERE status IN ('pending', 'claimed')")
    for row in c.fetchall():
        order_type = row["order_type"] or ("prestige" if str(row["id"]).startswith("PREST") else "ranked")
        bot.add_view(OrderActionsView(row["id"], row["ticket_channel_id"], order_type))
        bot.add_view(BoosterClaimView(row["id"], row["ticket_channel_id"]))

    # Restore booster rating views for recently completed orders (last 7 days)
    c.execute(
        "SELECT id, booster_id FROM orders WHERE status = 'completed' AND booster_rating IS NULL AND completed_at > NOW() - INTERVAL '7 days'"
    )
    for row in c.fetchall():
        if row["booster_id"]:
            bot.add_view(BoosterRatingView(row["id"], row["booster_id"]))

    c.execute("SELECT id FROM account_listings WHERE status = 'available'")
    for row in c.fetchall():
        bot.add_view(AccountBuyView(row["id"]))

    conn.close()
    print(f"[OK] Persistent views registered")

    bot.loop.create_task(giveaway_reminder_loop())
    bot.loop.create_task(inactive_ticket_loop())
    print(f"[OK] Background tasks started")


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("[ERROR] DISCORD_TOKEN not set in environment.")
        exit(1)
    init_db()
    print("[OK] Database initialised")
    bot.run(token)
