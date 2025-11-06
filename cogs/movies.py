import os
from copy import copy

from discord import app_commands, Embed
from discord.ext import commands
from dotenv import load_dotenv

from database_manager import DatabaseManager
from decorations.movies import *
from filter import *
from utils import *

load_dotenv()

# Fonctions
async def get_authors():
    users = await DatabaseManager.execute_query("SELECT users.id, users.username FROM users "
                                  "INNER JOIN movies on movies.created_by = users.id GROUP by users.id;", fetch=True)
    return dict([*map(lambda x: x[::-1], users)])

async def get_genres():
    genres = await DatabaseManager.execute_query("SELECT id, name FROM genres", fetch=True)
    return genres

def get_query(_base: str, filters: Filters):
    base = (
        f"{_base} "
        f"LEFT JOIN d_genre_movie d on d.movie_id = m.id "
        f"LEFT JOIN genres g on g.id = d.genre_id "
        f"WHERE TRUE")

    SQLQueryList = [base]

    wheres = filters.get_filter()
    sorters = filters.get_sorters()
    if wheres:
        SQLQueryList.append(" ".join(wheres))
    if sorters:
        SQLQueryList.append("ORDER BY")
        SQLQueryList.append(", ".join(sorters))

    return " ".join(SQLQueryList)

async def add_movie(movie: "Movie"):
    query = f"INSERT INTO movies (name, duration, to_see, created_by, TMDB_id, url) " \
            f"VALUES (%s, %s, %s, %s, %s, %s)"
    authors = await get_authors()
    if not authors[movie.author.name]:
        f_query = (f"INSERT INTO users (username, discord_id) "
                   f"VALUES (%s, %s)")
        await DatabaseManager.execute_query(f_query, (movie.author.name, movie.author.id))
    authors = await get_authors()

    rown, movie_id = await DatabaseManager.execute_query(query, (movie.title, movie.duration, movie.to_see,
                                                                 authors[movie.author.name], movie.tmdb_id, movie.url))

    for genre in movie.genre:
        query = f"INSERT INTO d_genre_movie (genre_id, movie_id) " \
                f"VALUES ({genre}, {movie_id})"
        await DatabaseManager.execute_query(query)

async def edit_movie(movie: "Movie"):
    query = f"UPDATE movies m SET name=%s, duration=%s, to_see=%s, TMDB_id=%s, url=%s WHERE m.id={movie.movie_id}"
    await DatabaseManager.execute_query(query, (movie.title, movie.duration, movie.to_see, movie.tmdb_id, movie.url))

    genres = await get_genre_movie(movie.movie_id)
    for d_id, genre in genres:
        if genre not in movie.genre:
            query = f"DELETE FROM d_genre_movie d WHERE d.id={d_id}"
            await DatabaseManager.execute_query(query)
    for genre in movie.genre:
        if genre not in genres:
            query = f"INSERT INTO d_genre_movie (genre_id, movie_id) " \
                f"VALUES ({genre}, {movie.movie_id})"
            await DatabaseManager.execute_query(query)

async def get_genre_movie(movie_id):
    query = f"SELECT d.id, g.id FROM genres g JOIN d_genre_movie d on d.genre_id=g.id WHERE d.movie_id={movie_id}"
    return await DatabaseManager.execute_query(query, fetch=True)

async def delete_movie(movie_id):
    query = f"DELETE FROM movies WHERE id={movie_id}"
    await DatabaseManager.execute_query(query)

async def get_config(user_id):
    query = f"SELECT c.max_movie_in_page FROM config c WHERE c.user_id IN {user_id}"
    config =  await DatabaseManager.execute_query(query, fetch=True)
    if not config:
        query = (f"INSERT INTO config (user_id, max_movie_in_page) "
                 f"VALUES ({user_id}, %s)")
        default_config = (await get_config(USER_ID_DEFAULT))[0]
        _, last_id = await DatabaseManager.execute_query(query, default_config)
        return [default_config]
    return config

async def edit_config(config, user_id):
    query = f"UPDATE config SET max_movie_in_page=%s WHERE user_id={user_id}"
    await DatabaseManager.execute_query(query, config)

def is_date_format(x: str):
    if len(x) != 10:
        return False
    if x.count("/") != 2:
        return False
    if not (x[2] == x[5] == "/"):
        return False
    if not (x[:2].isdigit() and x[3:5].isdigit() and x[6:].isdigit()):
        return False
    try:
        datetime.datetime(*[*map(int, x.split('/'))][::-1])
    except ValueError:
        return False
    return True


