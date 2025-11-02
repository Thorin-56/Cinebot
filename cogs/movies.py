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

# Constante
USER_ID_DEFAULT = 0

# Enum
class Emoji(Enum):
    SEP = discord.PartialEmoji(name="sep", id=1419289057187594342)
    FILTRE = discord.PartialEmoji(name="filtre", id=1419367029852344330)
    ARROW_UP = discord.PartialEmoji(name="arrow_up", id=1419367009510232064)
    ADD = discord.PartialEmoji(name="add", id=1419366985191526481)
    ARROW_DOWN = discord.PartialEmoji(name="arrow_down", id=1419397467425869835)


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
            Button("🗑️", ButtonStyle.red, self.delete_movie),
            Button("📝", ButtonStyle.green, self.edit_movie),
            Button("👁️", ButtonStyle.green, None),
        ]
        self.movie_select_action = 0

        self.filters = Filters()

    def cleanup(self):
        del self

    @valide_inter()
    async def setup(self):
        default_config, config = (await get_config(((await get_authors())[self.author.name], USER_ID_DEFAULT)))
        self.max_movie_in_page = config[0] if config and config[0] else default_config[0]

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

        btn_filter = [Button("", ButtonStyle.green, self.filter, Emoji.FILTRE.value)]

        btn_action = [
            Button("⬅️", ButtonStyle.green, partial(self.switch_action, _dir=-1)),
            copy(self.btn_actions[self.movie_select_action]),
            Button("➡️", ButtonStyle.green, partial(self.switch_action, _dir=1)),
        ]

        btn_add_movie = [Button("➕", ButtonStyle.grey, self.add_movie)]
        btn_config = [Button("⚙️", ButtonStyle.grey, self.edit_config)]

        if self.movie_select_in_page is None:
            btn_action[1].reset_fct()
        if self.movie_select_action in (2, -1) and self.movie_select_in_page is not None and self.movies[self.movie_select_in_page].url:
            btn_action[1].url = self.movies[self.movie_select_in_page].url
        if self.movies:
            btn = btn_arrow + btn_filter + slc_select_movie_2 + btn_action + btn_add_movie + btn_config
        else:
            btn = btn_filter

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
    async def filter(self):
        await FilterMenu(self).setup()

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
        await self.message.resource.edit(embed=self.embed, view=self.view)

        # Log
        movie_title = None
        if self.movie_select_in_page is not None:
            movie_title = self.movies[self.movie_select_in_page].title
        self.logger.log(f"[Main menu] [ID: {self.message.id}] {self.author.name} -> ("
                        f"page: {self.page + 1}/{self.len_pages}; "
                        f"movie_select: {movie_title})")


