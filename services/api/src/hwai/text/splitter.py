"""Text splitting behind an interface so a Thai splitter can plug in later."""

import re
from abc import ABC, abstractmethod


class TextSplitter(ABC):
    @abstractmethod
    def units(self, text: str) -> list[str]:
        """Split text into renderable units. Newlines are kept as their own "\\n" units."""


class EnglishSplitter(TextSplitter):
    """Words and punctuation marks as separate units; newlines preserved."""

    _TOKEN = re.compile(r"\n|[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*|[^\sA-Za-z0-9]")

    def units(self, text: str) -> list[str]:
        return self._TOKEN.findall(text.replace("\r\n", "\n").replace("\r", "\n"))
