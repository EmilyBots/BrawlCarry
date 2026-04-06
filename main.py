import discord
from discord.ext import commands
from discord import app_commands, ui
import json, os, sqlite3, uuid, random, io, aiohttp, asyncio
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

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
    # Migrate: add new columns if they don't exist yet
    for col in ("extra_entries TEXT", "ping TEXT"):
        try:
            c.execute(f"ALTER TABLE giveaways ADD COLUMN {col}")
        except Exception:
            pass
    c.execute("""CREATE TABLE IF NOT EXISTS guild_config (
        guild_id INT PRIMARY KEY,
        vouch_channel_id INT,
        ticket_channel_id INT,
        ticket_panel_title TEXT,
        ticket_panel_desc TEXT
    )""")
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

ALLOWED_CONFIG_KEYS = {"vouch_channel_id", "ticket_channel_id", "ticket_panel_title", "ticket_panel_desc"}

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
# WATERMARK UTILITY
# ---------------------------------------------------------------------------
def watermark_image(image_bytes: bytes, text: str = "Brawl Carry Vouches") -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
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

async def fetch_and_watermark(url: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                raw = await resp.read()
        loop = asyncio.get_event_loop()
        marked = await loop.run_in_executor(None, watermark_image, raw)
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
# RANKED BOOST — RANK OPTIONS
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

P11_OPTIONS = ["0-10", "11-20", "21-30", "31-40", "41-50", "51-60", "61-70", "71+"]

PRESTIGE_OPTIONS = ["Prestige 1 → Prestige 2", "Prestige 2 → Prestige 3"]

# ---------------------------------------------------------------------------
# MODALS
# ---------------------------------------------------------------------------
class OrderModal(ui.Modal, title="Create Carry Order"):
    from_tier = ui.TextInput(
        label="From (Current Rank / Prestige / Tier)",
        placeholder="e.g. Diamond III",
        style=discord.TextStyle.short
    )
    to_tier = ui.TextInput(
        label="To (Target Rank / Prestige / Tier)",
        placeholder="e.g. Masters I",
        style=discord.TextStyle.short
    )
    price = ui.TextInput(
        label="Agreed Price (USD)",
        placeholder="44.99",
        style=discord.TextStyle.short
    )
    method = ui.TextInput(
        label="Payment Method",
        placeholder="PayPal / Bank Transfer / Crypto ...",
        style=discord.TextStyle.short
    )
    image_url = ui.TextInput(
        label="Proof Image URL (optional)",
        placeholder="https://i.imgur.com/...",
        required=False,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price_val = float(self.price.value.replace("$", "").strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid price. Please enter a number like `44.99`.", ephemeral=True
            )
            return

        conn = get_db()
        c = conn.cursor()
        order_id = f"CARRY-{uuid.uuid4().hex[:6].upper()}"
        img = self.image_url.value.strip() if self.image_url.value else None
        c.execute(
            "INSERT INTO orders (id, user_id, from_tier, to_tier, price, method, image_url) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (order_id, interaction.user.id, self.from_tier.value, self.to_tier.value, price_val, self.method.value, img)
        )
        conn.commit()
        conn.close()

        e = base_embed("🚀 New Carry Order", color=PRIMARY)
        e.set_author(name="BrawlCarry | Brawl Stars Boost", icon_url=interaction.user.display_avatar.url)
        e.add_field(name="👤 Customer", value=interaction.user.mention, inline=True)
        e.add_field(name="💵 Amount", value=f"**${price_val:.2f}**", inline=True)
        e.add_field(name="🎮 Type", value="Ranked Boost", inline=True)
        e.add_field(name="📦 Route", value=f"`{self.from_tier.value}` → `{self.to_tier.value}`", inline=False)
        e.add_field(name="💳 Payment", value=self.method.value, inline=True)
        e.add_field(name="🆔 Order ID", value=f"`{order_id}`", inline=True)

        wm_file = None
        if img:
            wm_file = await fetch_and_watermark(img)
            if wm_file:
                e.set_image(url="attachment://proof.jpg")

        view = OrderActionsView(order_id)
        if wm_file:
            await interaction.channel.send(embed=e, view=view, file=wm_file)
        else:
            await interaction.channel.send(embed=e, view=view)
        await interaction.response.send_message("✅ Order submitted!", ephemeral=True)


class VouchModal(ui.Modal, title="Submit Your Vouch"):
    rating = ui.TextInput(
        label="Rating (1–5 stars)",
        placeholder="5",
        min_length=1,
        max_length=1,
        style=discord.TextStyle.short
    )
    amount = ui.TextInput(
        label="Order Amount (USD)",
        placeholder="44.99",
        style=discord.TextStyle.short
    )
    feedback = ui.TextInput(
        label="Your Feedback",
        placeholder="Fast service, very professional...",
        style=discord.TextStyle.long,
        max_length=500
    )
    image_url = ui.TextInput(
        label="Proof Image URL",
        placeholder="https://i.imgur.com/...",
        required=False,
        style=discord.TextStyle.short
    )

    def __init__(self, order_id: str = None):
        super().__init__()
        self.order_id = order_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            stars = max(1, min(5, int(self.rating.value.strip())))
        except ValueError:
            stars = 5

        try:
            amount_val = float(self.amount.value.replace("$", "").strip())
        except ValueError:
            amount_val = 0.0

        img = self.image_url.value.strip() if self.image_url.value else None
        star_str = "⭐" * stars + f"  ({stars}/5)"

        vouch_id = f"VOUCH-{uuid.uuid4().hex[:6].upper()}"
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO vouchers (id, code, amount, used_by, rating, feedback, image_url) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (vouch_id, vouch_id, amount_val, interaction.user.id, stars, self.feedback.value, img)
        )
        conn.commit()
        guild_id = interaction.guild.id if interaction.guild else None
        vouch_ch_id = None
        if guild_id:
            cfg = get_config(guild_id)
            if cfg:
                vouch_ch_id = cfg["vouch_channel_id"]
        conn.close()

        e = base_embed("⭐ New Vouch", color=GOLD)
        e.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        e.add_field(name="👤 Customer", value=interaction.user.mention, inline=True)
        e.add_field(name="💰 Order Amount", value=f"**${amount_val:.2f}**", inline=True)
        e.add_field(name="⭐ Rating", value=star_str, inline=True)
        e.add_field(name="💬 Feedback", value=f"*{self.feedback.value}*", inline=False)
        if self.order_id:
            e.set_footer(text=f"{FOOTER_BRAND} | Order: {self.order_id}")

        wm_file = None
        if img:
            wm_file = await fetch_and_watermark(img)
            if wm_file:
                e.set_image(url="attachment://proof.jpg")

        await interaction.response.send_message(
            "✅ Your vouch has been submitted. Thank you!", ephemeral=True
        )

        if vouch_ch_id and interaction.guild:
            ch = interaction.guild.get_channel(vouch_ch_id)
            if ch:
                if wm_file:
                    await ch.send(embed=e, file=wm_file)
                else:
                    await ch.send(embed=e)


class TicketPanelSetupModal(ui.Modal, title="Configure Ticket Panel"):
    panel_title = ui.TextInput(
        label="Panel Title",
        placeholder="🎫 Support Center",
        default="🎫 Support Center",
        style=discord.TextStyle.short
    )
    panel_desc = ui.TextInput(
        label="Panel Description",
        placeholder="Select a category below to open a ticket.",
        default="Select the category that best matches your request.\nOur team will be with you shortly.\n\n📌 Tickets are private and handled by staff only.",
        style=discord.TextStyle.long
    )

    async def on_submit(self, interaction: discord.Interaction):
        set_config(
            interaction.guild.id,
            ticket_panel_title=self.panel_title.value,
            ticket_panel_desc=self.panel_desc.value
        )
        await interaction.response.send_message(
            "✅ Ticket panel configuration saved.", ephemeral=True
        )


# ---------------------------------------------------------------------------
# RANKED BOOST MODAL  (opened after user selects options via Select menus)
# ---------------------------------------------------------------------------
class RankedOrderModal(ui.Modal, title="Ranked Boost Order"):
    notes = ui.TextInput(
        label="Additional Notes (Optional)",
        placeholder="Any special requests or information...",
        required=False,
        style=discord.TextStyle.long,
        max_length=500
    )

    def __init__(self, current_rank: str, desired_rank: str, p11: str, payment: str):
        super().__init__()
        self.current_rank = current_rank
        self.desired_rank = desired_rank
        self.p11          = p11
        self.payment      = payment

    async def on_submit(self, interaction: discord.Interaction):
        conn = get_db()
        c    = conn.cursor()
        order_id = f"RANKED-{uuid.uuid4().hex[:6].upper()}"
        c.execute(
            "INSERT INTO orders (id, user_id, from_tier, to_tier, price, method) VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, interaction.user.id, self.current_rank, self.desired_rank, 0.0, self.payment)
        )
        conn.commit()

        # Fetch ticket channel and auto-open a ticket
        guild_id    = interaction.guild.id if interaction.guild else None
        ticket_ch   = None
        if guild_id:
            cfg = get_config(guild_id)
            if cfg and cfg["ticket_channel_id"]:
                ticket_ch = interaction.guild.get_channel(cfg["ticket_channel_id"])

        conn.close()

        # Build order embed
        e = base_embed("🔥 New Ranked Boost Order", color=PRIMARY)
        e.set_author(name="BrawlCarry | Ranked Boost", icon_url=interaction.user.display_avatar.url)
        e.add_field(name="👤 Customer",           value=interaction.user.mention,          inline=True)
        e.add_field(name="🆔 Order ID",            value=f"`{order_id}`",                   inline=True)
        e.add_field(name="📦 Route",
                    value=f"`{self.current_rank}` → `{self.desired_rank}`",                 inline=False)
        e.add_field(name="⚡ Power 11 Brawlers",  value=f"**{self.p11}**",                  inline=True)
        e.add_field(name="💳 Payment Method",      value=f"**{self.payment}**",              inline=True)
        if self.notes.value:
            e.add_field(name="📝 Notes", value=self.notes.value, inline=False)

        # Auto-create ticket channel for this order
        guild  = interaction.guild
        member = interaction.user
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        for role in guild.roles:
            if role.permissions.administrator or role.permissions.manage_channels:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        ticket_ch = await guild.create_text_channel(
            name=f"ranked-{member.name[:12].lower()}",
            overwrites=overwrites,
            topic=f"Ranked Boost | {order_id} | Opened by {member} | {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        )

        welcome = base_embed("🔥 Ranked Boost Ticket", color=PRIMARY)
        welcome.description = (
            f"Welcome, {member.mention}! 🎮\n\n"
            f"📋 **Order:** `{order_id}`\n"
            f"📦 **Route:** `{self.current_rank}` → `{self.desired_rank}`\n"
            f"⚡ **P11 Brawlers:** {self.p11}\n"
            f"💳 **Payment:** {self.payment}\n"
            f"🕐 **Opened:** <t:{int(datetime.utcnow().timestamp())}:F>\n\n"
            "Our staff will contact you shortly to complete your order. "
            "Please have your payment ready!"
        )
        welcome.set_author(name=member.display_name, icon_url=member.display_avatar.url)

        await ticket_ch.send(content=member.mention, embed=welcome, view=TicketCloseView())
        await interaction.response.send_message(
            f"✅ Your Ranked Boost order has been placed!\n📩 Ticket opened: {ticket_ch.mention}",
            ephemeral=True
        )


# ---------------------------------------------------------------------------
# PRESTIGE BOOST MODAL  (opened after user selects options via Select menus)
# ---------------------------------------------------------------------------
class PrestigeOrderModal(ui.Modal, title="Prestige Boost Order"):
    notes = ui.TextInput(
        label="Additional Notes (Optional)",
        placeholder="Any special requests or information...",
        required=False,
        style=discord.TextStyle.long,
        max_length=500
    )

    def __init__(self, prestige_spec: str, payment: str):
        super().__init__()
        self.prestige_spec = prestige_spec
        self.payment       = payment

    async def on_submit(self, interaction: discord.Interaction):
        conn = get_db()
        c    = conn.cursor()
        order_id = f"PREST-{uuid.uuid4().hex[:6].upper()}"
        c.execute(
            "INSERT INTO orders (id, user_id, from_tier, to_tier, price, method) VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, interaction.user.id, self.prestige_spec.split("→")[0].strip(),
             self.prestige_spec.split("→")[-1].strip(), 0.0, self.payment)
        )
        conn.commit()
        conn.close()

        guild  = interaction.guild
        member = interaction.user
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        for role in guild.roles:
            if role.permissions.administrator or role.permissions.manage_channels:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        ticket_ch = await guild.create_text_channel(
            name=f"prestige-{member.name[:12].lower()}",
            overwrites=overwrites,
            topic=f"Prestige Boost | {order_id} | Opened by {member} | {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        )

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

        await ticket_ch.send(content=member.mention, embed=welcome, view=TicketCloseView())
        await interaction.response.send_message(
            f"✅ Your Prestige Boost order has been placed!\n📩 Ticket opened: {ticket_ch.mention}",
            ephemeral=True
        )


# ---------------------------------------------------------------------------
# RANKED BOOST SELECT-MENU VIEW  (step-by-step form, mirrors the Discord form)
# ---------------------------------------------------------------------------
class RankedOrderView(ui.View):
    """Multi-step select-menu form that collects all fields, then opens a modal for notes."""

    def __init__(self):
        super().__init__(timeout=300)
        self.current_rank: str | None = None
        self.desired_rank: str | None = None
        self.p11:          str | None = None
        self.payment:      str | None = None

        # ── Select: current rank ──────────────────────────────────────────
        current_select = ui.Select(
            placeholder="Select your current rank...",
            options=[discord.SelectOption(label=r, value=r) for r in CURRENT_RANKS],
            custom_id="ranked_current",
            row=0
        )
        current_select.callback = self._on_current
        self.add_item(current_select)

        # ── Select: desired rank ──────────────────────────────────────────
        desired_select = ui.Select(
            placeholder="Select your desired rank...",
            options=[discord.SelectOption(label=r, value=r) for r in DESIRED_RANKS],
            custom_id="ranked_desired",
            row=1
        )
        desired_select.callback = self._on_desired
        self.add_item(desired_select)

        # ── Select: P11 brawlers ──────────────────────────────────────────
        p11_select = ui.Select(
            placeholder="Select number of Power 11 brawlers...",
            options=[discord.SelectOption(label=n, value=n) for n in P11_OPTIONS],
            custom_id="ranked_p11",
            row=2
        )
        p11_select.callback = self._on_p11
        self.add_item(p11_select)

        # ── Select: payment method ────────────────────────────────────────
        pay_select = ui.Select(
            placeholder="Select payment method...",
            options=[discord.SelectOption(label="PayPal", value="PayPal", emoji="💳")],
            custom_id="ranked_pay",
            row=3
        )
        pay_select.callback = self._on_pay
        self.add_item(pay_select)

        # ── Submit button ─────────────────────────────────────────────────
        submit_btn = ui.Button(
            label="Submit",
            style=discord.ButtonStyle.primary,
            custom_id="ranked_submit",
            row=4,
            emoji="✅"
        )
        submit_btn.callback = self._on_submit
        self.add_item(submit_btn)

        # ── Cancel button ─────────────────────────────────────────────────
        cancel_btn = ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            custom_id="ranked_cancel",
            row=4,
            emoji="✖️"
        )
        cancel_btn.callback = self._on_cancel
        self.add_item(cancel_btn)

    async def _on_current(self, interaction: discord.Interaction):
        self.current_rank = interaction.data["values"][0]
        await interaction.response.defer()

    async def _on_desired(self, interaction: discord.Interaction):
        self.desired_rank = interaction.data["values"][0]
        await interaction.response.defer()

    async def _on_p11(self, interaction: discord.Interaction):
        self.p11 = interaction.data["values"][0]
        await interaction.response.defer()

    async def _on_pay(self, interaction: discord.Interaction):
        self.payment = interaction.data["values"][0]
        await interaction.response.defer()

    async def _on_submit(self, interaction: discord.Interaction):
        missing = []
        if not self.current_rank: missing.append("Current Rank")
        if not self.desired_rank: missing.append("Desired Rank")
        if not self.p11:          missing.append("Power 11 Brawlers")
        if not self.payment:      missing.append("Payment Method")
        if missing:
            await interaction.response.send_message(
                f"❌ Please fill in: **{', '.join(missing)}**", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            RankedOrderModal(self.current_rank, self.desired_rank, self.p11, self.payment)
        )

    async def _on_cancel(self, interaction: discord.Interaction):
        await interaction.response.send_message("❌ Order cancelled.", ephemeral=True)
        await interaction.message.delete()


# ---------------------------------------------------------------------------
# PRESTIGE BOOST SELECT-MENU VIEW
# ---------------------------------------------------------------------------
class PrestigeOrderView(ui.View):
    """Two-field form for prestige orders."""

    def __init__(self):
        super().__init__(timeout=300)
        self.prestige_spec: str | None = None
        self.payment:       str | None = None

        # ── Select: prestige spec ─────────────────────────────────────────
        pres_select = ui.Select(
            placeholder="Select prestige spec...",
            options=[discord.SelectOption(label=p, value=p) for p in PRESTIGE_OPTIONS],
            custom_id="prest_spec",
            row=0
        )
        pres_select.callback = self._on_spec
        self.add_item(pres_select)

        # ── Select: payment method ────────────────────────────────────────
        pay_select = ui.Select(
            placeholder="Select payment method...",
            options=[discord.SelectOption(label="PayPal", value="PayPal", emoji="💳")],
            custom_id="prest_pay",
            row=1
        )
        pay_select.callback = self._on_pay
        self.add_item(pay_select)

        # ── Submit ────────────────────────────────────────────────────────
        submit_btn = ui.Button(
            label="Submit",
            style=discord.ButtonStyle.primary,
            custom_id="prest_submit",
            row=2,
            emoji="✅"
        )
        submit_btn.callback = self._on_submit
        self.add_item(submit_btn)

        # ── Cancel ────────────────────────────────────────────────────────
        cancel_btn = ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            custom_id="prest_cancel",
            row=2,
            emoji="✖️"
        )
        cancel_btn.callback = self._on_cancel
        self.add_item(cancel_btn)

    async def _on_spec(self, interaction: discord.Interaction):
        self.prestige_spec = interaction.data["values"][0]
        await interaction.response.defer()

    async def _on_pay(self, interaction: discord.Interaction):
        self.payment = interaction.data["values"][0]
        await interaction.response.defer()

    async def _on_submit(self, interaction: discord.Interaction):
        missing = []
        if not self.prestige_spec: missing.append("Prestige Spec")
        if not self.payment:       missing.append("Payment Method")
        if missing:
            await interaction.response.send_message(
                f"❌ Please fill in: **{', '.join(missing)}**", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            PrestigeOrderModal(self.prestige_spec, self.payment)
        )

    async def _on_cancel(self, interaction: discord.Interaction):
        await interaction.response.send_message("❌ Order cancelled.", ephemeral=True)
        await interaction.message.delete()