class FilterMenu:
    def __init__(self, parent: MainMenu):
        self.parent: MainMenu = parent
        self.bot = self.parent.bot
        self.logger = self.parent.logger
        self.message = self.parent.message

        self.filters: Filters = self.parent.filters

        # menu view
        self.slc_menu = None

        # Selecteur
        self.filter_opt_slc = None
        self.filter_opt = {}

        # Bouton Trie
        self.sorter_dir = 'ASC'

        # Bouton Filtre
        self.filter_op = "AND"
        self.filter_not = ""
        self.filter_opt_ = None
        self.filter_value = None

        # Switch Buttons
        self.mem_SwBtn = {}

    async def _set_filter_opt(self):
        self.filter_opt = {
            "duration": {"name": "Durée",
                         "used": "sf",
                         "type": FilterOpt.INT},
            "name": {"name": "Titre",
                     "used": "sf",
                     "type": FilterOpt.STR},
            "created_by": {"name": "Auteur",
                           "used": "sf",
                           "type": FilterOpt.Enum,
                           "values": await get_authors()},
            "to_see": {"name": "à Voir",
                       "used": "sf",
                       "type": FilterOpt.Enum,
                       "values": {"Oui": 1,
                                  "Non": 0}},
            "genres": {"name": "Genre",
                       "used": "f",
                       "type": FilterOpt.Genre}
        }

    async def setup(self):
        await self._set_filter_opt()
        await self.m_menu()

    @property
    def embed(self) -> Embed:
        embed = Embed(title="Options de Filtre")
        embed.add_field(name="Tries:", value=f"```{'\n'.join([x.name for x in self.filters.sorters]).strip() or '/'}```")
        embed.add_field(name="Filtres:", value=f"```{'\n'.join([x.name for x in self.filters.filters]).strip() or '/'}```")
        return embed

    @property
    async def view(self) -> View:
        return await self.main_view()

    def filter_slc(self, key: str):
        if self.filter_opt_slc is None:
            return None
        elif self.filter_opt[self.filter_opt_slc] is None:
            return None
        elif key:
            return self.filter_opt[self.filter_opt_slc].get(key)
        else:
            return self.filter_opt[self.filter_opt_slc]

    async def main_view(self) -> View:
        inputs = []
        # Selecteur de l'option
        slc_title = self.filter_slc("name") or "Filtre: "
        inputs.append(
            Selecteur(slc_title, 1, 1,
                      [SelecteurOption(opt["name"], "", key) for key, opt in self.filter_opt.items()],
                      self.set_filter_opt_slc)
        )

        # Delete
        if self.filters:
            opt = [SelecteurOption(f"🔷{opt.name}", "", f"f{k}") for k, opt in enumerate(self.filters.filters)] + [
                SelecteurOption(f"🟩{opt.name}", "", f"s{k}") for k, opt in enumerate(self.filters.sorters)]
            inputs.append(
                Selecteur("Delete", 1, len(self.filters.filters) + len(self.filters.sorters), opt, self.delete)
            )

        # Bouton Trie
        inputs.append(
            Button("Trie", ButtonStyle.green,
                   (self.set_sorter if "s" in self.filter_slc("used") else None) if self.filter_slc("name") else None,
                   emoji=Emoji.ADD.value)
        )

        # Bouton Filtre
        inputs.append(
            Button("Filtre", ButtonStyle.blurple,
                   (self.set_filter if "f" in self.filter_slc("used") else None) if self.filter_slc("name") else None,
                   emoji=Emoji.ADD.value)
        )

        # Valider
        inputs.append(
            Button("Valider", ButtonStyle.green, self.valide)
        )

        # None Button
        inputs.append(Button("/", ButtonStyle.grey, None))
        inputs.append(Button("/", ButtonStyle.grey, None))

        # Options trie
        if self.slc_menu == 1:
            inputs.append(Button("", ButtonStyle.green, self.switch_sorter_dir,
                                 emoji=(Emoji.ARROW_UP, Emoji.ARROW_DOWN)[self.sorter_dir == "DESC"].value))
            inputs.append(Button("Ajouter", ButtonStyle.green, self.add_sorter))

        # Options filtre
        if self.slc_menu == 0:
            if self.filters.filters:
                inputs.append(Button(self.filter_op.lower(), ButtonStyle.blurple, self.switch_filter_op))
            inputs.append(Button(f"if {self.filter_not}".lower(), ButtonStyle.blurple, self.switch_filter_not))

            if self.filter_slc("type") == FilterOpt.INT:
                inputs.append(self.mem_SwBtn.get(self.filter_opt_slc) or
                              self.mem_SwBtn.update({self.filter_opt_slc: self.sw_btn_int()}) or
                              self.mem_SwBtn.get(self.filter_opt_slc))
                inputs.append(Button(self.filter_value or "?", ButtonStyle.blurple, self.open_filter_value_int))
            elif self.filter_slc("type") == FilterOpt.Enum:
                inputs.append(self.mem_SwBtn.get(self.filter_opt_slc) or
                              self.mem_SwBtn.update({self.filter_opt_slc: self.sw_btn_bool()}) or
                              self.mem_SwBtn.get(self.filter_opt_slc))


            elif self.filter_slc("type") == FilterOpt.STR:
                inputs.append(Button(self.filter_value or "?", ButtonStyle.blurple, self.open_filter_value_str))
            elif self.filter_slc("type") == FilterOpt.Genre:
                inputs.append(self.mem_SwBtn.get(self.filter_opt_slc) or
                              self.mem_SwBtn.update({self.filter_opt_slc: self.sw_btn_genre()}) or
                              self.mem_SwBtn.get(self.filter_opt_slc))
                genres = await get_genres()
                if genres:
                    inputs.append(
                        Selecteur("Genres:", 1, len(genres), [
                            SelecteurOption(genre[1], "", genre[0]) for genre in genres
                        ], self.set_filter_value)
                    )

            inputs.append(Button("Ajouter", ButtonStyle.blurple, self.add_filter if self.filter_value
                                                                                    is not None else None))

        return View(self.parent.author, inputs, None)

    # Switch Btn
    def sw_btn_int(self) -> SwitchButton:
        return SwitchButton([
                    Button("<", ButtonStyle.blurple, partial(self.set_filter_opt, value=FilterOpt.INT.INFERIOR)),
                    Button("=", ButtonStyle.blurple, partial(self.set_filter_opt, value=FilterOpt.INT.EQUAL)),
                    Button(">", ButtonStyle.blurple, partial(self.set_filter_opt, value=FilterOpt.INT.SUPERIOR)),
                ], self.m_menu)

    def sw_btn_bool(self) -> SwitchButton:
        return SwitchButton([
            Button(label, ButtonStyle.blurple, partial(self.set_filter_value, value=value))
            for label, value in self.filter_slc("values").items()], self.m_menu)

    def sw_btn_genre(self) -> SwitchButton:
        return SwitchButton([
            Button("inclus", ButtonStyle.blurple, partial(self.set_filter_opt, value=FilterOpt.Genre.INCLUDE)),
            Button("exclu", ButtonStyle.blurple, partial(self.set_filter_opt, value=FilterOpt.Genre.EXCLUDE)),
        ], self.m_menu)

    # Boutons
    async def open_filter_value_int(self, interaction: Interaction):
        modal = Modal([TextInput(self.filter_slc("name"), 1, 3, check=str.isdigit)], self.set_filter_value_modal)
        await interaction.response.send_modal(modal)

    async def open_filter_value_str(self, interaction: Interaction):
        modal = Modal([TextInput(self.filter_slc("name"), 1, 64)], self.set_filter_value_modal)
        await interaction.response.send_modal(modal)

    @valide_inter()
    @menu()
    async def set_filter_value_modal(self, value):
        if value[self.filter_slc("name")]:
            self.filter_value = value[self.filter_slc("name")]

    @valide_inter()
    @menu()
    async def set_filter_value(self, value):
        if isinstance(value, list):
            value = [*map(lambda x: int(x) if isinstance(x, str) and x.isdigit() else x, value)]
            if len(value) == 1:
                value.append(0)
            self.filter_value = [*map(int, value + [0])]

    @valide_inter()
    async def set_filter_opt(self, value):
        self.filter_opt_ = value

    # Bouton qui active menu filtre ou menu trie
    @valide_inter()
    @menu()
    async def set_filter(self):
        self.slc_menu = 0

    @valide_inter()
    @menu()
    async def set_sorter(self):
        self.slc_menu = 1

    # Boutons menu principal
    @valide_inter()
    @menu()
    async def delete(self, values):
        if not isinstance(values, list):
            values = [values]
        for i in sorted(values, key=lambda x: int(x[1:]))[::-1]:
            if i[0] == "f":
                self.filters.remove_filter(int(i[1:]))
            else:
                self.filters.remove_sorter(int(i[1:]))


    @valide_inter()
    @menu()
    async def set_filter_opt_slc(self, value):
        self.filter_opt_slc = value if self.filter_opt_slc != value else None
        if self.filter_slc("type") == FilterOpt.Enum:
            self.filter_opt_ = FilterOpt.Enum.EQUAL
            self.filter_value = list(self.filter_slc("values").values())[0]
        elif self.filter_slc("type") == FilterOpt.INT:
            self.filter_opt_ = FilterOpt.INT.INFERIOR
        elif self.filter_slc("type") == FilterOpt.STR:
            self.filter_opt_ = FilterOpt.STR.CONTAINS
        elif self.filter_slc("type") == FilterOpt.Genre:
            self.filter_opt_ = FilterOpt.Genre.INCLUDE
        await self.m_menu()

    @valide_inter()
    @menu()
    async def switch_sorter_dir(self):
        self.sorter_dir = ("ASC", "DESC")[self.sorter_dir == "ASC"]

    @valide_inter()
    @menu()
    async def switch_filter_op(self):
        self.filter_op = ("AND", "OR")[self.filter_op == "AND"]

    @valide_inter()
    @menu()
    async def switch_filter_not(self):
        self.filter_not = ("", "NOT")[self.filter_not == ""]

    # Ajout des filtres/tries
    @valide_inter()
    @menu()
    async def add_sorter(self):
        _sorter = Sorter(self.filters, f"{self.filter_slc('name')} {('↑', '↓')[self.sorter_dir != 'ASC']}",
                        self.sorter_dir == 'ASC', f"m.{self.filter_opt_slc}")
        self.filters.add_sorter(_sorter)
        self.slc_menu = None

    @valide_inter()
    @menu()
    async def add_filter(self):
        where = self.filter_opt_(f"m.{self.filter_opt_slc}", self.filter_value)
        if self.filter_slc("type") == FilterOpt.Genre:
            genres = dict(await get_genres())
            name = (f"{self.filter_slc("name")} {("EXCLUDE", "INCLUDE")[self.filter_opt_ == FilterOpt.Genre.INCLUDE]} "
                    f"{tuple([genres.get(x) for x in self.filter_value[:-1]])}")
        else:
            name = self.filter_slc("name")
        _filter = Filter(self.filters, name, self.filter_op == "AND", self.filter_not == "NOT",
                         where)
        self.filters.add_filter(_filter)
        self.slc_menu = None
        self.filter_value = None

    # Valide tous les filtres
    @valide_inter()
    async def valide(self):
        self.filter_opt_slc = None
        self.slc_menu = None
        await self.parent.setup()
        # logger
        self.logger.log(f"[Filter menu] [ID: {self.message.id}] {self.parent.author.name} -> ("
                        f"filtres: {self.filters.get_filter()}; "
                        f"tries: {self.filters.get_sorters()})")

    @valide_inter()
    async def m_menu(self):
        await self.message.resource.edit(embed=self.embed, view=await self.view)


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
            TextInput("Url", 0, 255, default=self.movie.url),
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
