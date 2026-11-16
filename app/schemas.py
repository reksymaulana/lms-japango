from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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


class SessionExchangeRequest(BaseModel):
    access_token: str = Field(min_length=1, max_length=8192)


class CategoryData(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Category name cannot be blank")
        return normalized


class MaterialData(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(default="", max_length=1000)
    content: str = Field(min_length=1, max_length=50000)
    category_id: int | None = Field(default=None, ge=1)

    @field_validator("title", "content")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field cannot be blank")
        return normalized

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        return value.strip()


class QuizData(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=1000)
    category_id: int | None = Field(default=None, ge=1)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Quiz title cannot be blank")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return value.strip()


class QuizQuestionData(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000)
    question_type: Literal["multiple_choice", "written"]
    options: list[str] = Field(default_factory=list, max_length=10)
    answer_key: str = Field(min_length=1, max_length=5000)
    points: int = Field(default=1, ge=1, le=100)

    @field_validator("prompt", "answer_key")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field cannot be blank")
        return normalized

    @field_validator("options")
    @classmethod
    def normalize_options(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if any(len(value) > 500 for value in normalized):
            raise ValueError("Each answer option must be at most 500 characters")
        return normalized

    @model_validator(mode="after")
    def validate_answer_key(self) -> "QuizQuestionData":
        if self.question_type == "multiple_choice":
            if len(self.options) < 2:
                raise ValueError("Multiple-choice questions need at least two options")
            if len(self.answer_key) > 500:
                raise ValueError("Multiple-choice answer key is too long")
            if len(set(self.options)) != len(self.options):
                raise ValueError("Multiple-choice options must be unique")
            if self.answer_key not in self.options:
                raise ValueError("Correct answer must exactly match one option")
        elif self.options:
            raise ValueError("Written questions cannot have multiple-choice options")
        return self


class BunpouData(BaseModel):
    level: str = Field(pattern=r"^N[3-5]$")
    title: str = Field(min_length=1, max_length=255)
    explanation: str = Field(min_length=1, max_length=10000)
    examples: list[dict[str, str]] = Field(min_length=1, max_length=20)

    @field_validator("title", "explanation")
    @classmethod
    def normalize_grammar_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field cannot be blank")
        return normalized

    @field_validator("examples")
    @classmethod
    def validate_examples(cls, values: list[dict[str, str]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for example in values:
            japanese = example.get("japanese", "").strip()
            translation = example.get("translation", "").strip()
            if not japanese or not translation:
                raise ValueError("Each example needs Japanese text and a translation")
            if len(japanese) > 2000 or len(translation) > 2000:
                raise ValueError("Grammar examples must be at most 2000 characters")
            normalized.append(
                {"japanese": japanese, "translation": translation}
            )
        return normalized