# Enum
class Emoji(Enume):
    SEP = discord.PartialEmoji(name="sep", id=1419289057187594342)
    FILTRE = discord.PartialEmoji(name="filter", id=1436077693744582887)
    ARROW_UP = discord.PartialEmoji(name="arrow_up", id=1436080735499976836)
    ADD = discord.PartialEmoji(name="add", id=1436071687451050165)
    ARROW_DOWN = discord.PartialEmoji(name="arrow_down", id=1436077245608235181)
    SETTINGS = discord.PartialEmoji(name="settings", id=1436052141939884153)

# Constante
USER_ID_DEFAULT = 0
NONE_BTN = Button("", ButtonStyle.grey, None, emoji=Emoji.SEP.value)
SORTER_VALUES = {
    "nale": {"id": "name",
              "name": "Titre"},
    "duration": {"id": "duration",
                 "name": "Durée"},
    "created_on": {"id": "created_on",
                 "name": "Date d'ajout"},
    "to_see": {"id": "to_see",
                 "name": "Vue"},
}

FILTER_VALUES = {
    "duration": {"id": "duration",
                 "name": "Durée",
                 "type": FilterOpt.INT},
    "created_on": {"id": "created_on",
                 "name": "Date d'ajout",
                   "type": FilterOpt.DATE},
    "to_see": {"id": "to_see",
                 "name": "Vue",
               "type": FilterOpt.Enum,
               "enum": (("Vue", 0), ("A Voir", 1))},
    "genres": {"id": "genres",
                 "name": "Genres",
               "type": FilterOpt.Genre},
}

# Objets
class Movie:
    def __init__(self, title=None, duration=None, genre=None, to_see=None, author=None, movie_id=None, tmdb_id=None, url=None):
        self.title = title
        self.genre: list = genre or []
        self.duration = duration
        self.to_see = to_see
        self.author: discord.User = author
        self.movie_id = movie_id
        self.tmdb_id = tmdb_id
        self.url = url

    def is_ready(self):
        return None not in (self.title,self.duration,self.to_see)

    def __repr__(self):
        return f"{('🔴', '🟢')[self.to_see]} {self.title} {self.duration} {self.genre}"


class Movies(commands.Cog):
    def __init__(self, bot, logger):
        self.bot: commands.Bot = bot
        self.logger = logger

    @app_commands.command(name="menu")
    @app_commands.checks.has_role("movies")
    async def c_menu(self, interaction: Interaction):

        message = await interaction.response.send_message(embed=Embed(title="Chargement..."), ephemeral=True,
                                                          delete_after=900)
        _menu = MainMenu(self, interaction.user, message)
        await _menu.setup()
        self.bot.loop.call_later(900, _menu.cleanup)


