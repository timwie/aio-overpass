import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from aio_overpass.element import Element

import langcodes
import pytest


@dataclass(unsafe_hash=True)
class Name:
    key: str = field(hash=True)
    prefixes: list[str] = field(hash=False)
    suffixes: list[str] = field(hash=False)

    def __repr__(self) -> str:
        parts = self.prefixes + ["name"] + self.suffixes
        return f"{type(self).__name__}({parts})"


@dataclass(unsafe_hash=True)
class NameInLanguage(Name):
    lang: langcodes.Language = field(hash=False)

    @property
    def lang_native_name(self):
        return self.lang.autonym()

    @property
    def lang_english_name(self):
        return self.lang.autonym()

    def __repr__(self) -> str:
        parts = self.prefixes + ["name"] + self.suffixes
        return f"{type(self).__name__}(in '{self.lang}': {parts})"


def _names_from_element(elem: Element) -> list[Name]:
    if not elem.tags:
        return []

    # TODO: https://wiki.openstreetmap.org/wiki/Proposal:Omitted_name_tag
    if elem.tags.get("noname") == "yes":
        return []

    keys = []

    for key in elem.tags.keys():
        if "name" not in key:
            continue
        name = _name_from_key(key)
        if name:
            keys.append(name)

    return keys


def _name_from_key(key: str) -> Optional[Name]:
    split = re.split(r"[_:]", key)
    prefixes = []
    suffixes = []

    if "name" not in split:
        return None

    for i, part in enumerate(split):
        if not part:
            continue
        if part == "name":
            break
        prefixes.append(part)

    for j, part in enumerate(split):
        if not part or j <= i:
            continue
        suffixes.append(part)

    lang = _lang(suffixes=suffixes)
    if lang is None:
        return Name(key=key, prefixes=prefixes, suffixes=suffixes)
    return NameInLanguage(key=key, prefixes=prefixes, suffixes=suffixes, lang=lang)


def _lang(suffixes: list[str]) -> Optional[langcodes.Language]:
    if not suffixes:
        return None

    try:
        lang = langcodes.Language.get(suffixes[0], normalize=True)
        if lang.is_valid():
            del suffixes[0]
            return lang
    except langcodes.LanguageTagError:
        pass

    return None


@pytest.mark.skip
def test_name_keys():
    data_path = Path(__file__).parent / "tag_data" / "name_keys.json"
    with data_path.open() as f:
        data = json.load(f)

    for entry in data["data"]:
        key = entry["key"]
        hmm = _name_from_key(entry["key"])
        print(f"{key} - {hmm!r}")
