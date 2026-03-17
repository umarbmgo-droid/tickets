import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import asyncio
from datetime import datetime
import time
import io

# ===== CONFIG =====
TOKEN = os.environ.get('TOKEN')
OWNER_ID = 361069640962801664
START_TIME = time.time()

# ===== BOT SETUP =====
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=None, intents=intents, help_command=None)  # No prefix commands

# ===== DATA STORAGE =====
data_file = 'ticket_data.json'
ticket_config = {}
ticket_counter = {}
ticket_transcripts = {}
ticket_categories = {}
staff_roles = {}

def load_data():
    global ticket_config, ticket_counter, ticket_transcripts, ticket_categories, staff_roles
    try:
        if os.path.exists(data_file):
            with open(data_file, 'r') as f:
                data = json.load(f)
                ticket_config = data.get('config', {})
                ticket_counter = data.get('counter', {})
                ticket_transcripts = data.get('transcripts', {})
                ticket_categories = data.get('categories', {})
                staff_roles = data.get('staff_roles', {})
    except Exception as e:
        print(f"Error loading data: {e}")

def save_data():
    try:
        with open(data_file, 'w') as f:
            json.dump({
                'config': ticket_config,
                'counter': ticket_counter,
                'transcripts': ticket_transcripts,
                'categories': ticket_categories,
                'staff_roles': staff_roles
            }, f, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")

load_data()

# ===== UTILITY FUNCTIONS =====
def get_uptime():
    uptime = int(time.time() - START_TIME)
    days = uptime // 86400
    hours = (uptime % 86400) // 3600
    minutes = (uptime % 3600) // 60
    seconds = uptime % 60
    return f"{days}d {hours}h {minutes}m {seconds}s"

def is_admin(interaction: discord.Interaction):
    if interaction.user.guild_permissions.administrator:
        return True
    if interaction.user.id == OWNER_ID:
        return True
    return False

def has_staff_role(guild_id, member):
    if member.guild_permissions.administrator:
        return True
    if member.id == OWNER_ID:
        return True
    
    guild_staff_roles = staff_roles.get(str(guild_id), [])
    for role_id in guild_staff_roles:
        role = member.guild.get_role(role_id)
        if role and role in member.roles:
            return True
    return False

async def save_transcript(channel, ticket_id, closer):
    """Save transcript of a ticket channel"""
    try:
        messages = []
        async for message in channel.history(limit=1000, oldest_first=True):
            messages.append({
                'author': str(message.author),
                'author_id': message.author.id,
                'content': message.content,
                'timestamp': message.created_at.isoformat(),
                'attachments': [a.url for a in message.attachments]
            })
        
        transcript_data = {
            'ticket_id': ticket_id,
            'channel_name': channel.name,
            'guild_id': channel.guild.id,
            'guild_name': channel.guild.name,
            'created_at': channel.created_at.isoformat(),
            'closed_at': datetime.now().isoformat(),
            'closed_by': str(closer),
            'closed_by_id': closer.id,
            'messages': messages,
            'message_count': len(messages)
        }
        
        # Save to transcripts channel if configured
        guild_id = str(channel.guild.id)
        if guild_id in ticket_transcripts:
            transcript_channel_id = ticket_transcripts[guild_id]
            transcript_channel = channel.guild.get_channel(transcript_channel_id)
            
            if transcript_channel:
                # Create transcript file
                transcript_text = f"""
TICKET TRANSCRIPT
================
Ticket ID: {ticket_id}
Channel: {channel.name}
Created: {channel.created_at.strftime('%Y-%m-%d %H:%M:%S')}
Closed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Closed by: {closer}
Messages: {len(messages)}

MESSAGES:
=========
"""
                for msg in messages:
                    transcript_text += f"\n[{msg['timestamp']}] {msg['author']}: {msg['content']}"
                    if msg['attachments']:
                        transcript_text += f"\n[Attachments: {', '.join(msg['attachments'])}]"
                
                # Create file object
                file = discord.File(
                    fp=io.StringIO(transcript_text),
                    filename=f"ticket-{ticket_id}.txt"
                )
                
                # Send transcript to channel
                await transcript_channel.send(
                    f"**Ticket Closed** - {channel.name}\n"
                    f"Closed by: {closer.mention}\n"
                    f"Messages: {len(messages)}",
                    file=file
                )
        
        return True
    except Exception as e:
        print(f"Error saving transcript: {e}")
        return False

# ===== STATUS LOOP =====
async def status_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        await bot.change_presence(activity=discord.Streaming(
            name="Ranked Tickets",
            url="https://www.twitch.tv/ranked"
        ))
        await asyncio.sleep(60)

# ===== EVENTS =====
@bot.event
async def on_ready():
    print(f"✅ Ticket Bot Online")
    print(f"🤖 Bot: {bot.user.name}")
    print(f"👑 Owner: <@{OWNER_ID}>")
    print(f"📊 Guilds: {len(bot.guilds)}")
    
    # Start status loop
    bot.loop.create_task(status_loop())
    
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Error syncing commands: {e}")

@bot.event
async def on_guild_join(guild):
    """Initialize guild settings when bot joins"""
    guild_id = str(guild.id)
    if guild_id not in ticket_counter:
        ticket_counter[guild_id] = 0
    if guild_id not in staff_roles:
        staff_roles[guild_id] = []
    save_data()

# ===== ADMIN COMMANDS GROUP =====
admin_group = app_commands.Group(name="admin", description="Admin commands for ticket setup")

@admin_group.command(name="setup", description="Start ticket system setup")
async def admin_setup(interaction: discord.Interaction):
    """Setup ticket system for the server"""
    if not is_admin(interaction):
        embed = discord.Embed(
            description="You need administrator permissions to use this command",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    guild_id = str(interaction.guild_id)
    
    # Initialize guild settings
    if guild_id not in ticket_counter:
        ticket_counter[guild_id] = 0
    if guild_id not in staff_roles:
        staff_roles[guild_id] = []
    
    embed = discord.Embed(
        title="Ticket System Setup",
        description="Configure your ticket system using the following commands:",
        color=0x2c3e50
    )
    embed.add_field(name="1. Category Setup", value="`/category add <name> <role>` - Create a ticket category with staff role", inline=False)
    embed.add_field(name="2. Panel Setup", value="`/panel create` - Create the ticket panel", inline=False)
    embed.add_field(name="3. Transcript Channel", value="`/transcripts set <channel>` - Set transcript channel", inline=False)
    embed.add_field(name="4. Staff Roles", value="`/staff add <role>` - Add a staff role", inline=False)
    embed.add_field(name="5. View Categories", value="`/category list` - List all categories", inline=False)
    embed.add_field(name="6. View Staff Roles", value="`/staff list` - List staff roles", inline=False)
    
    await interaction.response.send_message(embed=embed)

# ===== CATEGORY COMMANDS GROUP =====
category_group = app_commands.Group(name="category", description="Ticket category management")

@category_group.command(name="add", description="Add a ticket category with staff role")
@app_commands.describe(name="Category name", role="Staff role for this category")
async def category_add(interaction: discord.Interaction, name: str, role: discord.Role):
    """Add a ticket category with staff role"""
    if not is_admin(interaction):
        embed = discord.Embed(
            description="You need administrator permissions to use this command",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    guild_id = str(interaction.guild_id)
    
    if guild_id not in ticket_categories:
        ticket_categories[guild_id] = {}
    
    ticket_categories[guild_id][name.lower()] = {
        'name': name,
        'role_id': role.id,
        'created_by': interaction.user.id,
        'created_at': datetime.now().isoformat()
    }
    save_data()
    
    embed = discord.Embed(
        title="Category Added",
        description=f"Category **{name}** created with staff role {role.mention}",
        color=0x27ae60
    )
    await interaction.response.send_message(embed=embed)

@category_group.command(name="remove", description="Remove a ticket category")
@app_commands.describe(name="Category name to remove")
async def category_remove(interaction: discord.Interaction, name: str):
    """Remove a ticket category"""
    if not is_admin(interaction):
        embed = discord.Embed(
            description="You need administrator permissions to use this command",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    guild_id = str(interaction.guild_id)
    
    if guild_id in ticket_categories and name.lower() in ticket_categories[guild_id]:
        del ticket_categories[guild_id][name.lower()]
        save_data()
        embed = discord.Embed(
            title="Category Removed",
            description=f"Category **{name}** has been removed",
            color=0xe74c3c
        )
    else:
        embed = discord.Embed(
            title="Error",
            description=f"Category **{name}** not found",
            color=0xe74c3c
        )
    await interaction.response.send_message(embed=embed)

@category_group.command(name="list", description="List all ticket categories")
async def category_list(interaction: discord.Interaction):
    """List all ticket categories"""
    if not is_admin(interaction):
        embed = discord.Embed(
            description="You need administrator permissions to use this command",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    guild_id = str(interaction.guild_id)
    
    if guild_id not in ticket_categories or not ticket_categories[guild_id]:
        embed = discord.Embed(
            title="Categories",
            description="No categories configured",
            color=0x95a5a6
        )
    else:
        embed = discord.Embed(
            title="Ticket Categories",
            color=0x2c3e50
        )
        for name, data in ticket_categories[guild_id].items():
            role = interaction.guild.get_role(data['role_id'])
            role_mention = role.mention if role else f"Unknown Role ({data['role_id']})"
            embed.add_field(
                name=data['name'],
                value=f"Staff Role: {role_mention}",
                inline=False
            )
    
    await interaction.response.send_message(embed=embed)

# ===== PANEL COMMANDS GROUP =====
panel_group = app_commands.Group(name="panel", description="Ticket panel management")

@panel_group.command(name="create", description="Create the ticket panel in the current channel")
async def panel_create(interaction: discord.Interaction):
    """Create the ticket panel in the current channel"""
    if not is_admin(interaction):
        embed = discord.Embed(
            description="You need administrator permissions to use this command",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    embed = discord.Embed(
        title="Support Tickets",
        description="Click a button below to create a ticket",
        color=0x2c3e50
    )
    embed.add_field(
        name="How it works",
        value=(
            "1. Click a category button below\n"
            "2. A private ticket channel will be created\n"
            "3. Staff will assist you there\n"
            "4. Close the ticket when resolved"
        ),
        inline=False
    )
    
    # Create buttons for each category
    view = TicketView(interaction.guild_id)
    await interaction.response.send_message(embed=embed, view=view)

# ===== TRANSCRIPTS COMMANDS GROUP =====
transcripts_group = app_commands.Group(name="transcripts", description="Transcript channel management")

@transcripts_group.command(name="set", description="Set the channel where transcripts will be saved")
@app_commands.describe(channel="Channel to save transcripts")
async def transcripts_set(interaction: discord.Interaction, channel: discord.TextChannel):
    """Set the channel where transcripts will be saved"""
    if not is_admin(interaction):
        embed = discord.Embed(
            description="You need administrator permissions to use this command",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    guild_id = str(interaction.guild_id)
    ticket_transcripts[guild_id] = channel.id
    save_data()
    
    embed = discord.Embed(
        title="Transcript Channel Set",
        description=f"Transcripts will be saved to {channel.mention}",
        color=0x27ae60
    )
    await interaction.response.send_message(embed=embed)

# ===== STAFF COMMANDS GROUP =====
staff_group = app_commands.Group(name="staff", description="Staff role management")

@staff_group.command(name="add", description="Add a staff role that can manage tickets")
@app_commands.describe(role="Role to add as staff")
async def staff_add(interaction: discord.Interaction, role: discord.Role):
    """Add a staff role that can manage tickets"""
    if not is_admin(interaction):
        embed = discord.Embed(
            description="You need administrator permissions to use this command",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    guild_id = str(interaction.guild_id)
    
    if guild_id not in staff_roles:
        staff_roles[guild_id] = []
    
    if role.id not in staff_roles[guild_id]:
        staff_roles[guild_id].append(role.id)
        save_data()
        embed = discord.Embed(
            title="Staff Role Added",
            description=f"{role.mention} can now manage tickets",
            color=0x27ae60
        )
    else:
        embed = discord.Embed(
            title="Error",
            description=f"{role.mention} is already a staff role",
            color=0xe74c3c
        )
    await interaction.response.send_message(embed=embed)

@staff_group.command(name="remove", description="Remove a staff role")
@app_commands.describe(role="Role to remove from staff")
async def staff_remove(interaction: discord.Interaction, role: discord.Role):
    """Remove a staff role"""
    if not is_admin(interaction):
        embed = discord.Embed(
            description="You need administrator permissions to use this command",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    guild_id = str(interaction.guild_id)
    
    if guild_id in staff_roles and role.id in staff_roles[guild_id]:
        staff_roles[guild_id].remove(role.id)
        save_data()
        embed = discord.Embed(
            title="Staff Role Removed",
            description=f"{role.mention} can no longer manage tickets",
            color=0xe74c3c
        )
    else:
        embed = discord.Embed(
            title="Error",
            description=f"{role.mention} is not a staff role",
            color=0xe74c3c
        )
    await interaction.response.send_message(embed=embed)

@staff_group.command(name="list", description="List all staff roles")
async def staff_list(interaction: discord.Interaction):
    """List all staff roles"""
    if not is_admin(interaction):
        embed = discord.Embed(
            description="You need administrator permissions to use this command",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    guild_id = str(interaction.guild_id)
    
    if guild_id not in staff_roles or not staff_roles[guild_id]:
        embed = discord.Embed(
            title="Staff Roles",
            description="No staff roles configured",
            color=0x95a5a6
        )
    else:
        roles = []
        for role_id in staff_roles[guild_id]:
            role = interaction.guild.get_role(role_id)
            if role:
                roles.append(role.mention)
            else:
                roles.append(f"Unknown Role ({role_id})")
        
        embed = discord.Embed(
            title="Staff Roles",
            description="\n".join(roles),
            color=0x2c3e50
        )
    await interaction.response.send_message(embed=embed)

# ===== BASIC COMMANDS =====
@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    embed = discord.Embed(
        description=f"{round(bot.latency * 1000)}ms",
        color=0x2c3e50
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="uptime", description="Show how long the bot has been running")
async def uptime(interaction: discord.Interaction):
    uptime_str = get_uptime()
    embed = discord.Embed(
        description=uptime_str,
        color=0x2c3e50
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="stats", description="Show ticket statistics")
async def stats(interaction: discord.Interaction):
    """Show ticket statistics"""
    if not is_admin(interaction):
        embed = discord.Embed(
            description="You need administrator permissions to use this command",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    guild_id = str(interaction.guild_id)
    ticket_count = ticket_counter.get(guild_id, 0)
    
    embed = discord.Embed(
        title="Ticket Statistics",
        color=0x2c3e50
    )
    embed.add_field(name="Total Tickets Created", value=str(ticket_count))
    embed.add_field(name="Categories", value=str(len(ticket_categories.get(guild_id, {}))))
    embed.add_field(name="Staff Roles", value=str(len(staff_roles.get(guild_id, []))))
    
    await interaction.response.send_message(embed=embed)

# ===== TICKET VIEW =====
class TicketView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        
        # Add buttons for each category
        categories = ticket_categories.get(str(guild_id), {})
        for name, data in categories.items():
            button = discord.ui.Button(
                label=data['name'],
                style=discord.ButtonStyle.primary,
                custom_id=f"ticket_{name}"
            )
            button.callback = self.create_ticket_callback(name, data)
            self.add_item(button)
    
    def create_ticket_callback(self, category_name, category_data):
        async def callback(interaction: discord.Interaction):
            await create_ticket(interaction, category_name, category_data)
        return callback

async def create_ticket(interaction: discord.Interaction, category_name, category_data):
    """Create a new ticket"""
    guild = interaction.guild
    user = interaction.user
    
    # Check if user already has an open ticket
    existing = discord.utils.get(guild.channels, name=f"ticket-{user.name.lower()}")
    if existing:
        embed = discord.Embed(
            description=f"You already have an open ticket: {existing.mention}",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Get or create ticket category
    category = discord.utils.get(guild.categories, name="TICKETS")
    if not category:
        category = await guild.create_category("TICKETS")
    
    # Increment ticket counter
    guild_id = str(guild.id)
    if guild_id not in ticket_counter:
        ticket_counter[guild_id] = 0
    ticket_counter[guild_id] += 1
    ticket_num = ticket_counter[guild_id]
    save_data()
    
    # Create ticket channel
    channel_name = f"ticket-{ticket_num}-{user.name}"
    
    # Set permissions
    staff_role = guild.get_role(category_data['role_id'])
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    
    if staff_role:
        overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    
    channel = await guild.create_text_channel(
        channel_name,
        category=category,
        overwrites=overwrites
    )
    
    # Send welcome message
    embed = discord.Embed(
        title=f"Ticket #{ticket_num} - {category_data['name']}",
        description=f"Welcome {user.mention}! Support will be with you shortly.",
        color=0x2c3e50
    )
    embed.add_field(name="Category", value=category_data['name'])
    embed.add_field(name="Created", value=discord.utils.format_dt(datetime.now(), 'R'))
    
    # Add close button
    view = TicketControlView(guild.id, ticket_num, user.id)
    await channel.send(content=user.mention, embed=embed, view=view)
    
    # Confirm creation
    confirm_embed = discord.Embed(
        description=f"Ticket created: {channel.mention}",
        color=0x27ae60
    )
    await interaction.response.send_message(embed=confirm_embed, ephemeral=True)

# ===== TICKET CONTROL VIEW =====
class TicketControlView(discord.ui.View):
    def __init__(self, guild_id, ticket_num, user_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.ticket_num = ticket_num
        self.user_id = user_id
    
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user has permission (staff or ticket creator)
        if not has_staff_role(self.guild_id, interaction.user) and interaction.user.id != self.user_id:
            embed = discord.Embed(
                description="You don't have permission to close this ticket",
                color=0xe74c3c
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await self.close_ticket(interaction)
    
    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.primary, custom_id="claim_ticket")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_staff_role(self.guild_id, interaction.user):
            embed = discord.Embed(
                description="Only staff can claim tickets",
                color=0xe74c3c
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            description=f"Ticket claimed by {interaction.user.mention}",
            color=0x27ae60
        )
        await interaction.response.send_message(embed=embed)
    
    async def close_ticket(self, interaction: discord.Interaction):
        channel = interaction.channel
        
        # Save transcript
        await save_transcript(channel, self.ticket_num, interaction.user)
        
        # Send closing message
        embed = discord.Embed(
            title="Ticket Closing",
            description=f"This ticket will be deleted in 5 seconds...",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed)
        
        # Delete channel after delay
        await asyncio.sleep(5)
        await channel.delete(reason=f"Ticket closed by {interaction.user}")

# ===== TICKET SLASH COMMANDS (Staff Only) =====
ticket_group = app_commands.Group(name="ticket", description="Ticket management commands")

@ticket_group.command(name="close", description="Close the current ticket")
async def ticket_close(interaction: discord.Interaction):
    """Close the current ticket"""
    if not has_staff_role(str(interaction.guild_id), interaction.user):
        embed = discord.Embed(
            description="You don't have permission to close this ticket",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # Extract ticket number from channel name
    try:
        ticket_num = int(interaction.channel.name.split('-')[1])
    except:
        embed = discord.Embed(
            description="This command can only be used in ticket channels",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    await save_transcript(interaction.channel, ticket_num, interaction.user)
    
    embed = discord.Embed(
        description="Closing ticket in 5 seconds...",
        color=0xe74c3c
    )
    await interaction.response.send_message(embed=embed)
    
    await asyncio.sleep(5)
    await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")

@ticket_group.command(name="transcript", description="Save transcript of current ticket")
async def ticket_transcript(interaction: discord.Interaction):
    """Save transcript of current ticket"""
    if not has_staff_role(str(interaction.guild_id), interaction.user):
        embed = discord.Embed(
            description="You don't have permission to use this command",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    try:
        ticket_num = int(interaction.channel.name.split('-')[1])
    except:
        embed = discord.Embed(
            description="This command can only be used in ticket channels",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    await save_transcript(interaction.channel, ticket_num, interaction.user)
    
    embed = discord.Embed(
        description="Transcript saved!",
        color=0x27ae60
    )
    await interaction.response.send_message(embed=embed)

@ticket_group.command(name="add", description="Add a user to the ticket")
@app_commands.describe(user="User to add to the ticket")
async def ticket_add(interaction: discord.Interaction, user: discord.Member):
    """Add a user to the current ticket"""
    if not has_staff_role(str(interaction.guild_id), interaction.user):
        embed = discord.Embed(
            description="You don't have permission to use this command",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    await interaction.channel.set_permissions(user, read_messages=True, send_messages=True)
    
    embed = discord.Embed(
        description=f"{user.mention} has been added to this ticket",
        color=0x27ae60
    )
    await interaction.response.send_message(embed=embed)

@ticket_group.command(name="remove", description="Remove a user from the ticket")
@app_commands.describe(user="User to remove from the ticket")
async def ticket_remove(interaction: discord.Interaction, user: discord.Member):
    """Remove a user from the current ticket"""
    if not has_staff_role(str(interaction.guild_id), interaction.user):
        embed = discord.Embed(
            description="You don't have permission to use this command",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    await interaction.channel.set_permissions(user, overwrite=None)
    
    embed = discord.Embed(
        description=f"{user.mention} has been removed from this ticket",
        color=0xe74c3c
    )
    await interaction.response.send_message(embed=embed)

@ticket_group.command(name="rename", description="Rename the current ticket")
@app_commands.describe(name="New name for the ticket")
async def ticket_rename(interaction: discord.Interaction, name: str):
    """Rename the current ticket"""
    if not has_staff_role(str(interaction.guild_id), interaction.user):
        embed = discord.Embed(
            description="You don't have permission to use this command",
            color=0xe74c3c
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    old_name = interaction.channel.name
    await interaction.channel.edit(name=name)
    
    embed = discord.Embed(
        description=f"Channel renamed from `{old_name}` to `{name}`",
        color=0x27ae60
    )
    await interaction.response.send_message(embed=embed)

# ===== HELP COMMAND =====
@bot.tree.command(name="help", description="Show all commands")
async def help_command(interaction: discord.Interaction):
    """Show all commands"""
    embed = discord.Embed(
        title="Ticket Bot Commands",
        description="Professional Ticket Management System",
        color=0x2c3e50
    )
    
    embed.add_field(
        name="Basic Commands",
        value=(
            "`/ping` - Check bot latency\n"
            "`/uptime` - Show bot uptime\n"
            "`/help` - Show this menu\n"
            "`/stats` - Show ticket statistics"
        ),
        inline=False
    )
    
    embed.add_field(
        name="Admin Commands",
        value=(
            "`/admin setup` - Start ticket system setup\n"
            "`/category add <name> <role>` - Add ticket category\n"
            "`/category remove <name>` - Remove category\n"
            "`/category list` - List categories\n"
            "`/panel create` - Create ticket panel\n"
            "`/transcripts set <channel>` - Set transcript channel\n"
            "`/staff add <role>` - Add staff role\n"
            "`/staff remove <role>` - Remove staff role\n"
            "`/staff list` - List staff roles"
        ),
        inline=False
    )
    
    embed.add_field(
        name="Staff Commands",
        value=(
            "`/ticket close` - Close current ticket\n"
            "`/ticket transcript` - Save transcript\n"
            "`/ticket add <user>` - Add user to ticket\n"
            "`/ticket remove <user>` - Remove user\n"
            "`/ticket rename <name>` - Rename ticket"
        ),
        inline=False
    )
    
    embed.add_field(
        name="Features",
        value=(
            "• Multi-category tickets with staff roles\n"
            "• Automatic transcripts\n"
            "• Claim system\n"
            "• User-friendly buttons\n"
            "• Persistent storage\n"
            "• Professional logging"
        ),
        inline=False
    )
    
    embed.set_footer(text="Ranked Tickets")
    await interaction.response.send_message(embed=embed)

# ===== REGISTER COMMANDS =====
bot.tree.add_command(admin_group)
bot.tree.add_command(category_group)
bot.tree.add_command(panel_group)
bot.tree.add_command(transcripts_group)
bot.tree.add_command(staff_group)
bot.tree.add_command(ticket_group)

# ===== RUN BOT =====
if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERROR: No token found! Set TOKEN environment variable.")
        exit(1)
    
    print("🚀 Starting Ticket Bot...")
    bot.run(TOKEN)
