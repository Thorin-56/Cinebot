import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from logger import Logger

load_dotenv()
TOKEN = os.getenv("TOKEN")
logger = Logger()

intents = discord.Intents.all()


class MyBot(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logger = logger

    async def setup_hook(self):
        cogs_path = "cogs"
        file_paths = ["movies.movies"]
        for filename in file_paths:
            await self.load_extension(f'{cogs_path}.{filename}')
            print(f"Loaded Cog: {filename}")


bot = MyBot(command_prefix="!", intents=intents)


@bot.event
@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=1073644641263562804))
    await bot.tree.sync()
    logger.log("[system] BOT pret")


@bot.event
async def on_connect():
    logger.log("[system] BOT connecté")


@bot.event
async def on_disconnect():
    logger.log("[system] BOT déconnecté")


@bot.event
async def on_app_command_completion(interaction: discord.Interaction, command: discord.app_commands.Command):
    content = f"[command] {interaction.user.name} as utilisé {command.name}"
    if command.parameters:
        params = ""
        for name, value in interaction.namespace.__dict__.items():
            params += f"{name}={value}, "
        content += f" avec ({params[:-2]})"

    logger.log(content)


bot.run(TOKEN)
logger.log("[system] BOT arrété")
