from functools import partial
from typing import Callable

import discord
import requests
from discord import ButtonStyle
from fuzzywuzzy import fuzz


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

    def reset_fct(self):
        self.function = None
        return self


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
    def __init__(self, label, minim, maxi, option, function: callable, emoji=None):
        self.label = label
        self.min = minim
        self.max = maxi
        self.option = option
        self.function = function
        self.emoji = emoji


class TextInput:
    def __init__(self, label, min_length, max_length, check=None, default=None, required=True):
        self.label = label
        self.min_length = min_length
        self.max_length = max_length
        self.check = check
        self.default = default
        self.required = required


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
    def __init__(self, text_inputs: list[TextInput], callback: Callable = callable):
        super().__init__(title="Movie")
        self.text_inputs = {}
        self.callback = callback
        for text_input in text_inputs:
            if text_input.label in [i.label for i in self.text_inputs]:
                raise ValueError("Il faut des labels différents")
            _text_input = discord.ui.TextInput(label=text_input.label,
                                               min_length=text_input.min_length,
                                               max_length=text_input.max_length,
                                               default=text_input.default,
                                               required=text_input.required)
            self.text_inputs.update({_text_input: text_input})
            self.add_item(_text_input)

    async def on_submit(self, interaction: discord.Interaction):
        values = {}
        for i, j in self.text_inputs.items():
            if j.check:
                if not j.check(i.value):
                    values.update({i.label: None})
                    continue
            values.update({i.label: i.value})

        await self.callback(interaction, values)


async def search(entry: str, liste: list, nbr: int = 25):
    tried_list = list(sorted(liste, key=lambda x: fuzz.partial_ratio(entry, x)))[::-1]
    return tried_list[:(min(nbr, len(liste)))]


class FormParams:
    def __init__(self, name, description, value=None, key=None, falcutatif=False, formatage=None):
        self.name = name
        self.value_ = value
        self.key = key or name
        self.description = description
        self.facultatif = falcutatif
        self.formatage = formatage

    @property
    def value(self):
        return self.value_

    @value.setter
    def value(self, value):
        self.value_ = value


class FormText(FormParams):
    def __init__(self, name, description, check: partial | None = None, *args, **kwargs):
        super().__init__(name, description, *args, **kwargs)
        self.check = check


class FormEnum(FormParams):
    def __init__(self, name, description, params: list[SelecteurOption], minim, maxi, *args, **kwargs):
        super().__init__(name, description, *args, **kwargs)
        self.value_ = self.value_ or []
        self.params = params
        self.min = minim
        self.max = maxi

    @property
    def value(self):
        if self.value_:
            return ", ".join([str(value) for value in self.value_])
        else:
            return None

    @value.setter
    def value(self, value):
        self.value_ = value


class FormBool(FormParams):
    def __init__(self, name, description, params: tuple[any, any], *args, **kwargs):
        super().__init__(name, description, *args, **kwargs)
        self.value_ = self.value_ if self.value_ is not None else []
        self.params = params

    def switch(self):
        self.value = self.params[self.params.index(self.value) - 1] if self.value in self.params else self.params[0]


class FormList(FormParams):
    def __init__(self, name, description, params: dict, value: list | None = None, *args, **kwargs):
        super().__init__(name, description, value=value, *args, **kwargs)
        self.params: dict = params
        self.reverse_params: dict = {param[1]: param[0] for param in self.params.items()}
        self.value_ = self.value_ or []

    @property
    def value(self):
        if self.value_:
            return ", ".join([str(self.params[value.__str__()]) for value in self.value_])
        else:
            return None

    @value.setter
    def value(self, value):
        self.value_ = value


