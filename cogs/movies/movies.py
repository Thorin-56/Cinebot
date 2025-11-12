import json
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

async def add_genre(name, author):
    await DatabaseManager.execute_query("INSERT INTO genres (name, created_by)"
                                        "VALUES (%s, %s)", (name, author))

async def delete_genres(ids):
    if isinstance(ids, list):
        query = f"DELETE FROM genres WHERE id in {tuple(ids)}"
    else:
        query = f"DELETE FROM genres WHERE id={ids}"
    await DatabaseManager.execute_query(query)

async def edit_genre(_id, value):
    query = f"UPDATE genres SET name=%s WHERE id=%s"
    await DatabaseManager.execute_query(query, (value, _id))

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
    query = f"SELECT c.max_movie_in_page, c.filters FROM config c WHERE c.user_id IN {user_id}"
    config =  await DatabaseManager.execute_query(query, fetch=True)
    if not config:
        query = (f"INSERT INTO config (user_id, max_movie_in_page) "
                 f"VALUES ({user_id}, %s)")
        default_config = (await get_config(USER_ID_DEFAULT))[0]
        _, last_id = await DatabaseManager.execute_query(query, default_config)
        return [default_config]
    return config

async def edit_config(config, user_id):
    query = f"UPDATE config SET max_movie_in_page=%s, filters=%s WHERE user_id={user_id}"
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
    FILTRE = discord.PartialEmoji(name="filter", id=1436425969346019469)
    ARROW_UP = discord.PartialEmoji(name="arrow_up", id=1436080735499976836)
    ADD = discord.PartialEmoji(name="add", id=1436071687451050165)
    ARROW_DOWN = discord.PartialEmoji(name="arrow_down", id=1436080125941907528)
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

        #Menu
        self.menu_p = 0

        # Config
        self.max_movie_in_page: int = 0

        # Pages
        self.page: int = 0
        self.len_pages: int | None = None

        # Movie selectionne
        self.movie_select_in_page: int | None = None
        self.movies: None | list[Movie] = None
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
        self.max_movie_in_page = default_config[0]
        if config:
            if config[0] is not None:
                self.max_movie_in_page = config[0]
            if config[1]:
                data: dict = json.loads(config[1])
                self.filters.genres_include = data["genres_includes"]
                self.filters.genres_exclude = data["genres_excludes"]
                for x in data["others_filters"]:
                    self.filters.add_filter(
                        Filter(self.filters, x["name"], x["is_and"], x["is_not"], x["cdt"])
                    )
                for x in data["sorters"]:
                    self.filters.add_sorter(
                        Sorter(self.filters, x["name"], x["is_asc"], x["value"])
                    )

        self.genres = dict(await get_genres())
        self.filters.genres = self.genres

        self.page = 0
        await self.count_pages()
        await self.m_menu(load_movie=True)

    @property
    def view(self) -> View:
        menu_pages = [self.view_p1, self.view_p2]
        return menu_pages[self.menu_p]

    @property
    def view_p1(self) -> View:
        inputs = []

        btn_arrow_left5 = Button("⏪", ButtonStyle.blurple, (None, self.move_double_left_page)[self.page > 0])
        btn_arrow_left = Button("◀️", ButtonStyle.blurple, (None, self.move_left_page)[self.page > 0])
        btn_arrow_right = Button("▶️", ButtonStyle.blurple, (None, self.move_right_page)[self.page < self.len_pages - 1])
        btn_arrow_right5 = Button("⏩", ButtonStyle.blurple, (None, self.move_double_right_page)[self.page < self.len_pages - 1])
        btn_settings = Button("", ButtonStyle.grey, partial(self.set_menu_p, page=1), emoji=Emoji.SETTINGS.value)

        slc_select_movie_title = self.movies[self.movie_select_in_page].title \
            if self.movie_select_in_page is not None else "Selecionner un film"
        slc_select_movie_2 = Selecteur(slc_select_movie_title, 1, 1, [
                SelecteurOption(f"{"🔷" if k == self.movie_select_in_page else ""} {movie.title}", "", k)
                for k, movie in enumerate(self.movies)], self.select_movie)

        btn_edit = Button("📝", ButtonStyle.green, self.edit_movie)
        btn_delete = Button("🗑️", ButtonStyle.red, self.delete_movie)
        url = self.movies[self.movie_select_in_page].url if self.movie_select_in_page else None
        btn_view = Button("👁️", ButtonStyle.green, None, url=url)
        btn_back = Button("Retour", ButtonStyle.green, self.deselect_movie)

        # Ajout des boutons
        if self.movie_select_in_page is None:
            # Ligne 1
            inputs.append(btn_arrow_left5)
            inputs.append(btn_arrow_left)
            inputs.append(btn_arrow_right)
            inputs.append(btn_arrow_right5)
            inputs.append(btn_settings)
            # Ligne 2
            inputs.append(slc_select_movie_2)
        else:
            # Ligne 1
            inputs.append(btn_edit)
            inputs.append(btn_delete)
            inputs.append(btn_view)
            inputs.append(NONE_BTN)
            inputs.append(btn_back)

        return View(self.author, inputs, None)

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

    # Arrows
    @valide_inter()
    @menu(load_movie=True)
    def move_double_left_page(self):
        self.page = max(self.page - 5, 0)

    @valide_inter()
    @menu(load_movie=True)
    def move_left_page(self):
        self.page = self.page - 1

    @valide_inter()
    @menu(load_movie=True)
    def move_right_page(self):
        self.page = self.page + 1

    @valide_inter()
    @menu(load_movie=True)
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
    async def manage_genre(self):
        await ManageGenreMenu(self).m_menu()

    @valide_inter()
    async def edit_config(self):
        await ConfigMenu(self).setup()

    @valide_inter()
    async def edit_movie(self):
        genres = await get_genre_movie(self.movies[self.movie_select_in_page].movie_id)
        genres = [genre[1] for genre in genres]
        self.movies[self.movie_select_in_page].genre = genres
        await EditMovieMenu(self, self.movies[self.movie_select_in_page]).m_menu()

    @valide_act()
    @valide_inter()
    @menu(load_movie=True)
    async def delete_movie(self):
        await delete_movie(self.movies[self.movie_select_in_page].movie_id)

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
    async def m_menu(self, load_movie=False):
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

    @valide_inter()
    @menu()
    async def deselect_movie(self):
        self.movie_select_in_page = None

    @property
    def view_p2(self) -> View:
        inputs = []

        btn_add_movie = Button("➕ Film", ButtonStyle.grey, self.add_movie)
        btn_config = Button("⚙️", ButtonStyle.grey, self.edit_config)
        btn_sorter = Button("Trier", ButtonStyle.blurple, self.open_sorter_menu, emoji=Emoji.ARROW_UP.value)
        btn_filter = Button("Filtrer", ButtonStyle.blurple, self.open_filter_menu, emoji=Emoji.FILTRE.value)
        btn_validate = Button("Valider", ButtonStyle.green, partial(self.set_menu_p, page=0))

        btn_clear = Button("Supprimer les Filtres/Tries", ButtonStyle.red, self.clear_filters_sorters)
        btn_add_genre = Button("🔧Genre", ButtonStyle.grey, self.manage_genre)

        # Ligne 1
        inputs.append(btn_sorter)
        inputs.append(btn_filter)
        inputs.append(btn_add_movie)
        inputs.append(btn_config)
        inputs.append(btn_validate)
        # Ligne 2
        inputs.append(btn_clear)
        inputs.append(btn_add_genre)
        inputs.append(NONE_BTN)
        inputs.append(NONE_BTN)
        inputs.append(NONE_BTN)

        return View(self.author, inputs)

    @valide_inter()
    @menu()
    async def set_menu_p(self, page):
        self.menu_p = page

    @valide_inter()
    @menu(load_movie=True)
    async def clear_filters_sorters(self):
        self.filters.clear()


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
                sorters_btn.append(Button(btn_value["name"], ButtonStyle.blurple, partial(self.set_sorter_slc, value=btn_value)))

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
        await self.parent.load_movies()
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
            _type = FILTER_VALUES[self.filter_slc]["type"]
            if _type in (FilterOpt.INT, FilterOpt.DATE):
                for btn in _type._member_map_.values():
                    btns.append(Button(btn.value[0], ButtonStyle.blurple,
                                       partial((self.int_open_modal, self.date_open_modal)[_type ==  FilterOpt.DATE],
                                               value=btn, _filter=FILTER_VALUES[self.filter_slc])))

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
                TextInput("Entre", 1, 3, "value1", str.isdigit),
                TextInput("et ", 1, 3, "value2", str.isdigit)],
                partial(self.int_get_modal, opt=value, _filter=_filter))
        else:
            modal = Modal([
                TextInput("Valeur",1, 3 , "value", str.isdigit)],
                partial(self.int_get_modal, opt=value, _filter=_filter))
        await interaction.response.send_modal(modal)

    async def date_open_modal(self, interaction: Interaction, value: FilterOpt.INT, _filter):
        if value == FilterOpt.DATE.BETWEEN:
            modal = Modal([
                TextInput("Entre (dd/mm/aaaa)", 10, 10, "value", is_date_format),
                TextInput("et (dd/mm/aaaa)", 10, 10, "value2", is_date_format)],
                partial(self.date_get_modal, opt=value, _filter=_filter))
        else:
            modal = Modal([
                TextInput("Valeur (dd/mm/aaaa)",10, 10, "value", is_date_format)],
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
            value = datetime.datetime(*map(int, value.split("/")[::-1]))

        self.filters.add_filter(
            Filter(self.filters,
                   f"{_filter["name"]} {opt.value[0]} {value}",
                   True, False, opt.value[1]("m."+_filter["id"], value))
        )
        self.filter_slc = None

    @valide_inter()
    async def validate(self):
        self.parent.filters = self.filters
        self.parent.parent.page = 0
        await self.parent.count_pages()
        await self.parent.load_movies()
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

        add_genres = None
        remove_genre = None

        inputs = []
        search_movie = Button("Chercher 🔍", ButtonStyle.green, self.search)
        edit = Button("📝", ButtonStyle.green, self.edit_open_modal)
        validate = Button("Valider", ButtonStyle.green, self.validate if self.movie.is_ready() else None)
        back = Button("Retour", ButtonStyle.grey, self.parent.m_menu)
        if genre_to_add:
            add_genres = Selecteur("Ajouter genres", 1, len(genre_to_add), [
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
        if add_genres:
            inputs.append(add_genres)
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
            TextInput("Titre", 1, 64, "title", None, self.movie.title),
            TextInput("Durée", 1, 3, "duration", check=str.isdigit, default=self.movie.duration),
            TextInput("A voir (o/n)", 1, 1, "to_see", lambda x: x in "on",
                      "no"[self.movie.to_see] if self.movie.to_see is not None else None),
            TextInput("Url", 0, 255, "url", default=self.movie.url, required=False),
        ], self.edit_callback_modal)
        await interaction.response.send_modal(modal)

    @menu()
    @valide_inter()
    async def edit_callback_modal(self, values):
        self.movie.title = values["title"] or self.movie.title
        self.movie.duration = int(values["duration"]) if values["duration"] else self.movie.duration
        self.movie.to_see = values["to_see"]=='o' if values["to_see"] is not None else self.movie.to_see
        self.movie.url = values["url"] or self.movie.url

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
        modal = Modal([TextInput("Titre", 1, 64, "title")], self.search_callback_modal)
        await interaction.response.send_modal(modal)

    @valide_inter()
    async def search_callback_modal(self, value):
        await SearchMovieMenu(self, value["title"]).m_menu()

    @valide_inter()
    async def validate(self):
        await add_movie(self.movie)
        await self.parent.count_pages()
        await self.parent.m_menu()

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
        modal = Modal([TextInput("Titre", 1, 64, "title")], self.search_callback_modal)
        await interaction.response.send_modal(modal)

    @valide_inter()
    async def search_callback_modal(self, value):
        self.__init__(self.parent, value["title"])
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

    @valide_act()
    @valide_inter()
    async def validate(self):
        await edit_movie(self.movie)
        await self.parent.m_menu()


class ConfigMenu:
    def __init__(self, parent):
        self.parent: MainMenu = parent

        self.bot = self.parent.bot
        self.logger = self.parent.logger
        self.message = self.parent.message
        self.author = self.parent.author

        self.config: list = [None, None, ]
        self.default_config = [None, None, ]

    async def setup(self):
        self.default_config, self.config = await get_config(((await get_authors())[self.author.name], USER_ID_DEFAULT))
        self.default_config, self.config = list(self.default_config), list(self.config)
        await self.m_menu()

    @property
    async def view(self):
        inputs = []

        edit = Button("📝", ButtonStyle.green, self.edit_open_modal)
        test = Button("test", ButtonStyle.green, self.save_filter)
        back = Button("Retour", ButtonStyle.grey, self.parent.m_menu)
        validate = Button("Valider", ButtonStyle.green, self.validate)

        inputs.append(edit)
        inputs.append(test)
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
                                 "nbr_movie", lambda x: (x.isdigit() and 0 < int(x) < 26) or x=="",
                                 self.config[0] if self.config else self.default_config[0])], self.edit_callback_modal)
        await interaction.response.send_modal(modal)

    @valide_inter()
    @menu()
    async def edit_callback_modal(self, values):
        max_movie_in_page = values["nbr_movie"]
        self.config[0] = max_movie_in_page

    @valide_inter()
    async def validate(self):
        await edit_config(self.config, (await get_authors())[self.author.name])
        await self.parent.setup()
        await self.parent.m_menu()

    @valide_inter()
    @menu()
    async def save_filter(self):
        config_filter = {"genres_excludes": self.parent.filters.genres_exclude,
                         "genres_includes": self.parent.filters.genres_include,
                         "others_filters": [{"name": f.name,
                                             "is_and": f.is_and,
                                             "is_not": f.is_not,
                                             "cdt": f.get_cdt} for f in self.parent.filters.get_filter_],
                         "sorters": [{"name": s.name,
                                      "value": s.value,
                                      "is_asc": s.is_asc} for s in self.parent.filters.sorters]}
        self.config[1] = json.dumps(config_filter)
        await edit_config(self.config, (await get_authors())[self.author.name])


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