class MainMenu:
    def __init__(self, parent, author, message):
        self.parent: Movies = parent
        self.bot = self.parent.bot
        self.logger = self.parent.logger
        self.message: discord.InteractionCallbackResponse = message

        self.author: discord.User | discord.Member = author

        # Config
        self.max_movie_in_page: int = 0

        # Pages
        self.page: int = 0
        self.len_pages: int | None = None

        # Movie selectionne
        self.movie_select_in_page: int | None = None
        self.movies: None | list[Movie] = None
        self.btn_actions = [
            Button("🗑️", ButtonStyle.red, partial(self.f_validate_btn, func=self.delete_movie)),
            Button("📝", ButtonStyle.green, self.edit_movie),
            Button("👁️", ButtonStyle.green, None),
        ]
        self.btn_cancel = Button("Annuler", ButtonStyle.grey, self.cancel_validation)
        self.movie_select_action = 0
        self.validate_btn = None

        self.genres = None
        self.filters = Filters()

    def cleanup(self):
        del self

    @valide_inter()
    async def setup(self):
        default_config, config = (await get_config(((await get_authors())[self.author.name], USER_ID_DEFAULT)))
        self.max_movie_in_page = config[0] if config and config[0] else default_config[0]

        self.genres = dict(await get_genres())
        self.filters.genres = self.genres

        self.page = 0
        await self.count_pages()
        await self.m_menu()

    @property
    def view(self) -> View:

        slc_select_movie_title = self.movies[self.movie_select_in_page].title \
            if self.movie_select_in_page is not None else "Selecionner un film"
        slc_select_movie_2 = [
            Selecteur(slc_select_movie_title, 1, 1, [
                SelecteurOption(f"{"🔷" if k == self.movie_select_in_page else ""} {movie.title}", "", k)
                for k, movie in enumerate(self.movies)], self.select_movie)
        ]

        btn_arrow = [
            Button("⏪", ButtonStyle.blurple, (None, self.move_double_left_page)[self.page > 0]),
            Button("◀️", ButtonStyle.blurple, (None, self.move_left_page)[self.page > 0]),
            Button("▶️", ButtonStyle.blurple, (None, self.move_right_page)[self.page < self.len_pages - 1]),
            Button("⏩", ButtonStyle.blurple, (None, self.move_double_right_page)[self.page < self.len_pages - 1]),

        ]

        if not self.validate_btn:
            btn_action = [
                Button("⬅️", ButtonStyle.green, partial(self.switch_action, _dir=-1)),
                copy(self.btn_actions[self.movie_select_action]),
                Button("➡️", ButtonStyle.green, partial(self.switch_action, _dir=1)),
            ]
            if self.movie_select_in_page is None:
                btn_action[1].reset_fct()
            if self.movie_select_action in (2, -1) and self.movie_select_in_page is not None and self.movies[
                self.movie_select_in_page].url:
                btn_action[1].url = self.movies[self.movie_select_in_page].url
        else:
            btn_action = [
                self.validate_btn,
                self.btn_cancel,
                Button("", ButtonStyle.grey, None, emoji=Emoji.SEP.value)
            ]

        btn_add_movie = [Button("➕", ButtonStyle.grey, self.add_movie)]
        btn_config = [Button("⚙️", ButtonStyle.grey, self.edit_config)]

        btn_sorter = Button("Trier", ButtonStyle.green, self.open_sorter_menu, emoji=Emoji.ARROW_UP.value)
        btn_filter = Button("Filtrer", ButtonStyle.green, self.open_filter_menu, emoji=Emoji.FILTRE.value)


        if self.movies:
            btn = btn_arrow + [NONE_BTN] + slc_select_movie_2 + btn_action + btn_add_movie + btn_config + [btn_sorter, btn_filter]
        else:
            btn = [btn_filter]

        return View(self.author, btn, None)

    @property
    def embed(self) -> Embed:
        embed = Embed(title="Menu")

        movies = list([(
            f"{('🔴', '🟢')[movie.to_see]} {movie.title}",
            f"{str_hour(movie.duration)}" + ("", " \n   ")[len(movie.title) > 45] or "/",
        ) for movie in self.movies])

        movies = [*map(lambda y: [*map(lambda x: f"```{x}```", y)], movies)]

        if self.movie_select_in_page is not None:
            movies[self.movie_select_in_page] = [*map(lambda x: f"```ansi\n\u001b[34;1m{x[3:-3]}```",
                                                      movies[self.movie_select_in_page])]
        if movies:
            movies_titles, movies_durations = zip(*movies)

            embed.add_field(name="Durée:", value="\n".join(movies_durations), inline=True)
            embed.add_field(name="Films:", value="\n".join(movies_titles), inline=True)
            embed.set_footer(text=f"Pages: {self.page + 1}/{self.len_pages}")
        else:
            embed.add_field(name="Aucun film correspond", value="changer vos filtres")
        return embed

    # Fonction Boutons
    # Selecteur
    @valide_inter()
    @menu(load_movie=False)
    def select_movie(self, nbr):
        self.movie_select_in_page = None if self.movie_select_in_page == int(nbr) else int(nbr)

    # Movie actions
    @valide_inter()
    @menu(load_movie=False)
    def switch_action(self, _dir: int):
        self.movie_select_action += _dir
        if self.movie_select_action >= len(self.btn_actions):
            self.movie_select_action = 0
        elif self.movie_select_action < 0:
            self.movie_select_action = len(self.btn_actions) - 1

    # Arrows
    @valide_inter()
    @menu()
    def move_double_left_page(self):
        self.page = max(self.page - 5, 0)

    @valide_inter()
    @menu()
    def move_left_page(self):
        self.page = self.page - 1

    @valide_inter()
    @menu()
    def move_right_page(self):
        self.page = self.page + 1

    @valide_inter()
    @menu()
    def move_double_right_page(self):
        self.page = min(self.page + 5, self.len_pages - 1)

    @valide_inter()
    async def open_sorter_menu(self):
        await SorterMenu(self).m_menu()

    @valide_inter()
    async def open_filter_menu(self):
        await FilterMenu(self).m_menu()

    @valide_inter()
    async def add_movie(self):
        await AddMovieMenu(self).m_menu()

    @valide_inter()
    async def edit_movie(self):
        genres = await get_genre_movie(self.movies[self.movie_select_in_page].movie_id)
        genres = [genre[1] for genre in genres]
        self.movies[self.movie_select_in_page].genre = genres
        await EditMovieMenu(self, self.movies[self.movie_select_in_page]).m_menu()

    @valide_inter()
    @menu()
    async def delete_movie(self):
        await delete_movie(self.movies[self.movie_select_in_page].movie_id)

    @valide_inter()
    async def edit_config(self):
        await ConfigMenu(self).setup()

    @valide_inter()
    @menu(load_movie=False)
    async def f_validate_btn(self, func):
        self.validate_btn = Button("Valider", ButtonStyle.green, func)

    @valide_inter()
    @menu()
    async def cancel_validation(self):
        self.validate_btn = None

    # /
    async def load_movies(self):
        SQLQuery = get_query("SELECT DISTINCT m.id, m.name, m.duration, m.to_see, m.TMDB_id, m.url FROM movies m", self.filters)
        SQLQuery += f" LIMIT {self.page * self.max_movie_in_page}, {self.max_movie_in_page};"

        self.movies = []
        for movie in await DatabaseManager.execute_query(SQLQuery, fetch=True, logger=self.logger):
            movie = Movie(movie[1], movie[2], [], movie[3], None, movie[0], movie[4], movie[5])
            self.movies.append(movie)


    async def count_pages(self):
        SQLQueryCount = get_query("SELECT COUNT(DISTINCT m.id) FROM movies m", self.filters)
        movies_count = (await DatabaseManager.execute_query(SQLQueryCount, fetch=True, logger=self.logger))[0][0]
        self.len_pages = movies_count // self.max_movie_in_page + bool(movies_count % self.max_movie_in_page)

    @valide_inter()
    async def m_menu(self, load_movie=True):
        if load_movie:
            await self.load_movies()
            self.movie_select_in_page = None
            self.validate_btn = None
        await self.message.resource.edit(embed=self.embed, view=self.view)

        # Log
        movie_title = None
        if self.movie_select_in_page is not None:
            movie_title = self.movies[self.movie_select_in_page].title
        self.logger.log(f"[Main menu] [ID: {self.message.id}] {self.author.name} -> ("
                        f"page: {self.page + 1}/{self.len_pages}; "
                        f"movie_select: {movie_title})")