# ---------------------------------------------------------------------------
# PANEL BUTTON VIEWS  (one button → ephemeral form message)
# ---------------------------------------------------------------------------
class RankedPanelButton(ui.View):
    """Persistent button on the ranked panel."""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Ranked Boost Order", style=discord.ButtonStyle.danger,
               emoji="🔥", custom_id="ranked_panel_btn_v1")
    async def open_ranked(self, interaction: discord.Interaction, button: ui.Button):
        e = base_embed("🔥 Ranked Boost Order", color=PRIMARY)
        e.description = (
            "Fill in the fields below and press **Submit** to place your order.\n"
            "A private ticket will be created for you automatically."
        )
        e.add_field(
            name="⚠️ Notice",
            value="This form will be submitted to **BrawlMart | Bot**. "
                  "Do not share passwords or other sensitive information.",
            inline=False
        )
        await interaction.response.send_message(embed=e, view=RankedOrderView(), ephemeral=True)


class PrestigePanelButton(ui.View):
    """Persistent button on the prestige panel."""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Prestige Boost Order", style=discord.ButtonStyle.primary,
               emoji="✨", custom_id="prestige_panel_btn_v1")
    async def open_prestige(self, interaction: discord.Interaction, button: ui.Button):
        e = base_embed("✨ Prestige Boost Order", color=ACCENT)
        e.description = (
            "Fill in the fields below and press **Submit** to place your order.\n"
            "A private ticket will be created for you automatically."
        )
        e.add_field(
            name="⚠️ Notice",
            value="This form will be submitted to **BrawlMart | Bot**. "
                  "Do not share passwords or other sensitive information.",
            inline=False
        )
        await interaction.response.send_message(embed=e, view=PrestigeOrderView(), ephemeral=True)


