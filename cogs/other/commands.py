import discord.ext.commands
from discord import app_commands, Member, Interaction, InteractionResponse


class Command(discord.ext.commands.Cog):
    def __init__(self, bot, logger):
        self.bot = bot
        self.logger = logger

    @app_commands.command(name="harcele")
    async def harcele(self, interaction: Interaction, user: Member, nbr: int, msg: str):
        response: InteractionResponse = interaction.response
        await response.defer()
        for i in range(nbr):
            await user.send(msg)

async def setup(bot):
    await bot.add_cog(Command(bot, bot.logger))