class Form:
    def __init__(self, ctx, title: str, params: list[FormParams], callback):
        self.ctx = ctx
        self.title = title
        self.params = params
        self.main_embed = self.embed
        self.callback_ = callback

    @property
    def can_valide(self):
        for param in self.params:
            if param.value is None and not param.facultatif:
                return False
        return True

    @property
    def embed(self):

        description = []
        for param in self.params:
            aff_value = "?"
            if param.value is not None:
                aff_value = param.value
            if param.formatage:
                aff_value = param.formatage(aff_value)
            description.append(f"**{param.name}**:  {aff_value}")

        return discord.Embed(
            title=self.title,
            description="\n".join(description))

    @property
    def view(self):
        options = [
            Button(param.name, discord.ButtonStyle.green, partial(self.callback, param=param)) for param in self.params
        ]
        if self.can_valide:
            options += [
                Button("Valider", discord.ButtonStyle.primary,
                       partial(self.valide, values={param.key: param.value_ for param in self.params}))]
        options.append(Button("Annuler", discord.ButtonStyle.red, self.cancel))

        return View(self.ctx, options)

    async def valide(self, interaction: discord.Interaction, values):
        await self.callback_(interaction, values)

    @staticmethod
    async def cancel(interaction: discord.Interaction):
        await interaction.response.edit_message(content="Form Annulé avec succès", embed=None, view=None)

    async def callback(self, interaction: discord.Interaction, param: FormParams):
        if isinstance(param, FormText):
            modal = Modal([TextInput(param.name, 1, 32,
                                     default=param.value)], partial(self.enter_txt, param=param))
            await interaction.response.send_modal(modal)
        elif isinstance(param, FormEnum):
            embed = discord.Embed(title=self.title, description=param.description)
            view = View(self.ctx, [
                Selecteur(param.name, param.min, param.max, sorted(param.params, key=lambda x: x.label),
                          partial(self.get_enum, param=param))])
            await interaction.response.edit_message(embed=embed, view=view)
        elif isinstance(param, FormList):
            await self.menu_search(interaction, "", set(), param)
        elif isinstance(param, FormBool):
            param.switch()
            await interaction.response.edit_message(embed=self.embed, view=self.view)

    async def enter_txt(self, interaction: discord.Interaction, values: dict, param: FormText):
        value = values[param.name]
        is_check = True
        if param.check:
            is_check = param.check(value)
        if not is_check:
            await interaction.response.send_message("Saisi Incorecte", ephemeral=True)
        else:
            param.value = value
            await interaction.response.edit_message(embed=self.embed, view=self.view)

    async def get_enum(self, interaction: discord.Interaction, values: list, param: FormEnum):
        param.value = values
        await interaction.response.edit_message(embed=self.embed, view=self.view)

    async def searche_list(self, interaction: discord.Interaction, values, param: FormList):
        modal = Modal([
            TextInput(param.name, 1, 256)
        ], partial(self.resp_search_list, values=values, param=param))
        await interaction.response.send_modal(modal)

    async def resp_search_list(self, interaction: discord.Interaction, text_values: dict, values, param: FormList):
        value = text_values[param.name]
        await self.menu_search(interaction, value, values, param)

    async def menu_search(self, interaction: discord.Interaction, entry, values, param: FormList):
        resultes = [param.reverse_params[x] for x in await search(entry, list(param.params.values()), 25)]
        options = [
            Button("Rechercher", discord.ButtonStyle.green, partial(self.searche_list, values=values, param=param)),
            Selecteur("Ajouter", 1, min(25, len(resultes)), [
                SelecteurOption(param.params[x], '', x) for x in resultes],
                      partial(self.list_add_value, search_v=entry, values=values, param=param)),
            Button("Valider", discord.ButtonStyle.green, partial(self.valide_list, values=values, param=param)),
            Button("Annuler", discord.ButtonStyle.red, self.cancel_list)
        ]
        if values:
            options.insert(2, Selecteur("Retirer", 1, min(25, len(values)), [
                SelecteurOption(param.params[x.__str__()], '', x) for x in values],
                      partial(self.list_remove_value, search_v=entry, values=values, param=param)))

        embed = discord.Embed(title=self.title,
                              description=param.description + f"\n **Values:** "
                                                              f"{", ".join([param.params[value] for value in values])}")
        view = View(self.ctx, options)
        await interaction.response.edit_message(embed=embed, view=view)

    async def list_add_value(self, interaction: discord.Interaction, value, search_v, values: set, param: FormList):
        values |= set(value)
        await self.menu_search(interaction, search_v, values, param)

    async def list_remove_value(self, interaction: discord.Interaction, value, search_v, values: set, param: FormList):
        values -= set(value)
        await self.menu_search(interaction, search_v, values, param)

    async def valide_list(self, interaction: discord.Interaction, values, param: FormList):
        param.value = values
        await interaction.response.edit_message(embed=self.embed, view=self.view)

    async def cancel_list(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.embed, view=self.view)