# ---------------------------------------------------------------------------
# PERSISTENT VIEWS  (existing)
# ---------------------------------------------------------------------------
class OrderButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Place Order", style=discord.ButtonStyle.primary, emoji="🎮", custom_id="order_btn_v2")
    async def order(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(OrderModal())


class OrderActionsView(ui.View):
    def __init__(self, order_id: str):
        super().__init__(timeout=None)
        self.order_id = order_id

    @ui.button(label="Claim Your Boost", style=discord.ButtonStyle.primary, emoji="🟠", custom_id="order_upgrade_btn")
    async def upgrade(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(
            "📨 Our team will contact you shortly to begin your order!", ephemeral=True
        )


class VouchButtonView(ui.View):
    def __init__(self, order_id: str = None):
        super().__init__(timeout=None)
        self.order_id = order_id

    @ui.button(label="Submit a Vouch", style=discord.ButtonStyle.success, emoji="⭐", custom_id="vouch_btn_v2")
    async def vouch(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(VouchModal(order_id=self.order_id))


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
            c.execute("UPDATE giveaways SET participants = ? WHERE id = ?",
                      (json.dumps(participants), self.giveaway_id))
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
        e.description = f"**{count:,}** participant{'s' if count != 1 else ''} have entered this giveaway."
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
        e.description = extra if extra else "No extra entry methods have been configured for this giveaway."
        await interaction.response.send_message(embed=e, ephemeral=True)


class TicketSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Carry Order",     value="carry", emoji="🎮", description="Place or inquire about a Brawl Stars boost order"),
            discord.SelectOption(label="General Support", value="other", emoji="ℹ️",  description="Any other questions or concerns"),
        ]
        super().__init__(
            placeholder="📩 Select a category to open a ticket...",
            options=options,
            custom_id="ticket_select_v2"
        )

    async def callback(self, interaction: discord.Interaction):
        category_map = {
            "carry": ("🎮 Carry Order",    PRIMARY),
            "other": ("ℹ️ General Support", SUCCESS),
        }
        label, color = category_map.get(self.values[0], ("Ticket", PRIMARY))
        guild  = interaction.guild
        member = interaction.user

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        for role in guild.roles:
            if role.permissions.administrator or role.permissions.manage_channels:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        ch = await guild.create_text_channel(
            name=f"ticket-{member.name[:12].lower()}",
            overwrites=overwrites,
            topic=f"{label} | Opened by {member} | {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        )

        e = base_embed(label, color=color)
        e.description = (
            f"Welcome, {member.mention}!\n\n"
            f"📋 **Category:** {label}\n"
            f"🕐 **Opened:** <t:{int(datetime.utcnow().timestamp())}:F>\n\n"
            "Staff will be with you shortly. Please describe your request in detail."
        )
        e.set_author(name=member.display_name, icon_url=member.display_avatar.url)

        await ch.send(content=member.mention, embed=e, view=TicketCloseView())
        await interaction.response.send_message(f"✅ Ticket created: {ch.mention}", ephemeral=True)


class TicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


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
            "⭐ Rate your experience (1–5)\n"
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
    ticket_channel="Channel where the ticket panel will live"
)
@app_commands.checks.has_permissions(administrator=True)
async def setup(
    interaction: discord.Interaction,
    vouch_channel: discord.TextChannel = None,
    ticket_channel: discord.TextChannel = None
):
    updates = {}
    if vouch_channel:
        updates["vouch_channel_id"] = vouch_channel.id
    if ticket_channel:
        updates["ticket_channel_id"] = ticket_channel.id
    if updates:
        set_config(interaction.guild.id, **updates)

    e = base_embed("⚙️ Server Configuration", color=SUCCESS)
    e.description = "Bot settings updated successfully."
    if vouch_channel:
        e.add_field(name="⭐ Vouch Channel", value=vouch_channel.mention, inline=True)
    if ticket_channel:
        e.add_field(name="🎫 Ticket Channel", value=ticket_channel.mention, inline=True)
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="order_panel", description="Post the order creation panel in this channel")
@app_commands.describe(image_url="Optional banner image URL for the panel")
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
@app_commands.describe(image_url="Optional banner image URL for the panel")
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
@app_commands.describe(image_url="Optional banner image URL for the panel")
@app_commands.checks.has_permissions(manage_channels=True)
async def prestige_panel(interaction: discord.Interaction, image_url: str = None):
    e = base_embed("✨ Prestige Boost", color=ACCENT)
    e.description = (
        "Unlock your prestige! Click the button below to place your **Prestige Boost** order.\n\n"
        "**Pricing** *(depends on brawler & power level)*\n"
        "🔴 Prestige 1 → 2 \n"
        "🟡 Prestige 2 → 3 \n\n"
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
             else "Select the category that best matches your request.\nOur team will be with you shortly.\n\n📌 Tickets are private and handled by staff only.")
    e = discord.Embed(title=title, color=PRIMARY, description=desc)
    e.set_footer(text=FOOTER_BRAND)
    e.timestamp = datetime.utcnow()
    await interaction.channel.send(embed=e, view=TicketView())
    await interaction.response.send_message("✅ Ticket panel posted.", ephemeral=True)


@bot.tree.command(name="configure_ticket_panel", description="Customise the ticket panel title and description")
@app_commands.checks.has_permissions(administrator=True)
async def configure_ticket_panel(interaction: discord.Interaction):
    cfg = get_config(interaction.guild.id)
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
        "⭐ Rate your experience (1–5)\n"
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
    prize="Prize name",
    hours="Duration in hours",
    winners="Number of winners",
    description="Giveaway description or rules",
    extra_entries="Extra entry methods shown when users click the Extra Entries button",
    ping="Who to ping: @everyone, @here, a role mention, or none",
    image_url="Optional banner image URL"
)
@app_commands.checks.has_permissions(manage_channels=True)
async def giveaway(
    interaction: discord.Interaction,
    prize: str,
    hours: int,
    winners: int,
    description: str,
    extra_entries: str = None,
    ping: str = "@everyone",
    image_url: str = None
):
    conn = get_db()
    c = conn.cursor()
    ga_id   = f"G{uuid.uuid4().hex[:8].upper()}"
    ends_at = datetime.utcnow() + timedelta(hours=hours)
    c.execute(
        "INSERT INTO giveaways (id, prize, desc, winners, hosted_by, participants, image_url, extra_entries, ping, ended_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ga_id, prize, description, winners, interaction.user.id, "[]", image_url, extra_entries, ping, ends_at)
    )
    conn.commit()
    conn.close()

    end_ts = int(ends_at.timestamp())

    e = discord.Embed(title=f"🎁 {prize}", color=PRIMARY)
    e.add_field(name="ℹ️ Description", value=description, inline=False)
    e.add_field(name="⏰ Ends", value=f"<t:{end_ts}:F>  (<t:{end_ts}:R>)", inline=False)
    e.add_field(name="🏆 Winners", value=f"**{winners}** winner{'s' if winners != 1 else ''}", inline=True)
    e.add_field(name="👥 Participants", value="**0** entered", inline=True)
    e.add_field(name="🎯 Hosted By", value=interaction.user.mention, inline=True)
    if extra_entries:
        e.add_field(name="🎁 Bonus Entries", value="Click **Extra Entries** to see how to earn more!", inline=False)
    if image_url:
        e.set_image(url=image_url)
    e.set_footer(text=f"{FOOTER_BRAND} | ID: {ga_id}")
    e.timestamp = datetime.utcnow()

    ping_content = ping if (ping and ping.lower() != "none") else ""
    if ping_content:
        ping_content += " **🎉 NEW GIVEAWAY!**"
    else:
        ping_content = "**🎉 NEW GIVEAWAY!**"

    await interaction.channel.send(
        content=ping_content,
        embed=e,
        view=GiveawayView(ga_id),
        allowed_mentions=discord.AllowedMentions(everyone=True, roles=True)
    )
    await interaction.response.send_message(f"✅ Giveaway started! ID: `{ga_id}`", ephemeral=True)