class SorterMenu:
    def __init__(self, parent):
        self.parent: MainMenu = parent
        self.bot = self.parent.bot
        self.logger = self.parent.logger
        self.message = self.parent.message
        self.filters = deepcopy(self.parent.filters)

        self.sorter_slc = None

    @property
    async def embed(self) -> Embed:
        embed = Embed(title="Trier")

        if self.filters.sorters:
            embed.add_field(name="Trie actuel:",
                            value='\n'.join([f'```{x.name} {('↓', '↑')[x.is_asc]}```' for x in self.filters.sorters]))

        return embed

    @property
    async def view(self) -> View:
        inputs = []

        if not self.sorter_slc:
            # Initalise BTN
            sorters_btn = []
            for btn_id, btn_value in SORTER_VALUES.items():
                sorters_btn.append(Button(btn_value["name"], ButtonStyle.green, partial(self.set_sorter_slc, value=btn_value)))

            btn_cancel = Button("Retour", ButtonStyle.grey, self.parent.m_menu)
            btn_validate = Button("Valider", ButtonStyle.green, self.validate)

            selecteur_delete = Selecteur("Retirer trie", 1, len(self.filters.sorters), [
                SelecteurOption(sorter.name, "", k) for k, sorter in enumerate(self.filters.sorters)
            ], self.remove_sorter)

            # Ajout BTN
            for btn in sorters_btn:
                inputs.append(btn)

            inputs.append(btn_cancel)
            inputs.append(btn_validate)
            if self.filters.sorters:
                inputs.append(selecteur_delete)
        else:
            # Initalise BTN
            btn_croiss = Button("Croissant ", ButtonStyle.green,
                                partial(self.add_sorter, value=self.sorter_slc, is_asc=True),
                                emoji=Emoji.ARROW_UP.value)
            btn_decroiss = Button("Decroissant ", ButtonStyle.green,
                                  partial(self.add_sorter, value=self.sorter_slc, is_asc=False),
                                  emoji=Emoji.ARROW_DOWN.value)
            btn_cancel = Button("Retour", ButtonStyle.grey, self.cancel_add_sorter)

            # Ajout BTN
            inputs.append(btn_croiss)
            inputs.append(btn_decroiss)
            inputs.append(btn_cancel)

        return View(self.parent.author, inputs)

    @valide_inter()
    async def m_menu(self):
        await self.message.resource.edit(embed=await self.embed, view=await self.view)

    # Buttons
    @valide_inter()
    @menu()
    async def cancel_add_sorter(self):
        self.sorter_slc = None

    @valide_inter()
    @menu()
    async def set_sorter_slc(self, value):
        self.sorter_slc = value

    @valide_inter()
    @menu()
    async def add_sorter(self, value, is_asc):
        self.filters.add_sorter(Sorter(self.filters, value["name"], is_asc, "m."+value["id"]))
        self.sorter_slc = None

    @valide_inter()
    @menu()
    async def remove_sorter(self, value):
        if isinstance(value, list):
            for x in [*map(int, value)][::-1]:
                self.filters.remove_sorter(x)
        elif isinstance(value, str):
            self.filters.remove_sorter(int(value))

    @valide_inter()
    async def validate(self):
        self.parent.filters = self.filters
        await self.parent.m_menu()
        del self


