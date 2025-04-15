import discord
from discord.ext import tasks, commands
import requests
import asyncio
from datetime import datetime, timedelta
import os

RIOT_API_KEY = os.getenv('RIOT_API_KEY')
DISCORD_API_KEY = os.getenv('DISCORD_BOT_TOKEN')
DISCORD_CHANNEL = os.getenv('CHANNEL_ID')

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

# Configuration
REGION = "na1"  # Change to your region
SUMMONER_NAME = "Upper Decky"  # Without tag
TAG = '6mil'
CHECK_INTERVAL = 20  # Minutes

# Initialize bot
intents = discord.Intents.default()
intents.messages = True
bot = commands.Bot(command_prefix='!', intents=intents)

class LoLGameTracker:
    def __init__(self):
        self.last_checked_game_id = None
        self.summoner_puuid = None
        self.summoner_name = None
        
        # Initialize summoner data
        self.initialize_summoner()

    def initialize_summoner(self):
        """Get summoner PUUID and name"""
        print('test')
        summoner_url = f"https://{REGION}.api.riotgames.com/lol/summoner/v4/summoners/by-name/{SUMMONER_NAME}?api_key={RIOT_API_KEY}"
        response = requests.get(summoner_url)
        print('test')
        
        if response.status_code == 200:
            data = response.json()
            self.summoner_puuid = data['puuid']
            self.summoner_name = data['name']
            print(f"Tracking summoner: {self.summoner_name} (PUUID: {self.summoner_puuid})")
        else:
            print(f"Error initializing summoner: {response.status_code}")

    def get_recent_match(self):
        """Get the most recent match for the summoner"""
        if not self.summoner_puuid:
            return None
            
        # Get match list (last 20 matches)
        matches_url = f"https://americas.api.riotgames.com/lol/match/v5/matches/by-puuid/{self.summoner_puuid}/ids?start=0&count=1&api_key={RIOT_API_KEY}"
        matches_response = requests.get(matches_url)
        
        if matches_response.status_code != 200:
            print(f"Error getting match list: {matches_response.status_code}")
            return None
            
        match_ids = matches_response.json()
        if not match_ids:
            return None
            
        latest_match_id = match_ids[0]
        
        # If this is the same as our last checked game, return None
        if latest_match_id == self.last_checked_game_id:
            return None
            
        # Get match details
        match_url = f"https://americas.api.riotgames.com/lol/match/v5/matches/{latest_match_id}?api_key={RIOT_API_KEY}"
        match_response = requests.get(match_url)
        
        if match_response.status_code != 200:
            print(f"Error getting match details: {match_response.status_code}")
            return None
            
        match_data = match_response.json()
        self.last_checked_game_id = latest_match_id
        
        return match_data

    def format_match_info(self, match_data):
        """Format match data into a readable string"""
        # Find the player in the participants
        player_data = None
        for participant in match_data['info']['participants']:
            if participant['puuid'] == self.summoner_puuid:
                player_data = participant
                break
                
        if not player_data:
            return "Could not find player in match data"
            
        # Convert timestamp to readable format
        game_time = datetime.fromtimestamp(match_data['info']['gameCreation'] / 1000)
        game_duration = timedelta(seconds=match_data['info']['gameDuration'])
        
        # Basic match info
        embed = discord.Embed(
            title=f"{self.summoner_name}'s Recent Game",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Champion", value=player_data['championName'], inline=True)
        embed.add_field(name="Role", value=player_data['teamPosition'], inline=True)
        embed.add_field(name="KDA", value=f"{player_data['kills']}/{player_data['deaths']}/{player_data['assists']}", inline=True)
        embed.add_field(name="Result", value="Victory" if player_data['win'] else "Defeat", inline=True)
        embed.add_field(name="Game Mode", value=match_data['info']['gameMode'], inline=True)
        embed.add_field(name="Duration", value=str(game_duration), inline=True)
        embed.set_footer(text=f"Played at {game_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        return embed

# Initialize tracker
tracker = LoLGameTracker()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    check_recent_game.start()

@tasks.loop(minutes=CHECK_INTERVAL)
async def check_recent_game():
    channel = bot.get_channel(DISCORD_CHANNEL)  # Replace with your channel ID
    if not channel:
        print("Channel not found")
        return
        
    recent_match = tracker.get_recent_match()
    if recent_match:
        match_embed = tracker.format_match_info(recent_match)
        await channel.send(embed=match_embed)

@check_recent_game.before_loop
async def before_check_recent_game():
    await bot.wait_until_ready()

@bot.command(name='forcecheck')
async def force_check(ctx):
    """Force a check for recent games"""
    recent_match = tracker.get_recent_match()
    if recent_match:
        match_embed = tracker.format_match_info(recent_match)
        await ctx.send(embed=match_embed)
    else:
        await ctx.send(f"No new games found for {tracker.summoner_name}")

bot.run(DISCORD_API_KEY)