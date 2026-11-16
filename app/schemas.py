from typing import Literal

from pydantic import BaseModel, Field


class KanjiData(BaseModel):
    character: str
    level: str = Field(pattern=r"^N[3-5]$")
    meanings: list[str] = Field(default_factory=list)
    onyomi: list[str] = Field(default_factory=list)
    kunyomi: list[str] = Field(default_factory=list)
    stroke_count: int | None = None
    grade: int | None = None


class VocabularyData(BaseModel):
    word: str
    reading: str | None = None
    meanings: list[str] = Field(default_factory=list)
    jlpt_level: str | None = Field(default=None, pattern=r"^N[1-5]$")


class ReviewAnswer(BaseModel):
    item_type: Literal["kanji", "vocabulary"]
    item_id: str = Field(min_length=1, max_length=255)
    quality: int = Field(ge=0, le=5)
