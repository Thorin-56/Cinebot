import inspect
from functools import  wraps

import discord.ui
from discord import Interaction
from utils import Modal


# Decorateurs
def valide_inter():
    def decorateur(func):
        @wraps(func)
        async def wrapper(self, interaction: Interaction = None, *args, **kwargs):
            if interaction:
                await interaction.response.defer()
            if inspect.iscoroutinefunction(func):
                result = await func(self, *args, **kwargs)
            else:
                result = func(self, *args, **kwargs)
            return result

        return wrapper

    return decorateur

def valide_act():
    def decorateur(func):
        @wraps(func)
        async def wrapper(self, interaction: Interaction, *args, **kwargs):
            await  interaction.response.send_modal(
                Modal([discord.ui.TextDisplay("Validez vous")], lambda inter, _: func(self, inter)))

        return wrapper

    return decorateur


def menu(**_kwargs):
    def decorateur(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            if inspect.iscoroutinefunction(func):
                result = await func(self, *args, **kwargs)
            else:
                result = func(self, *args, **kwargs)
            await self.m_menu(**_kwargs)
            return result

        return wrapper

    return decorateur