import discord
from discord.ext import commands, tasks
from steamwebapi.api import ISteamUser, IPlayerService
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()
# Configuration
STEAM_API_KEY = os.getenv('STEAM_API_KEY')
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
CHANNEL_ID = int(os.getenv('LOL_CHANNEL_ID'))
STEAM_IDS = ['76561198123091187']  # List of Steam IDs to monitor

# Initialize APIs
steam_user = ISteamUser(steam_api_key=STEAM_API_KEY)
player_service = IPlayerService(steam_api_key=STEAM_API_KEY)

# Bot setup
intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

# Store recent games to avoid duplicate notifications
recent_games = {}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    check_steam_purchases.start()

@tasks.loop(minutes=5)
async def check_steam_purchases():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("Channel not found!")
        return

    for steam_id in STEAM_IDS:
        try:
            # Get player's recently played games
            player_games = player_service.get_recently_played_games(steam_id).get('response', {}).get('games', [])
            
            # Get player's summary for their name
            player_summary = steam_user.get_player_summaries(steam_id).get('response', {}).get('players', [{}])[0]
            player_name = player_summary.get('personaname', 'Unknown Player')
            
            for game in player_games:
                appid = game.get('appid')
                game_name = game.get('name')
                playtime = game.get('playtime_2weeks', 0) / 60  # Convert to hours
                
                # Check if this is a new game (not in our recent_games dict)
                if appid not in recent_games.get(steam_id, {}):
                    # Add to recent games
                    if steam_id not in recent_games:
                        recent_games[steam_id] = {}
                    recent_games[steam_id][appid] = True
                    
                    # If playtime is very low (likely just purchased), send notification
                    if playtime < 0.5:  # Less than 30 minutes played
                        embed = discord.Embed(
                            title="🎮 New Steam Purchase!",
                            description=f"**{player_name}** just bought **{game_name}** on Steam!",
                            color=0x00ff00,
                            timestamp=datetime.utcnow()
                        )
                        embed.set_thumbnail(url=f"https://steamcdn-a.akamaihd.net/steam/apps/{appid}/header.jpg")
                        embed.set_footer(text="Steam Purchase Tracker")
                        
                        await channel.send(embed=embed)
            
            # Clean up old games (optional, to prevent memory issues)
            if len(recent_games.get(steam_id, {})) > 20:
                # Keep only the 10 most recent games
                recent_games[steam_id] = dict(list(recent_games[steam_id].items())[:10])
                
        except Exception as e:
            print(f"Error checking Steam purchases for {steam_id}: {e}")

@check_steam_purchases.before_loop
async def before_check_purchases():
    await bot.wait_until_ready()