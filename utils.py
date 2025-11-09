from functools import partial
from typing import Callable
import discord
import requests
from discord import ButtonStyle
from discord.ui import TextDisplay, ActionRow


def str_hour(x):
    return f"{x // 60}H{x % 60:>02}"


def get_movies_list(query, apkey):
    url = f"https://api.themoviedb.org/3/search/movie?include_adult=false&language=fr&page=1&query={query}"

    headers = {
        f"accept": "application/json",
        f"Authorization": f"Bearer {apkey}"
    }
    return requests.get(url, headers=headers).json()


def get_detail(movie_id, apkey):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}?language=fr"
    headers = {
        f"accept": "application/json",
        f"Authorization": f"Bearer {apkey}"
    }
    movie = requests.get(url, headers=headers).json()
    print(movie)
    if movie.get("release_date"):
        movie_date = movie["release_date"].split("-")
        movie_date = f"{movie_date[2]}/{movie_date[1]}/{movie_date[0]}"
    else:
        movie_date = "?"
    descr = (f"durée: {str_hour(movie["runtime"])}; "
             f"Sortie: {movie_date}")
    return (movie["title"], movie["runtime"], movie["popularity"], descr, movie["poster_path"], movie["overview"],
            movie["production_companies"], movie["id"])


def get_movies(query, apkey) -> list[tuple[str, str, int]]:
    """ return list[tuple(title, runtime, popularity, description, image, resumé, studio, id)]"""
    movies = []
    for movie in get_movies_list(query, apkey)["results"]:
        movies.append((movie["title"], f"{movie.get('release_date') or '?'}", movie["id"]))
    return movies


class Button:
    def __init__(self, label: str, color: ButtonStyle | int, function, emoji=None, url=None):
        self.label = label
        self.color = color
        self.function = function
        self.emoji = emoji
        self.url = url
        self._item = None

    def reset_fct(self):
        self.function = None
        return self

    @property
    def item(self):
        if not self._item:
            self._item = discord.ui.Button(label=self.label, style=self.color,
                                           disabled=not not (self.url or self.function), url=self.url)
        return self._item

class SwitchButton(Button):
    def __init__(self, buttons: list[Button], function):
        super().__init__(buttons[0].label, buttons[0].color, self.switch, buttons[0].emoji)
        self.buttons = buttons
        self._function = function
        self.pos = 0

    async def switch(self, *args, **kwargs):
        self.pos = self.pos + 1 if self.pos < len(self.buttons) - 1 else 0
        self.label = self.buttons[self.pos].label
        self.color = self.buttons[self.pos].color
        self.emoji = self.buttons[self.pos].emoji
        await self.buttons[self.pos].function()
        await self._function(*args, **kwargs)


class Selecteur:
    def __init__(self, label, minim, maxi, option, function: Callable, emoji=None):
        self.label = label
        self.min = minim
        self.max = maxi
        self.option = option
        self.function = function
        self.emoji = emoji


class TextInput:
    def __init__(self, label, min_length, max_length, name, check=None, default=None, required=True):
        self.label = label
        self.min_length = min_length
        self.max_length = max_length
        self.name = name
        self.check = check
        self.default = default
        self.required = required
        self._item = None

    @property
    def item(self) -> discord.ui.TextInput:
        if not self._item:
            self._item = discord.ui.TextInput(label=self.label, min_length=self.min_length, max_length=self.max_length,
                                    default=self.default, required=self.required)
        return self._item


class SelecteurOption:
    def __init__(self, label, description, value):
        self.label = label
        self.description = description
        self.value = value


class View(discord.ui.View):
    def __init__(self, author, list_button, timeout=3600):
        super().__init__(timeout=timeout)
        self.author = author

        for i in list_button:
            if isinstance(i, Button):
                button: discord.ui.Button = discord.ui.Button(label=i.label, style=i.color,
                                                              disabled=i.function is None and i.url is None,
                                                              emoji=i.emoji, url=i.url)
                button.callback = partial(self.button_callback, button_def=i)
                self.add_item(button)

            elif isinstance(i, Selecteur):
                select: discord.ui.Select = discord.ui.Select(
                    placeholder=i.label, min_values=i.min, max_values=i.max, options=[
                        discord.SelectOption(label=j.label, description=j.description, value=j.value) for j in i.option
                    ], disabled=i.function is None
                )
                select.callback = partial(self.select_callback, select_def=i)
                self.add_item(select)

    async def button_callback(self, interaction: discord.Interaction, button_def: Button):
        if interaction.user != self.author or not button_def.function:
            await interaction.response.defer()
            return
        await button_def.function(interaction)

    async def select_callback(self, interaction: discord.Interaction, select_def: Selecteur):
        if interaction.user != self.author or not select_def.function:
            await interaction.response.defer()
            return
        data = interaction.data["values"]
        if select_def.max == select_def.min == 1:
            data = data[0]
        await select_def.function(interaction, data)


class Modal(discord.ui.Modal):
    def __init__(self, items: list[TextInput | discord.ui.Item | Button], callback: Callable = callable):
        super().__init__(title="Movie")
        self.text_inputs: dict[discord.ui.TextInput, TextInput] = {}
        self.callback = callback
        if not items:
            raise IndexError("au moins 1 item requis")

        for item in items:
            if isinstance(item, TextInput):
                if item.name in [i.label for i in self.text_inputs]:
                    raise ValueError("Il faut des labels différents")

                self.text_inputs.update({item.item: item})
                self.add_item(item.item)
            elif isinstance(item, (TextDisplay, ActionRow)):
                self.add_item(item)


    async def on_submit(self, interaction: discord.Interaction):
        values = {}
        for i, j in self.text_inputs.items():
            if j.check:
                print(i.value)
                if not j.check(i.value):
                    values.update({j.name: None})
                    continue
            values.update({j.name: i.value})

        await self.callback(interaction, values)

