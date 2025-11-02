from enum import Enum
from functools import reduce


class FilterOpt:

    class STR(Enum):
        EQUAL = lambda key, value: f"{key}='{value}'"
        NOT_EQUAL = lambda key, value: f"{key}<>'{value}'"
        CONTAINS = lambda key, value: f"{key} like '%{value}%'"

    class INT(Enum):
        EQUAL = lambda key, value: f"{key}={value}"
        NOT_EQUAL = lambda key, value: f"{key}<>{value}"
        SUPERIOR = lambda key, value: f"{key}>{value}"
        INFERIOR = lambda key, value: f"{key}<{value}"

    class Genre(Enum):
        INCLUDE = lambda _, value: f"g.id in {tuple(value)}"
        EXCLUDE = lambda _, value: (f"m.id not in (SELECT DISTINCT m.id FROM movies m "
                                      f"LEFT JOIN d_genre_movie d on d.movie_id = m.id "
                                      f"LEFT JOIN genres g on g.id = d.genre_id WHERE g.id in {tuple(value)})")

    class Enum(Enum):
        EQUAL = lambda key, value: f"{key}={value}"


class Filters:
    def __init__(self):
        self.filters: list["Filter"] = []
        self.sorters: list["Sorter"] = []

    def add_filter(self, _filter: "Filter"):
        self.filters.append(_filter)
        if _filter.index == 0:
            _filter.as_and = None

    def remove_filter(self, index):
        if 0 <= index < len(self.filters):
            self.filters.pop(index)
        if index == 0 and self.filters:
            self.filters[0].as_and = None

    def add_sorter(self, sorter):
        self.sorters.append(sorter)

    def remove_sorter(self, index):
        if 0 <= index < len(self.sorters):
            self.sorters.pop(index)

    def get_filter(self) -> list:
        if self.filters:
            filters_list = reduce(lambda x, y: x + y, self.filters)
            return filters_list.cdts
        else:
            return []

    def get_sorters(self) -> list:
        if self.sorters:
            sorters_list = reduce(lambda x, y: x + y, self.sorters)
            return sorters_list.sorters
        else:
            return []

    def __bool__(self):
        return not not (self.filters or self.sorters)


class Filter:
    def __init__(self, parent, name, is_and, is_not, cdt):
        self.parent: "Filters" = parent

        self.name = name
        self.is_and = is_and
        self.as_and = True
        self.is_not = is_not

        self._cdt = cdt

    @property
    def index(self):
        return self.parent.filters.index(self)

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
        return self.parent.sorters.index(self)

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


