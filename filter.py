import datetime
from copy import deepcopy
from enum import Enum as Enume
from functools import reduce


class FilterOpt:

    class STR(Enume):
        EQUAL = ("Egale", lambda key, value: f"{key}='{value}'")
        NOT_EQUAL = ("Différent", lambda key, value: f"{key}<>'{value}'")
        CONTAINS = ("Contient", lambda key, value: f"{key} like '%{value}%'")

    class INT(Enume):
        EQUAL = ("Egale", lambda key, value: f"{key}={value}")
        NOT_EQUAL = ("Différent", lambda key, value: f"{key}<>{value}")
        SUPERIOR = ("Superieure", lambda key, value: f"{key}>{value}")
        INFERIOR = ("Inferieur", lambda key, value: f"{key}<{value}")
        BETWEEN = ("Entre", lambda key, value: f"{key} BETWEEN {value[0]} AND {value[1]}")

    class DATE(Enume):
        EQUAL = ("Egale", lambda key, value: f"{key} BETWEEN {value} AND {value + datetime.timedelta(1)}")
        NOT_EQUAL = ("Différent", lambda key, value: f"{key} NOT BETWEEN {value} AND {value + datetime.timedelta(1)}")
        SUPERIOR = ("Superieure", lambda key, value: f"{key}>{value}")
        INFERIOR = ("Inferieur", lambda key, value: f"{key}<{value}")
        BETWEEN = ("Entre", lambda key, value: f"{key} BETWEEN {value[0]} AND {value[1] + datetime.timedelta(1)}")

    class Genre(Enume):
        INCLUDE = ("Inclus", lambda _, value: f"g.id in {tuple(list(value) + [value[0]])}")
        EXCLUDE = ("Exclus", lambda _, value: (f"m.id not in (SELECT DISTINCT m.id FROM movies m "
                                      f"LEFT JOIN d_genre_movie d on d.movie_id = m.id "
                                      f"LEFT JOIN genres g on g.id = d.genre_id WHERE g.id in {tuple(list(value) + [value[0]])})"))

    class Enum(Enume):
        EQUAL = ("Egale", lambda key, value: f"{key}={value}")


class Filters:
    def __init__(self):
        self._filters: list["Filter"] = []
        self._sorters: list["Sorter"] = []

        self.genres_include = []
        self.genres_exclude = []

        self.genres = None

    @property
    def sorters(self):
        return self._sorters

    @property
    def filters(self):
        filters = deepcopy(self._filters)
        if self.genres_include:
            filters.append(
                Filter(None, f"Inclus {[self.genres[x] for x in self.genres_include]}",
                       True, False, FilterOpt.Genre.INCLUDE.value[1](None, self.genres_include))
            )
        if self.genres_exclude:
            filters.append(
                Filter(None, f"Exclus {[self.genres[x] for x in self.genres_exclude]}",
                       True, False, FilterOpt.Genre.EXCLUDE.value[1](None, self.genres_exclude))
            )
        return filters

    def add_filter(self, _filter: "Filter"):
        self._filters.append(_filter)
        if _filter.index == 0:
            _filter.as_and = None

    def remove_filter(self, index):
        if 0 <= index < len(self._filters):
            self._filters.pop(index)
            if index == 0 and self._filters:
                self._filters[0].as_and = None
        elif index == len(self._filters):
            if self.genres_include:
                self.genres_include.clear()
            else:
                self.genres_exclude.clear()
        elif index == len(self._filters) + 1:
            self.genres_exclude.clear()

    def add_sorter(self, sorter):
        self._sorters.append(sorter)

    def remove_sorter(self, index):
        if 0 <= index < len(self._sorters):
            self._sorters.pop(index)

    def get_filter(self) -> list:
        if self.filters:
            filters_list = reduce(lambda x, y: x + y, self.filters)
            return filters_list.cdts
        else:
            return []

    def get_sorters(self) -> list:
        if self._sorters:
            sorters_list = reduce(lambda x, y: x + y, self._sorters)
            return sorters_list.sorters
        else:
            return []

    def __bool__(self):
        return not not (self._filters or self._sorters)


class Filter:
    def __init__(self, parent, name, is_and, is_not, cdt, _id=None):
        self.parent: "Filters" = parent
        self.id = _id

        self.name = name
        self.is_and = is_and
        self.as_and = True
        self.is_not = is_not

        self._cdt = cdt

    @property
    def index(self):
        return self.parent._filters.index(self)

    @property
    def cdt(self):
        _and = ("AND", ("OR", "AND")[self.is_and])[not not self.as_and]
        _not = (None, "NOT")[self.is_not]
        l_cdt = []
        if _and:
            l_cdt.append(_and)
        if _not:
            l_cdt.append(_not)
        l_cdt.append(self._cdt)

        return " ".join(l_cdt)

    @property
    def cdts(self):
        return [self.cdt]

    def __add__(self, other: "Filter") -> "FilterList":

        return FilterList([self.cdt, other.cdt])


class FilterList:
    def __init__(self, cdts):
        self.cdts = cdts

    def __add__(self, other: "Filter"):

        return FilterList(self.cdts + [other.cdt])


class Sorter:
    def __init__(self, parent, name, is_asc, value):
        self.parent: "Filters" = parent
        self.name = name
        self.is_asc = is_asc
        self.value = value

    @property
    def index(self):
        return self.parent._sorters.index(self)

    @property
    def sorters(self):
        return [f"{self.value} {("DESC", "ASC")[self.is_asc]}"]

    def __add__(self, other: "Sorter") -> "SorterList":
        return SorterList([f"{self.value} {("DESC", "ASC")[self.is_asc]}", f"{other.value} {("DESC", "ASC")[other.is_asc]}"])

class SorterList:
    def __init__(self, sorters):
        self.sorters = sorters

    def __add__(self, other: "Sorter"):
        return SorterList(self.sorters + [f"{other.value} {("DESC", "ASC")[other.is_asc]}"])