@bot.tree.command(name="end_giveaway", description="End a giveaway and pick winners")
@app_commands.describe(giveaway_id="Giveaway ID (shown in the embed footer)")
@app_commands.checks.has_permissions(manage_channels=True)
async def end_giveaway(interaction: discord.Interaction, giveaway_id: str):
    conn = get_db()
    c = conn.cursor()
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
    e.add_field(name="🏆 Winners", value=winner_mentions, inline=False)
    e.add_field(name="👥 Total Participants", value=f"**{len(participants):,}**", inline=True)
    e.add_field(name="🆔 Giveaway ID", value=f"`{giveaway_id}`", inline=True)
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
                e.description = (
                    "If the main server becomes unavailable, join our backup:\n\n"
                    f"> **{link}**"
                )
                await member.send(embed=e)
                results["sent"] += 1
            except Exception:
                results["failed"] += 1

    await asyncio.gather(*[send_dm(m) for m in members])

    e = base_embed("📨 Backup Link Sent", color=SUCCESS)
    e.add_field(name="✅ Delivered", value=f"**{results['sent']}**", inline=True)
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
        "`/setup` — Configure vouch and ticket channels\n"
        "`/configure_ticket_panel` — Customise ticket panel text\n"
        "`/order_panel` — Post the generic order panel\n"
        "`/ranked_panel` — Post the Ranked Boost panel 🔥\n"
        "`/prestige_panel` — Post the Prestige Boost panel ✨\n"
        "`/ticket_panel` — Post the ticket panel\n"
        "`/vouch_panel` — Send vouch panel to user or channel\n"
        "`/giveaway` — Start a giveaway (supports extra entries & custom ping)\n"
        "`/end_giveaway` — End a giveaway and draw winners\n"
        "`/backup_link` — DM all members the backup server link\n\n"
        "**👤 User Commands**\n"
        "`/stats` — View your carry statistics\n"
        "`/help` — Show this menu"
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
    bot.add_view(OrderButton())
    bot.add_view(TicketView())
    bot.add_view(TicketCloseView())
    bot.add_view(VouchButtonView())
    bot.add_view(RankedPanelButton())
    bot.add_view(PrestigePanelButton())
    # Re-register all active giveaway views so buttons survive restarts
    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT id FROM giveaways WHERE winner_ids IS NULL OR winner_ids = ''")
    for row in c.fetchall():
        bot.add_view(GiveawayView(row["id"]))
    conn.close()

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("[ERROR] DISCORD_TOKEN not set in environment.")
        exit(1)
    bot.run(token)
