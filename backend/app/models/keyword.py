from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

KeywordCategory = Literal[
    "subject", "scene", "color", "style", "composition", "quality_modifier", "general"
]


class LocalizedTerms(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    zh: list[str] = Field(default_factory=list)
    en: list[str] = Field(default_factory=list)

    @field_validator("zh", "en")
    @classmethod
    def normalize_terms(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))