class FilterMenu:
    def __init__(self, parent):
        self.parent: MainMenu = parent
        self.bot = self.parent.bot
        self.message = self.parent.message
        self.logger = self.parent.logger

        self.filters = deepcopy(self.parent.filters)
        self.filter_slc = None

        self._genre = None

        self.genres_include = self.filters.genres_include
        self.genres_exclude = self.filters.genres_exclude

    @property
    async def embed(self) -> Embed:
        embed = Embed(title="Filtrer")

        if self.filters.filters:
            embed.add_field(name="Filtres actuel:",
                            value='\n'.join([f'```{x.name}```' for x in self.filters.filters]))
        return embed

    @property
    async def view(self) -> View:
        inputs = []

        if not self.filter_slc:
            filter_btn = []
            for btn_id, btn_value in FILTER_VALUES.items():
                filter_btn.append(Button(btn_value["name"], ButtonStyle.blurple, partial(self.set_filter_slc, value=btn_id)))

            btn_validate = Button("Valider", ButtonStyle.green, self.validate)
            btn_cancel = Button("Annuler", ButtonStyle.grey, self.parent.m_menu)

            selecteur_delete = Selecteur("Retirer Filtre", 1, len(self.filters.filters), [
                SelecteurOption(_filter.name[:100], "", k) for k, _filter in enumerate(self.filters.filters)
            ], self.remove_filter)

            for btn in filter_btn:
                inputs.append(btn)
            inputs.append(btn_validate)
            inputs.append(btn_cancel)
            if self.filters.filters:
                inputs.append(selecteur_delete)

        else:
            btns = []
            if FILTER_VALUES[self.filter_slc]["type"] in (FilterOpt.INT, FilterOpt.DATE):
                for btn in FILTER_VALUES[self.filter_slc]["type"]._member_map_.values():
                    btns.append(Button(btn.value[0], ButtonStyle.blurple,
                                       partial(self.int_open_modal, value=btn, _filter=FILTER_VALUES[self.filter_slc])))

                btn_cancel = Button("Retour", ButtonStyle.grey, self.cancel_filter)

                btns.append(btn_cancel)

            elif FILTER_VALUES[self.filter_slc]["type"] == FilterOpt.Genre:
                genres = await self.genres

                selecteur_include = Selecteur("Genres Inclus", 1, len(genres), [
                    SelecteurOption(f"🔹{genre}🔹" if genre_id in self.genres_include else genre,
                                    "", genre_id) for genre_id, genre in genres.items()], self.set_genres_include)

                selecteur_exclude = Selecteur("Genres Exclus", 1, len(genres), [
                    SelecteurOption(f"🔹{genre}🔹" if genre_id in self.genres_exclude else genre,
                                    "", genre_id) for genre_id, genre in genres.items()], self.set_genres_exclude)

                btn_validate = Button("Valider", ButtonStyle.green, self.set_filter_genres)
                btn_cancel = Button("Retour", ButtonStyle.grey, self.cancel_filter)

                inputs.append(selecteur_include)
                inputs.append(selecteur_exclude)
                inputs.append(btn_validate)
                inputs.append(btn_cancel)

            elif FILTER_VALUES[self.filter_slc]["type"] == FilterOpt.Enum:
                for btn_name, btn_value in FILTER_VALUES[self.filter_slc]["enum"]:
                    btns.append(
                        Button(btn_name, ButtonStyle.blurple, partial(self.set_enum_value, value=btn_value,
                                                                      _filter=FILTER_VALUES[self.filter_slc]))
                    )
                btn_cancel = Button("Retour", ButtonStyle.grey, self.cancel_filter)

                btns.append(btn_cancel)

            for btn in btns:
                inputs.append(btn)

        return View(self.parent.author, inputs)


    @valide_inter()
    async def m_menu(self):
        await self.message.resource.edit(embed=await self.embed, view=await self.view)

    @property
    async def genres(self):
        if not self._genre:
            self._genre = dict(await get_genres())

        return self._genre

    # Buttons
    @valide_inter()
    @menu()
    async def set_filter_slc(self, value):
        self.filter_slc = value

    async def int_open_modal(self, interaction: Interaction, value: FilterOpt.INT, _filter):
        if value == FilterOpt.INT.BETWEEN:
            modal = Modal([
                TextInput("Entre", 1, 3, str.isdigit),
                TextInput("et ", 1, 3, str.isdigit)],
                partial(self.int_get_modal, opt=value, _filter=_filter))
        else:
            modal = Modal([
                TextInput("Valeur",1, 3    , str.isdigit)],
                partial(self.int_get_modal, opt=value, _filter=_filter))
        await interaction.response.send_modal(modal)

    async def date_open_modal(self, interaction: Interaction, value: FilterOpt.INT, _filter):
        if value == FilterOpt.DATE.BETWEEN:
            modal = Modal([
                TextInput("Entre (dd/mm/aaaa)", 10, 10, is_date_format),
                TextInput("et (dd/mm/aaaa)", 10, 10, is_date_format)],
                partial(self.date_get_modal, opt=value, _filter=_filter))
        else:
            modal = Modal([
                TextInput("Valeur (dd/mm/aaaa)",10, 10 , is_date_format)],
                partial(self.date_get_modal, opt=value, _filter=_filter))
        await interaction.response.send_modal(modal)

    @valide_inter()
    @menu()
    async def int_get_modal(self, value, opt: FilterOpt.INT, _filter):
        value = list(value.values())
        if len(value) == 1:
            value = value[0]

        self.filters.add_filter(
            Filter(self.filters,
                   f"{_filter["name"]} {opt.value[0]} {value}",
                   True, False, opt.value[1]("m."+_filter["id"], value))
        )
        self.filter_slc = None

    @valide_inter()
    @menu()
    async def date_get_modal(self, value, opt: FilterOpt.INT, _filter):
        value = list(value.values())
        if len(value) == 1:
            value = value[0]
            value = f"'{datetime.datetime(*map(int, value.split("/")[::-1]))}'"

        self.filters.add_filter(
            Filter(self.filters,
                   f"{_filter["name"]} {opt.value[0]} {value}",
                   True, False, opt.value[1]("m."+_filter["id"], value))
        )
        self.filter_slc = None

    @valide_inter()
    async def validate(self):
        self.parent.filters = self.filters
        self.parent.page = 0
        await self.parent.count_pages()
        await self.parent.m_menu()
        del self

    @valide_inter()
    @menu()
    async def remove_filter(self, value):
        if isinstance(value, list):
            for index in [*map(int, value)][::-1]:
                self.filters.remove_filter(index)
        elif isinstance(value, str):
            self.filters.remove_filter(int(value))

    @valide_inter()
    @menu()
    async def set_genres_include(self, values):
        for i in [*map(int, values)]:
            if i in self.genres_include:
                self.genres_include.remove(i)
            else:
                self.genres_include.append(i)

    @valide_inter()
    @menu()
    async def set_genres_exclude(self, values):
        for i in [*map(int, values)]:
            if i in self.genres_exclude:
                self.genres_exclude.remove(i)
            else:
                self.genres_exclude.append(i)

    @valide_inter()
    @menu()
    async def set_filter_genres(self):
        if self.genres_include:
            self.filters.genres_include = copy(self.genres_include)
        if self.genres_exclude:
            self.filters.genres_exclude = copy(self.genres_exclude)

        self.filter_slc = None
        self.genres_include = self.filters.genres_include
        self.genres_exclude = self.filters.genres_exclude

    @valide_inter()
    @menu()
    async def cancel_filter(self):
        self.filter_slc = None
        self.genres_include = self.filters.genres_include
        self.genres_exclude = self.filters.genres_exclude

    @valide_inter()
    @menu()
    async def set_enum_value(self, value, _filter):
        self.filters.add_filter(
            Filter(self.filters, f"{dict(map(lambda x: x[::-1], _filter['enum']))[value]}", True, False,
                   FilterOpt.Enum.EQUAL.value[1](_filter["id"], value))
        )
        self.filter_slc = None


