import discord
from discord.ext import tasks, commands
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os
from steam import check_steam_purchases
load_dotenv()

# Configuration
RIOT_API_KEY = os.getenv('RIOT_API_KEY')
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
LOL_CHANNEL_ID = int(os.getenv('LOL_CHANNEL_ID'))
VAL_CHANNEL_ID = int(os.getenv('VAL_CHANNEL_ID'))
REGION = 'americas'
CHECK_INTERVAL = 0.5

# Get all players from environment variable (format: "GameName/Tag,GameName2/Tag2")
PLAYERS = [p for p in os.getenv('ALL_GAMERS', '').split(',') if p]
print(PLAYERS)

# Initialize bot
intents = discord.Intents.default()
intents.messages = True
bot = commands.Bot(command_prefix='!', intents=intents)

class MultiGameTracker:
    def __init__(self):
        self.lol_last_matches = {}  # {puuid: last_match_id}
        self.val_last_matches = {}  # {puuid: last_match_id}
        self.player_names = {}  # {puuid: game_name}
        
    def initialize_players(self):
        """Get PUUIDs for all players"""
        for game_name in PLAYERS:
            # URL decode the game name (replace %20 with space)
            url = f"https://{REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}?api_key={RIOT_API_KEY}"
            print(f"https://{REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}?api_key={RIOT_API_KEY}")
            response = requests.get(url)
            print(response)
            if response.status_code == 200:
                data = response.json()
                puuid = data['puuid']
                self.player_names[puuid] = game_name
                print(f"Tracking player: {game_name} (PUUID: {puuid})")

    def get_recent_lol_match(self, puuid):
        """Get most recent LoL match for a player"""
        if puuid not in self.lol_last_matches:
            self.lol_last_matches[puuid] = None
            
        matches_url = f"https://americas.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count=1&api_key={RIOT_API_KEY}"
        response = requests.get(matches_url)
        
        if response.status_code != 200:
            return None
            
        match_ids = response.json()
        if not match_ids:
            return None
            
        latest_match_id = match_ids[0]
        if latest_match_id == self.lol_last_matches[puuid]:
            return None
            
        match_url = f"https://americas.api.riotgames.com/lol/match/v5/matches/{latest_match_id}?api_key={RIOT_API_KEY}"
        match_response = requests.get(match_url)
        
        if match_response.status_code == 200:
            self.lol_last_matches[puuid] = latest_match_id
            return match_response.json()
        return None

    def get_recent_val_match(self, puuid):
        """Get most recent Valorant match for a player"""
        if puuid not in self.val_last_matches:
            self.val_last_matches[puuid] = None
            
        url = f"https://americas.api.riotgames.com/val/match/v1/matchlists/by-puuid/{puuid}?api_key={RIOT_API_KEY}"
        response = requests.get(url)
        
        if response.status_code != 200:
            return None
            
        matches = response.json().get('history', [])
        if not matches:
            return None
            
        latest_match_id = matches[0]['matchId']
        if latest_match_id == self.val_last_matches[puuid]:
            return None
            
        match_url = f"https://americas.api.riotgames.com/val/match/v1/matches/{latest_match_id}?api_key={RIOT_API_KEY}"
        match_response = requests.get(match_url)
        
        if match_response.status_code == 200:
            self.val_last_matches[puuid] = latest_match_id
            return match_response.json()
        return None

    def format_match(self, match_data, puuid, game_type):
        """Create Discord embed for match"""
        name = self.player_names[puuid]
        
        if game_type == 'lol':
            player = next(p for p in match_data['info']['participants'] if p['puuid'] == puuid)
            embed = discord.Embed(
                title=f"{name}'s Recent LoL Game",
                color=discord.Color.blue()
            )
            embed.add_field(name="Champion", value=player['championName'], inline=True)
            embed.add_field(name="KDA", value=f"{player['kills']}/{player['deaths']}/{player['assists']}", inline=True)
            embed.add_field(name="Result", value="Victory" if player['win'] else "Defeat", inline=True)
            embed.set_footer(text=f"{match_data['info']['gameMode']} | {datetime.fromtimestamp(match_data['info']['gameCreation']/1000).strftime('%m/%d %H:%M')}")
        
        else:  # valorant
            player = next(p for p in match_data['players'] if p['puuid'] == puuid)
            embed = discord.Embed(
                title=f"{name}'s Recent Valorant Game",
                color=0xff4655
            )
            embed.add_field(name="Agent", value=player['character'], inline=True)
            embed.add_field(name="KDA", value=f"{player['stats']['kills']}/{player['stats']['deaths']}/{player['stats']['assists']}", inline=True)
            embed.set_footer(text=f"{match_data['metadata']['mode']} | {datetime.fromtimestamp(match_data['metadata']['game_start']/1000).strftime('%m/%d %H:%M')}")
        
        return embed

# Initialize tracker
tracker = MultiGameTracker()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    tracker.initialize_players()
    check_matches.start()
    check_steam_purchases.start()

@tasks.loop(minutes=CHECK_INTERVAL)
async def check_matches():
    """Check for new matches in both games"""
    lol_channel = bot.get_channel(LOL_CHANNEL_ID)
    val_channel = bot.get_channel(VAL_CHANNEL_ID)
    
    for puuid in tracker.player_names:
        # Check League matches
        lol_match = tracker.get_recent_lol_match(puuid)
        if lol_match and lol_channel:
            await lol_channel.send(embed=tracker.format_match(lol_match, puuid, 'lol'))
        
        # Check Valorant matches
        val_match = tracker.get_recent_val_match(puuid)
        if val_match and val_channel:
            await val_channel.send(embed=tracker.format_match(val_match, puuid, 'val'))

@check_matches.before_loop
async def before_checking():
    await bot.wait_until_ready()

@bot.command(name='forcecheck')
async def force_check(ctx, game: str = None):
    """Force a check for recent games (!forcecheck lol/val)"""
    for puuid in tracker.player_names:
        if not game or game.lower() == 'lol':
            lol_match = tracker.get_recent_lol_match(puuid)
            if lol_match:
                await ctx.send(embed=tracker.format_match(lol_match, puuid, 'lol'))
        
        if not game or game.lower() == 'val':
            val_match = tracker.get_recent_val_match(puuid)
            if val_match:
                await ctx.send(embed=tracker.format_match(val_match, puuid, 'val'))

bot.run(DISCORD_BOT_TOKEN)