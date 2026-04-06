import discord
from discord.ext import commands
from discord import app_commands, ui
import json, os, sqlite3, uuid, random, io, aiohttp
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

FOOTER_BRAND = "Powered by Brawl Carry\u2122"

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
        ended_at TIMESTAMP
    )""")
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

def set_config(guild_id: int, **kwargs):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,))
    for key, val in kwargs.items():
        c.execute(f"UPDATE guild_config SET {key} = ? WHERE guild_id = ?", (val, guild_id))
    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# WATERMARK UTILITY
# ---------------------------------------------------------------------------
async def watermark_image(image_bytes: bytes, text: str = "Iceyz Vouches") -> bytes:
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
        marked = await watermark_image(raw)
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
                "\u274c Invalid price. Please enter a number like `44.99`.", ephemeral=True
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

        e = base_embed("\U0001f680 RANKED ORDER", color=PRIMARY)
        e.add_field(name="\U0001f91d Buyer", value=f"\u21b3 {interaction.user.mention}", inline=False)
        e.add_field(name="\U0001f4b5 Order Amount (USD) \U0001f4b2", value=f"\u21b3 **${price_val:.2f}**", inline=False)
        e.add_field(name="\U0001f680 Order Type", value="\u21b3 Ranked b\U0001f15eost", inline=False)
        e.add_field(
            name="\U0001f4e6 Order Details \u2139\ufe0f",
            value=f"\u21b3 {self.from_tier.value} \u2192 {self.to_tier.value}",
            inline=False
        )
        e.set_author(name="\U0001f3ae BrawlCarry | Brawl Stars Boost")

        wm_file = None
        if img:
            wm_file = await fetch_and_watermark(img)
            if wm_file:
                e.set_image(url="attachment://proof.jpg")

        view = OrderActionsView(order_id)
        if wm_file:
            await interaction.response.send_message(embed=e, view=view, file=wm_file)
        else:
            await interaction.response.send_message(embed=e, view=view)


class VouchModal(ui.Modal, title="Submit Your Vouch"):
    rating = ui.TextInput(
        label="Rating (1-5 stars)",
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
        star_str = "\u2b50" * stars

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

        e = base_embed("\u2b50 CUSTOMER VOUCH", color=GOLD)
        e.add_field(name="\U0001f91d Customer", value=f"\u21b3 {interaction.user.mention}", inline=False)
        e.add_field(name="\U0001f4b0 Order Amount", value=f"\u21b3 **${amount_val:.2f}**", inline=False)
        e.add_field(name="\U0001f4dd Feedback", value=f"\u21b3 *{self.feedback.value}*", inline=False)
        e.add_field(name=f"\u2b50 Rating ({stars}/5)", value=star_str, inline=False)
        if self.order_id:
            e.set_footer(text=f"{FOOTER_BRAND} | Order: {self.order_id}")

        wm_file = None
        if img:
            wm_file = await fetch_and_watermark(img)
            if wm_file:
                e.set_image(url="attachment://proof.jpg")

        await interaction.response.send_message(
            "\u2705 Your vouch has been submitted. Thank you!", ephemeral=True
        )

        if vouch_ch_id:
            ch = interaction.guild.get_channel(vouch_ch_id) if interaction.guild else None
            if ch:
                if wm_file:
                    await ch.send(embed=e, file=wm_file)
                else:
                    await ch.send(embed=e)


class TicketPanelSetupModal(ui.Modal, title="Configure Ticket Panel"):
    panel_title = ui.TextInput(
        label="Panel Title (markdown supported)",
        placeholder="## Support Center",
        default="## \U0001f3ab Support Center",
        style=discord.TextStyle.short
    )
    panel_desc = ui.TextInput(
        label="Panel Description (markdown supported)",
        placeholder="Select a category below to open a ticket.",
        default="Select the category that best matches your request.\nOur team will be with you shortly.\n\n> \U0001f4cc Tickets are private and handled by staff only.",
        style=discord.TextStyle.long
    )

    async def on_submit(self, interaction: discord.Interaction):
        set_config(
            interaction.guild.id,
            ticket_panel_title=self.panel_title.value,
            ticket_panel_desc=self.panel_desc.value
        )
        await interaction.response.send_message(
            "\u2705 Ticket panel configuration saved.", ephemeral=True
        )

# ---------------------------------------------------------------------------
# PERSISTENT VIEWS
# ---------------------------------------------------------------------------
class OrderButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Create Order", style=discord.ButtonStyle.primary, emoji="\U0001f3ae", custom_id="order_btn_v2")
    async def order(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(OrderModal())


class OrderActionsView(ui.View):
    def __init__(self, order_id: str):
        super().__init__(timeout=None)
        self.order_id = order_id

    @ui.button(label="Get Your Rank Upgraded", style=discord.ButtonStyle.primary, emoji="\U0001f7e0", custom_id="order_upgrade_btn")
    async def upgrade(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(
            "\U0001f4e8 Our team will contact you shortly to begin your order!", ephemeral=True
        )


class VouchButtonView(ui.View):
    def __init__(self, order_id: str = None):
        super().__init__(timeout=None)
        self.order_id = order_id

    @ui.button(label="Submit A Vouch", style=discord.ButtonStyle.success, emoji="\u2b50", custom_id="vouch_btn_v2")
    async def vouch(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(VouchModal(order_id=self.order_id))


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
            c.execute("UPDATE giveaways SET participants = ? WHERE id = ?",
                      (json.dumps(participants), self.giveaway_id))
            conn.commit()
            await interaction.response.send_message("\u2705 You have entered the giveaway! Good luck.", ephemeral=True)
        conn.close()

    @ui.button(label="View Participants", style=discord.ButtonStyle.blurple, emoji="\U0001f465", custom_id="ga_view_v2")
    async def view(self, interaction: discord.Interaction, button: ui.Button):
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT participants FROM giveaways WHERE id = ?", (self.giveaway_id,))
        ga = c.fetchone()
        conn.close()
        count = len(json.loads(ga["participants"])) if ga and ga["participants"] else 0
        await interaction.response.send_message(
            f"\U0001f465 **{count:,}** participant{'s' if count != 1 else ''} have entered.", ephemeral=True
        )

    @ui.button(label="Extra Entries", style=discord.ButtonStyle.secondary, emoji="\U0001f381", custom_id="ga_extra_v2")
    async def extra(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(
            "\U0001f4cc Check the pinned messages for extra entry methods!", ephemeral=True
        )


class TicketSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Carry Order",     value="carry",   emoji="\U0001f3ae", description="Place or inquire about a brawl stars boost order"),
            discord.SelectOption(label="General Support", value="other",   emoji="\u2139\ufe0f",  description="Any other questions or concerns"),
        ]
        super().__init__(
            placeholder="\U0001f4e9 Select a category to open a ticket...",
            options=options,
            custom_id="ticket_select_v2"
        )

    async def callback(self, interaction: discord.Interaction):
        category_map = {
            "carry":   ("\U0001f3ae Carry Order",    PRIMARY),
            "other":   ("\u2139\ufe0f General Support", SUCCESS),
        }
        label, color = category_map.get(self.values[0], ("Ticket", PRIMARY))
        guild = interaction.guild
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

        e = base_embed(f"{label}", color=color)
        e.description = (
            f"Welcome, {member.mention}!\n\n"
            f"> \U0001f4cc **Category:** {label}\n"
            f"> \U0001f552 **Opened:** <t:{int(datetime.utcnow().timestamp())}:F>\n\n"
            "Staff will be with you shortly. Please describe your request in detail."
        )
        e.set_author(name=f"{member.display_name}", icon_url=member.display_avatar.url)

        close_view = TicketCloseView()
        await ch.send(content=member.mention, embed=e, view=close_view)
        await interaction.response.send_message(
            f"\u2705 Your ticket has been created: {ch.mention}", ephemeral=True
        )


class TicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


class TicketCloseView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="\U0001f512", custom_id="ticket_close_v2")
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        e = base_embed("\U0001f512 Ticket Closing", color=DANGER)
        e.description = "This ticket will be deleted in **5 seconds**."
        await interaction.response.send_message(embed=e)
        import asyncio
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except Exception:
            pass

    @ui.button(label="Send Vouch Panel", style=discord.ButtonStyle.success, emoji="\u2b50", custom_id="ticket_send_vouch_v2")
    async def send_vouch(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("\u274c Staff only.", ephemeral=True)
            return
        e = base_embed("\u2b50 Submit Your Vouch", color=GOLD)
        e.description = (
            "Thank you for your order!\n\n"
            "> \U0001f4f8 Attach a screenshot as proof\n"
            "> \u2b50 Rate your experience (1-5)\n"
            "> \U0001f4ac Leave honest feedback\n\n"
            "Click the button below to submit."
        )
        await interaction.response.send_message(embed=e, view=VouchButtonView())

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

    e = base_embed("\u2699\ufe0f Server Configuration", color=SUCCESS)
    e.description = "Bot settings updated successfully."
    if vouch_channel:
        e.add_field(name="\u2b50 Vouch Channel", value=vouch_channel.mention, inline=True)
    if ticket_channel:
        e.add_field(name="\U0001f3ab Ticket Channel", value=ticket_channel.mention, inline=True)
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="order_panel", description="Post the order creation panel in this channel")
@app_commands.describe(image_url="Optional banner image URL for the panel")
@app_commands.checks.has_permissions(manage_channels=True)
async def order_panel(interaction: discord.Interaction, image_url: str = None):
    e = base_embed("\U0001f680 Brawl Stars Boost Orders", color=PRIMARY)
    e.description = (
        "## \U0001f3ae Place Your Carry Order\n\n"
        "> Click the button below to fill out your order details.\n\n"
        "**What we offer:**\n"
        "> \U0001f947 Brawl Stars boost, eg. Ranked\n"
        "> \u26a1 Fast completion\n"
        "> \u2b50 5-star rated service"
    )
    if image_url:
        e.set_image(url=image_url)
    await interaction.response.send_message(embed=e, view=OrderButton())


@bot.tree.command(name="ticket_panel", description="Post the support ticket panel in this channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def ticket_panel(interaction: discord.Interaction):
    cfg = get_config(interaction.guild.id)
    title = (cfg["ticket_panel_title"] if cfg and cfg["ticket_panel_title"]
             else "## \U0001f3ab Support Center")
    desc = (cfg["ticket_panel_desc"] if cfg and cfg["ticket_panel_desc"]
            else (
                "Select the category that best matches your request.\n"
                "Our team will be with you shortly.\n\n"
                "> \U0001f4cc Tickets are private and handled by staff only."
            ))
    e = discord.Embed(color=PRIMARY, description=f"{title}\n{desc}")
    e.set_footer(text=FOOTER_BRAND)
    e.timestamp = datetime.utcnow()
    await interaction.response.send_message(embed=e, view=TicketView())


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
    e = base_embed("\u2b50 Submit Your Vouch", color=GOLD)
    e.description = (
        "Thank you for your order!\n\n"
        "> \U0001f4f8 Attach a screenshot as proof\n"
        "> \u2b50 Rate your experience (1-5)\n"
        "> \U0001f4ac Leave honest feedback\n\n"
        "Click the button below to submit."
    )
    if order_id:
        e.set_footer(text=f"{FOOTER_BRAND} | Order: {order_id}")

    view = VouchButtonView(order_id=order_id)
    if user:
        try:
            await user.send(embed=e, view=view)
            await interaction.response.send_message(
                f"\u2705 Vouch panel sent to {user.mention}.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "\u274c Could not DM that user. They may have DMs disabled.", ephemeral=True
            )
    else:
        await interaction.response.send_message(embed=e, view=view)


@bot.tree.command(name="giveaway", description="Start a new giveaway")
@app_commands.describe(
    prize="Prize name",
    hours="Duration in hours",
    winners="Number of winners",
    description="Rules or description",
    image_url="Optional banner image URL"
)
@app_commands.checks.has_permissions(manage_channels=True)
async def giveaway(
    interaction: discord.Interaction,
    prize: str,
    hours: int,
    winners: int,
    description: str,
    image_url: str = None
):
    conn = get_db()
    c = conn.cursor()
    ga_id = f"G{uuid.uuid4().hex[:8].upper()}"
    ends_at = datetime.utcnow() + timedelta(hours=hours)
    c.execute(
        "INSERT INTO giveaways (id, prize, desc, winners, hosted_by, participants, image_url, ended_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (ga_id, prize, description, winners, interaction.user.id, "[]", image_url, ends_at)
    )
    conn.commit()
    conn.close()

    end_ts = int(ends_at.timestamp())
    e = base_embed("\U0001f389 GIVEAWAY \U0001f389", color=PRIMARY)
    e.description = f"## \U0001f381 {prize}"
    e.add_field(name="\u2139\ufe0f Description", value=f"> {description}", inline=False)
    e.add_field(name="\u23f0 Ends", value=f"in {hours} hour{'s' if hours != 1 else ''} ( <t:{end_ts}:F> )", inline=False)
    e.add_field(name="\U0001f3c6 Winners", value=f"**{winners}** winner{'s' if winners != 1 else ''}", inline=True)
    e.add_field(name="\U0001f465 Participants", value="**0** participants", inline=True)
    e.add_field(name="\U0001f3af Hosted By", value=interaction.user.mention, inline=True)
    if image_url:
        e.set_image(url=image_url)
    e.set_footer(text=f"{FOOTER_BRAND} | Giveaway ID: {ga_id}")
    await interaction.response.send_message(
        "@everyone **NEW GIVEAWAY!**",
        embed=e,
        view=GiveawayView(ga_id),
        allowed_mentions=discord.AllowedMentions(everyone=True)
    )


@bot.tree.command(name="end_giveaway", description="End a giveaway and pick winners")
@app_commands.describe(giveaway_id="Giveaway ID (shown in footer)")
@app_commands.checks.has_permissions(manage_channels=True)
async def end_giveaway(interaction: discord.Interaction, giveaway_id: str):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM giveaways WHERE id = ?", (giveaway_id,))
    ga = c.fetchone()

    if not ga:
        await interaction.response.send_message("\u274c Giveaway not found.", ephemeral=True)
        conn.close()
        return

    participants = json.loads(ga["participants"]) if ga["participants"] else []
    if not participants:
        await interaction.response.send_message("\u274c No participants to draw from.", ephemeral=True)
        conn.close()
        return

    winner_ids = random.sample(participants, min(ga["winners"], len(participants)))
    c.execute("UPDATE giveaways SET winner_ids = ? WHERE id = ?", (json.dumps(winner_ids), giveaway_id))
    conn.commit()
    conn.close()

    winner_mentions = " ".join([f"<@{w}>" for w in winner_ids])
    e = base_embed("\U0001f389 GIVEAWAY ENDED", color=SUCCESS)
    e.description = f"## \U0001f381 {ga['prize']}"
    e.add_field(name="\U0001f3c6 Winners", value=winner_mentions, inline=False)
    e.add_field(name="\U0001f465 Total Participants", value=f"**{len(participants):,}**", inline=True)
    e.set_footer(text=f"{FOOTER_BRAND} | Giveaway: {giveaway_id}")
    await interaction.response.send_message(
        f"\U0001f389 Congratulations {winner_mentions}!",
        embed=e,
        allowed_mentions=discord.AllowedMentions(users=True)
    )


@bot.tree.command(name="backup_link", description="DM all members the backup server link")
@app_commands.describe(link="Backup server invite link")
@app_commands.checks.has_permissions(administrator=True)
async def backup_link(interaction: discord.Interaction, link: str):
    import asyncio
    await interaction.response.defer(ephemeral=True)

    members = [m for m in interaction.guild.members if not m.bot]
    results = {"sent": 0, "failed": 0}
    sem = asyncio.Semaphore(20)

    async def send_dm(member):
        async with sem:
            try:
                e = base_embed("\u26a0\ufe0f BACKUP SERVER", color=DANGER)
                e.description = (
                    "If the main server becomes unavailable, join our backup:\n\n"
                    f"> **{link}**"
                )
                await member.send(embed=e)
                results["sent"] += 1
            except Exception:
                results["failed"] += 1

    await asyncio.gather(*[send_dm(m) for m in members])

    e = base_embed("\U0001f4e8 Backup Link Sent", color=SUCCESS)
    e.add_field(name="\u2705 Delivered", value=f"**{results['sent']}**", inline=True)
    e.add_field(name="\u274c Failed", value=f"**{results['failed']}**", inline=True)
    await interaction.followup.send(embed=e, ephemeral=True)


@bot.tree.command(name="stats", description="View carry statistics for a user")
@app_commands.describe(user="User to look up (defaults to you)")
async def stats(interaction: discord.Interaction, user: discord.User = None):
    target = user or interaction.user
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) as count, SUM(price) as total FROM orders WHERE user_id = ?",
        (target.id,)
    )
    row = c.fetchone()
    c.execute("SELECT COUNT(*) as vc FROM vouchers WHERE used_by = ?", (target.id,))
    vc = c.fetchone()
    conn.close()

    e = base_embed(f"\U0001f4ca {target.display_name}", color=PRIMARY)
    e.set_thumbnail(url=target.display_avatar.url)
    e.add_field(name="\U0001f3ae Total Carries", value=f"**{row['count'] or 0}**", inline=True)
    e.add_field(name="\U0001f4b5 Total Spent", value=f"**${row['total']:.2f}**" if row["total"] else "**$0.00**", inline=True)
    e.add_field(name="\u2b50 Vouches", value=f"**{vc['vc'] or 0}**", inline=True)
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="help", description="View all available bot commands")
async def help_cmd(interaction: discord.Interaction):
    e = base_embed("\U0001f4cb BrawlCarry Bot Commands", color=PRIMARY)
    e.description = (
        "## \u2699\ufe0f Admin Commands\n"
        "> `/setup` \u2014 Configure vouch and ticket channels\n"
        "> `/configure_ticket_panel` \u2014 Customise ticket panel text\n"
        "> `/order_panel` \u2014 Post the order panel\n"
        "> `/ticket_panel` \u2014 Post the ticket panel\n"
        "> `/vouch_panel` \u2014 Send vouch panel to user or channel\n"
        "> `/giveaway` \u2014 Start a giveaway\n"
        "> `/end_giveaway` \u2014 End a giveaway and draw winners\n"
        "> `/backup_link` \u2014 DM all members the backup server link\n\n"
        "## \U0001f464 User Commands\n"
        "> `/stats` \u2014 View your carry statistics\n"
        "> `/help` \u2014 Show this menu"
    )
    await interaction.response.send_message(embed=e, ephemeral=True)

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

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("[ERROR] DISCORD_TOKEN not set in environment.")
        exit(1)
    bot.run(token)