class AddMovieMenu:
    def __init__(self, parent):
        self.parent: MainMenu = parent

        self.bot = self.parent.bot
        self.logger = self.parent.logger
        self.message = self.parent.message

        self.title = "Ajouter un nouveau film"

        self.movie = Movie(author=self.parent.author, genre=[])

    async def view(self) -> View:
        genres = await get_genres()

        genre_to_add = dict(filter(lambda x: x[0] not in self.movie.genre, genres))
        genre_to_remove = dict(filter(lambda x: x[0] in self.movie.genre, genres))

        add_genre = None
        remove_genre = None

        inputs = []
        search_movie = Button("Chercher 🔍", ButtonStyle.green, self.search)
        edit = Button("📝", ButtonStyle.green, self.edit_open_modal)
        validate = Button("Valider", ButtonStyle.green, self.validate if self.movie.is_ready() else None)
        back = Button("Retour", ButtonStyle.grey, self.parent.m_menu)
        if genre_to_add:
            add_genre = Selecteur("Ajouter genres", 1, len(genre_to_add), [
                SelecteurOption(x[1], "", x[0]) for x in genre_to_add.items()
            ], self.add_genres)
        if genre_to_remove:
            remove_genre = Selecteur("Retirer genres", 1, len(genre_to_remove), [
                SelecteurOption(x[1], "", x[0]) for x in genre_to_remove.items()
            ], self.remove_genres)

        inputs.append(search_movie)
        inputs.append(edit)
        inputs.append(validate)
        inputs.append(back)
        if add_genre:
            inputs.append(add_genre)
        if remove_genre:
            inputs.append(remove_genre)
        return View(self.parent.author, inputs)

    async def embed(self) -> Embed:
        genres = dict(await get_genres())
        embed = Embed(title=self.title)
        embed.add_field(name=".", value=
        f"```Titre: ```\n"
        f"```Duré: ```\n"
        f"```A voir: ```\n"
        f"```Url: ```\n"
        f"```Genres: ```")
        embed.add_field(name="Film", value=
        f"```{self.movie.title or ' ? '}```\n"
        f"```{str_hour(self.movie.duration) if self.movie.duration else ' ? '}```\n"
        f"```{("Non", "Oui")[self.movie.to_see] if self.movie.to_see is not None else ' ? '}```\n"
        f"```{self.movie.url if self.movie.url is not None else ' ? '}```\n"
        f"```{', '.join([genres[x] for x in self.movie.genre]) if self.movie.genre else ' / '}```")
        return embed

    @valide_inter()
    async def m_menu(self):
        await self.message.resource.edit(embed=await self.embed(), view=await self.view())

    # Buttons

    async def edit_open_modal(self, interaction: Interaction):
        modal = Modal([
            TextInput("Titre", 1, 64, None, self.movie.title),
            TextInput("Durée", 1, 3, check=str.isdigit, default=self.movie.duration),
            TextInput("A voir (o/n)", 1, 1, lambda x: x in "on",
                      "no"[self.movie.to_see] if self.movie.to_see is not None else None),
            TextInput("Url", 0, 255, default=self.movie.url, required=False),
        ], self.edit_callback_modal)
        await interaction.response.send_modal(modal)

    @menu()
    @valide_inter()
    async def edit_callback_modal(self, values):
        self.movie.title = values["Titre"] or self.movie.title
        self.movie.duration = int(values["Durée"]) if values["Durée"] else self.movie.duration
        self.movie.to_see = values["A voir (o/n)"]=='o' if values["A voir (o/n)"] is not None else self.movie.to_see
        self.movie.url = values["Url"] or self.movie.url

    @menu()
    @valide_inter()
    async def add_genres(self, values):
        if isinstance(values, list):
            self.movie.genre += [*map(int, values)]
        elif isinstance(values, str) or isinstance(values, str):
            self.movie.genre.append(int(values))

    @menu()
    @valide_inter()
    async def remove_genres(self, values):
        if isinstance(values, list):
            for x in [*map(int, values)]:
                self.movie.genre.remove(x)
        elif isinstance(values, str) or isinstance(values, str):
            self.movie.genre.remove(int(values))

    async def search_open_modal(self, interaction: Interaction):
        modal = Modal([TextInput("Titre", 1, 64)], self.search_callback_modal)
        await interaction.response.send_modal(modal)

    @valide_inter()
    async def search_callback_modal(self, value):
        await SearchMovieMenu(self, value["Titre"]).m_menu()

    @valide_inter()
    async def validate(self):
        await add_movie(self.movie)
        await self.parent.setup()

    async def search(self, interaction: Interaction):
        if not self.movie.tmdb_id and not self.movie.title:
            await self.search_open_modal(interaction)
            return
        elif not self.movie.tmdb_id:
            query = self.movie.title
            await DetailMovieMenu(self, query).m_menu(interaction)
        else:
            await DetailMovieMenu(self).m_menu(interaction)


