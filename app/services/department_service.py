import re
import unicodedata


# Values published by DTU's GetSearchValues endpoint. Course XML files store
# only these codes in Main_Dep/@UID, so search must not depend on a populated
# human-readable department column.
DEPARTMENT_NAMES = {
    "1": "Department of Applied Mathematics and Computer Science",
    "10": "Department of Physics",
    "12": "Department of Environmental and Resource Engineering",
    "13": "Department of Transport",
    "22": "Department of Health Technology",
    "23": "National Food Institute",
    "24": "National Veterinary Institute",
    "25": "National Institute of Aquatic Resources",
    "26": "Department of Chemistry",
    "27": "Department of Biotechnology and Biomedicine",
    "28": "Department of Chemical Engineering",
    "29": "DTU Biosustain",
    "30": "National Space Institute",
    "31": "Department of Electrical Engineering",
    "33": "Department of Micro and Nanotechnology",
    "34": "Department of Electrical and Photonics Engineering",
    "36": "DTU Bioinformatics",
    "38": "DTU Entrepreneurship",
    "41": "Department of Civil and Mechanical Engineering",
    "42": "Department of Technology, Management and Economics",
    "46": "Department of Wind and Energy Systems",
    "47": "Department of Energy Conversion and Storage",
    "59": "DTU Nanolab",
    "83": "Other courses",
    "IHK": "Department of Engineering Technology and Didactics",
}

_EXTRA_ALIASES = {
    "1": (
        "DTU Compute",
        "Compute",
        "Computer Science",
        "Applied Mathematics and Computer Science",
        "Institut for Matematik og Computer Science",
    ),
    "10": ("DTU Physics", "Physics", "Institut for Fysik"),
    "12": ("DTU Sustain", "DTU Environment"),
    "22": ("DTU Health Tech",),
    "23": ("DTU Food",),
    "24": ("DTU Vet",),
    "25": ("DTU Aqua",),
    "26": ("DTU Chemistry",),
    "27": ("DTU Bioengineering",),
    "28": ("DTU Chemical Engineering",),
    "30": ("DTU Space",),
    "34": ("DTU Electro",),
    "41": ("DTU Construct",),
    "42": ("DTU Management",),
    "46": ("DTU Wind",),
    "47": ("DTU Energy",),
    "IHK": ("DTU Engineering Technology",),
}


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[^\W_]+", value))


def _name_aliases(name: str) -> set[str]:
    normalized = _normalize(name)
    aliases = {normalized}
    for prefix in ("department of ", "national institute of ", "national "):
        if normalized.startswith(prefix):
            aliases.add(normalized.removeprefix(prefix))
    return aliases


_ALIASES_TO_CODES: dict[str, set[str]] = {}
for _code, _name in DEPARTMENT_NAMES.items():
    _aliases = _name_aliases(_name)
    _aliases.update(_normalize(alias) for alias in _EXTRA_ALIASES.get(_code, ()))
    _aliases.add(_normalize(_code))
    if _code.isdigit():
        _aliases.add(_normalize(_code.zfill(2)))
    for _alias in _aliases:
        _ALIASES_TO_CODES.setdefault(_alias, set()).add(_code)


def resolve_department_codes(value: str) -> set[str]:
    """Resolve a DTU department name, brand, alias, or code to XML UID values."""
    return set(_ALIASES_TO_CODES.get(_normalize(value), set()))


def department_name(code: str | None) -> str | None:
    if not code:
        return None
    return DEPARTMENT_NAMES.get(code.strip().upper())


def display_department(name: str | None, code: str | None) -> str | None:
    return name or department_name(code)