class ManageGenreMenu:
    def __init__(self, parent):
        self.parent: MainMenu = parent
        self.message = self.parent.message
        self.logger = self.parent.logger
        self.bot = self.parent.bot
        self.author = self.parent.author

        self.genres = []
        self.genre_slc = None

    @property
    async def view(self) -> View:
        inputs = []

        btn_add = Button("➕ genre", ButtonStyle.green, self.add_genre_open_modal)
        btn_valider = Button("Valider", ButtonStyle.green, self.parent.m_menu)
        selecteur = Selecteur("selectionez genre", 1, len(self.genres), [
            SelecteurOption(genre[1], "", genre[0]) for genre in self.genres
        ], self.set_genre_slc)

        btn_delete = Button("Supprimer", ButtonStyle.red, self.delete_genre)
        btn_edit = Button("📝", ButtonStyle.blurple, self.edit_genre_open_modal)
        btn_back = Button("Retour", ButtonStyle.grey, self.unslc_genre_slc)

        if not self.genre_slc:
            # Ligne 1
            inputs.append(btn_add)
            inputs.append(btn_valider)
            inputs.append(NONE_BTN)
            inputs.append(NONE_BTN)
            inputs.append(NONE_BTN)
            # Ligne 2
            inputs.append(selecteur)
        else:
            inputs.append(btn_delete)
            if isinstance(self.genre_slc, int):
                inputs.append(btn_edit)
            else:
                inputs.append(NONE_BTN)
            inputs.append(btn_back)
            inputs.append(NONE_BTN)
            inputs.append(NONE_BTN)

        return View(self.author, inputs)

    @property
    async def embed(self) -> Embed:
        embed = Embed(title="Gérer les genres")
        nbr = 10
        display_genres = [self.genres[x:min(x+nbr, len(self.genres))] for x, _ in list(enumerate(self.genres))[::nbr]]
        print(display_genres)
        for genres in display_genres:
            embed.add_field(name="Genres:", value="\n".join([f"```{genre_name}```" for genre_id, genre_name in genres]))

        return embed

    @valide_inter()
    async def m_menu(self):
        if not self.genres:
            await self.load_genres()
        await self.message.resource.edit(embed=await self.embed, view=await self.view)

    @valide_inter()
    async def load_genres(self):
        self.genres = await get_genres()

    @valide_inter()
    @menu()
    async def set_genre_slc(self, value):
        if len(value) == 1:
            self.genre_slc = int(value[0])
        else:
            self.genre_slc = [*map(int, value)]

    async def add_genre_open_modal(self, interraction: Interaction):
        modal = Modal([TextInput("Nom du genre", 1, 32, "genre")], self.add_genre_get_modal)
        await interraction.response.send_modal(modal)

    @valide_inter()
    @menu()
    async def add_genre_get_modal(self, value):
        value = value["genre"]
        await add_genre(value, (await get_authors())[self.author.name])
        await self.load_genres()

    @valide_act()
    @valide_inter()
    @menu()
    async def delete_genre(self):
        await delete_genres(self.genre_slc)
        self.genre_slc = None
        await self.load_genres()

    @valide_inter()
    @menu()
    async def unslc_genre_slc(self):
        self.genre_slc = None

    async def edit_genre_open_modal(self, interraction: Interaction):
        modal = Modal([
            TextInput("Genre", 1, 32, "genre", default=dict(self.genres)[self.genre_slc])
        ], self.edit_genre_get_modal)
        await interraction.response.send_modal(modal)

    @valide_inter()
    @menu()
    async def edit_genre_get_modal(self, value):
        value = value["genre"]
        await edit_genre(self.genre_slc, value)
        self.genre_slc = None
        await self.load_genres()


async def setup(bot):
    await bot.add_cog(Movies(bot, bot.logger))