class SearchMovieMenu:
    def __init__(self, parent, query):
        self.parent: AddMovieMenu = parent

        self.bot = self.parent.bot
        self.logger = self.parent.logger
        self.message = self.parent.message

        self.query = query
        self.movies = get_movies(self.query, os.getenv("APKEY"))

        self.movie_slc = None

    @property
    def embed(self) -> Embed:
        title = "Rechercher un film"
        if self.movie_slc:
            title = self.movie_slc[0]
        embed = Embed(title=title)
        if self.movie_slc:
            embed.set_image(url=f"https://image.tmdb.org/t/p/w500{self.movie_slc[4]}")
            embed.add_field(name="Description:", value=f"{self.movie_slc[5]}")
            if self.movie_slc[6]:
                embed.add_field(name="Productions", value=", ".join([*map(lambda x: x["name"], self.movie_slc[6])]),
                                inline=False)
            embed.set_footer(text=f"{self.movie_slc[3]}")
        elif not self.movies:
            embed.add_field(name="Aucun film trouvé", value="aucun films n'a était trouvé correspondant a votre recherche")
        return embed

    @property
    def view(self) -> View:
        inputs = []
        movies = None
        validate = None

        if self.movies:
            movies = Selecteur("Films", 1, 1, [
                SelecteurOption(x[0][:100], x[1], k) for k, x in enumerate(self.movies)
            ], self.set_movie_slc)
        search_movie = Button("rechercher 🔍", ButtonStyle.green, self.search_open_modal)
        if self.movie_slc:
            validate = Button("Valider", ButtonStyle.green, self.validate_movie_slc)
        back = Button("Retour", ButtonStyle.grey, self.parent.m_menu)

        if movies:
            inputs.append(movies)
        inputs.append(search_movie)
        if validate:
            inputs.append(validate)
        inputs.append(back)
        return View(self.parent.parent.author, inputs)

    @valide_inter()
    async def m_menu(self):
        await self.message.resource.edit(embed=self.embed, view=self.view)

    # Buttons

    @menu()
    @valide_inter()
    async def set_movie_slc(self, value):
        self.movie_slc = get_detail(self.movies[int(value)][2], os.getenv("APKEY"))

    async def search_open_modal(self, interaction: Interaction):
        modal = Modal([TextInput("Titre", 1, 64)], self.search_callback_modal)
        await interaction.response.send_modal(modal)

    @valide_inter()
    async def search_callback_modal(self, value):
        self.__init__(self.parent, value["Titre"])
        await self.m_menu()

    @valide_inter()
    async def validate_movie_slc(self):
        self.parent.movie.title = self.movie_slc[0]
        self.parent.movie.duration = self.movie_slc[1]
        self.parent.movie.tmdb_id = self.movie_slc[7]
        await self.parent.m_menu()


class EditMovieMenu(AddMovieMenu):
    def __init__(self, parent, movie):
        super().__init__(parent)
        self.view_btns = []
        self.title = "Modifier le Film"
        self.movie = movie

    @valide_inter()
    async def validate(self):
        await edit_movie(self.movie)
        await self.parent.setup()


class ConfigMenu:
    def __init__(self, parent):
        self.parent: MainMenu = parent

        self.bot = self.parent.bot
        self.logger = self.parent.logger
        self.message = self.parent.message
        self.author = self.parent.author

        self.config = [None, ]
        self.default_config = [None, ]

    async def setup(self):
        self.default_config, self.config = await get_config(((await get_authors())[self.author.name], USER_ID_DEFAULT))
        self.default_config, self.config = list(self.default_config), list(self.config)
        await self.m_menu()

    @property
    async def view(self):
        inputs = []

        edit = Button("📝", ButtonStyle.green, self.edit_open_modal)
        back = Button("Retour", ButtonStyle.grey, self.parent.m_menu)
        validate = Button("Valider", ButtonStyle.green, self.validate)

        inputs.append(edit)
        inputs.append(back)
        inputs.append(validate)

        return View(self.author, inputs)

    @property
    async def embed(self):
        embed = Embed(title="Configuration")
        embed.add_field(name="", value="``` Film affiché par page: ```")
        embed.add_field(name="", value=f"``` {self.config[0] if self.config else f"Default ({self.default_config[0]})"} ```")
        return embed

    @valide_inter()
    async def m_menu(self):
        await self.message.resource.edit(embed=await self.embed, view=await self.view)

    # Buttons
    async def edit_open_modal(self, interaction: Interaction):
        modal = Modal([TextInput("Nombre de film affiché par page (1-25)", 0, 2,
                                 lambda x: (x.isdigit() and 0 < int(x) < 26) or x=="",
                                 self.config[0] if self.config else self.default_config[0])], self.edit_callback_modal)
        await interaction.response.send_modal(modal)

    @valide_inter()
    @menu()
    async def edit_callback_modal(self, values):
        max_movie_in_page = values["Nombre de film affiché par page (1-25)"]
        self.config[0] = max_movie_in_page

    @valide_inter()
    async def validate(self):
        await edit_config(self.config, (await get_authors())[self.author.name])
        await self.parent.setup()


class DetailMovieMenu(SearchMovieMenu):
    def __init__(self, parent, query=""):
        super().__init__(parent, query)
        self.parent: AddMovieMenu | EditMovieMenu = parent
        if self.parent.movie.tmdb_id:
            self.movie_slc = get_detail(self.parent.movie.tmdb_id, os.getenv("APKEY"))
            self.movies = [self.movie_slc]

    @valide_inter()
    async def search_callback_modal(self, value):
        super().__init__(self.parent, value["Titre"])
        await self.m_menu()


async def setup(bot):
    await bot.add_cog(Movies(bot, bot.logger))
