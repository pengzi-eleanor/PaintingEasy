from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.data.keyword_knowledge import KeywordCategory, LocalizedTerms

PersonaId = Literal[
    "graphic_designer", "illustrator", "photographer", "ecommerce_worker", "ui_designer"
]
PlatformId = str


def _platform_priority(persona: PersonaId) -> list[str]:
    # Shared platform configuration is the sole source of career ordering.
    from app.services.platforms import platforms_for_persona

    return [item.id for item in platforms_for_persona(persona)]


class ModifierCondition(BaseModel):
    """Each required group must match; any_of is an optional additional trigger group."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    required_groups: list[LocalizedTerms] = Field(default_factory=list)
    any_of: LocalizedTerms = Field(default_factory=LocalizedTerms)

    @model_validator(mode="after")
    def require_trigger(self) -> ModifierCondition:
        if not self.required_groups and not self.any_of.zh and not self.any_of.en:
            raise ValueError("modifier condition must contain an explicit trigger")
        return self

    def matches(self, query: str) -> bool:
        normalized = query.casefold()

        def matches_group(group: LocalizedTerms) -> bool:
            return any(term.casefold() in normalized for term in (*group.zh, *group.en))

        if any(not matches_group(group) for group in self.required_groups):
            return False
        return not (self.any_of.zh or self.any_of.en) or matches_group(self.any_of)


class PreferredModifier(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    keyword: str = Field(min_length=1)
    category: KeywordCategory
    condition: ModifierCondition
    weight: float = Field(gt=0, le=1)
    reason: str = Field(min_length=1)

    @field_validator("category")
    @classmethod
    def reject_subject_modifier(cls, value: KeywordCategory) -> KeywordCategory:
        if value == "subject":
            raise ValueError("persona modifiers cannot introduce subjects")
        return value


class PersonaProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: PersonaId
    name: LocalizedTerms
    goal: str = Field(min_length=1)
    category_weights: dict[KeywordCategory, float]
    preferred_modifiers: list[PreferredModifier]
    blocked_expansions: list[str]
    platform_priority: list[PlatformId]
    prompt_context: str = Field(min_length=1, max_length=300)
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_profile(self) -> PersonaProfile:
        if not self.name.zh or not self.name.en:
            raise ValueError("persona name must contain Chinese and English")
        if set(self.category_weights) != {
            "subject",
            "scene",
            "color",
            "style",
            "composition",
            "quality_modifier",
            "general",
        }:
            raise ValueError("category_weights must cover every keyword category")
        if any(weight <= 0 or weight > 1.5 for weight in self.category_weights.values()):
            raise ValueError("category weight must be in (0, 1.5]")
        if len(self.platform_priority) != len(set(self.platform_priority)):
            raise ValueError("platform_priority contains duplicates")
        return self


def _condition(*, zh: list[str], en: list[str], required: list[LocalizedTerms] | None = None):
    return ModifierCondition(required_groups=required or [], any_of={"zh": zh, "en": en})


BASE_WEIGHTS = {
    "subject": 1.0,
    "scene": 1.0,
    "color": 1.0,
    "style": 1.0,
    "composition": 1.0,
    "quality_modifier": 1.0,
    "general": 1.0,
}


PERSONA_PROFILES = (
    PersonaProfile(
        id="graphic_designer",
        name={"zh": ["平面设计师"], "en": ["Graphic Designer"]},
        goal="优先满足版式、文字留白、品牌传播和营销物料需求。",
        category_weights={**BASE_WEIGHTS, "composition": 1.35, "quality_modifier": 1.15},
        preferred_modifiers=[
            PreferredModifier(
                id="gd_text_space",
                keyword="copy space",
                category="composition",
                condition=_condition(zh=["海报", "版式", "文案"], en=["poster", "layout", "copy"]),
                weight=0.76,
                reason="海报或版式意图需要预留文字区域",
            ),
            PreferredModifier(
                id="gd_brand",
                keyword="brand identity",
                category="style",
                condition=_condition(zh=["品牌"], en=["brand", "branding"]),
                weight=0.72,
                reason="品牌意图触发统一的品牌视觉表达",
            ),
            PreferredModifier(
                id="gd_marketing",
                keyword="marketing campaign",
                category="general",
                condition=_condition(zh=["营销", "促销"], en=["marketing", "promotion"]),
                weight=0.7,
                reason="营销用途明确时补充商业传播语境",
            ),
        ],
        blocked_expansions=["subject_person", "subject_cat"],
        platform_priority=_platform_priority("graphic_designer"),
        prompt_context="关注版式层级、文字留白、品牌一致性与营销用途，不改变原始主体。",
        version=1,
    ),
    PersonaProfile(
        id="illustrator",
        name={"zh": ["插画师"], "en": ["Illustrator"]},
        goal="优先呈现画风、角色设定、概念表达和色彩方案。",
        category_weights={**BASE_WEIGHTS, "style": 1.35, "color": 1.25},
        preferred_modifiers=[
            PreferredModifier(
                id="il_character",
                keyword="character design",
                category="style",
                condition=_condition(zh=["角色", "人物设定"], en=["character"]),
                weight=0.78,
                reason="角色意图明确时补充角色设计表达",
            ),
            PreferredModifier(
                id="il_concept",
                keyword="concept art",
                category="style",
                condition=_condition(zh=["概念", "世界观"], en=["concept", "worldbuilding"]),
                weight=0.75,
                reason="概念创作意图触发概念艺术方向",
            ),
            PreferredModifier(
                id="il_palette",
                keyword="color palette",
                category="color",
                condition=_condition(zh=["色彩", "配色"], en=["color", "palette"]),
                weight=0.72,
                reason="配色意图明确时补充色板检索词",
            ),
        ],
        blocked_expansions=["subject_technology"],
        platform_priority=_platform_priority("illustrator"),
        prompt_context="关注画风、角色、概念设定与色彩语言，只在明确语义下扩展。",
        version=1,
    ),
    PersonaProfile(
        id="photographer",
        name={"zh": ["摄影师"], "en": ["Photographer"]},
        goal="优先关注光线、镜头语言、景别和可解释构图。",
        category_weights={**BASE_WEIGHTS, "composition": 1.3, "scene": 1.15, "color": 1.1},
        preferred_modifiers=[
            PreferredModifier(
                id="ph_light",
                keyword="natural light",
                category="color",
                condition=_condition(
                    zh=["光线", "自然光", "摄影"], en=["light", "lighting", "photo"]
                ),
                weight=0.76,
                reason="光线或摄影意图触发自然光表现",
            ),
            PreferredModifier(
                id="ph_lens",
                keyword="50mm lens",
                category="composition",
                condition=_condition(zh=["镜头", "焦段"], en=["lens", "focal length"]),
                weight=0.72,
                reason="镜头意图明确时补充标准焦段",
            ),
            PreferredModifier(
                id="ph_shot",
                keyword="wide shot",
                category="composition",
                condition=_condition(zh=["景别", "全景"], en=["shot size", "wide shot"]),
                weight=0.7,
                reason="景别意图明确时补充全景构图",
            ),
        ],
        blocked_expansions=["style_oil_painting"],
        platform_priority=_platform_priority("photographer"),
        prompt_context="关注真实光线、镜头、景别与构图，不将摄影偏好变成新主体。",
        version=1,
    ),
    PersonaProfile(
        id="ecommerce_worker",
        name={"zh": ["电商工作者"], "en": ["E-commerce Worker"]},
        goal="优先满足商品展示、干净背景和商业转化用途。",
        category_weights={
            **BASE_WEIGHTS,
            "scene": 1.25,
            "composition": 1.2,
            "quality_modifier": 1.2,
        },
        preferred_modifiers=[
            PreferredModifier(
                id="ec_showcase",
                keyword="product showcase",
                category="composition",
                condition=_condition(zh=["商品", "产品"], en=["product", "item"]),
                weight=0.78,
                reason="商品意图触发展示型构图",
            ),
            PreferredModifier(
                id="ec_background",
                keyword="clean background",
                category="scene",
                condition=_condition(zh=["背景", "白底"], en=["background", "white background"]),
                weight=0.74,
                reason="背景意图明确时突出干净商品背景",
            ),
            PreferredModifier(
                id="ec_commercial",
                keyword="commercial use",
                category="general",
                condition=_condition(
                    zh=["商业", "电商", "广告"], en=["commercial", "ecommerce", "ad"]
                ),
                weight=0.7,
                reason="商业用途明确时补充商用语境",
            ),
        ],
        blocked_expansions=["general_inspiration"],
        platform_priority=_platform_priority("ecommerce_worker"),
        prompt_context="关注商品主体的清晰展示、背景控制和商业用途，不替换商品主体。",
        version=1,
    ),
    PersonaProfile(
        id="ui_designer",
        name={"zh": ["UI 设计师"], "en": ["UI Designer"]},
        goal="仅在存在 UI 意图时关注界面、设备、组件和设计系统。",
        category_weights={**BASE_WEIGHTS, "composition": 1.3, "style": 1.15},
        preferred_modifiers=[
            PreferredModifier(
                id="ui_interface",
                keyword="user interface",
                category="composition",
                condition=_condition(
                    zh=["界面", "UI", "应用"], en=["ui", "interface", "app screen"]
                ),
                weight=0.8,
                reason="检测到 UI 意图后补充界面检索词",
            ),
            PreferredModifier(
                id="ui_device",
                keyword="device mockup",
                category="composition",
                condition=_condition(
                    zh=["设备", "手机", "平板"],
                    en=["device", "phone", "tablet"],
                    required=[
                        LocalizedTerms(zh=["界面", "UI"], en=["ui", "interface", "app screen"])
                    ],
                ),
                weight=0.74,
                reason="同时存在 UI 与设备意图时补充设备样机",
            ),
            PreferredModifier(
                id="ui_system",
                keyword="design system",
                category="style",
                condition=_condition(
                    zh=["组件", "设计系统"],
                    en=["component", "design system"],
                    required=[
                        LocalizedTerms(zh=["界面", "UI"], en=["ui", "interface", "app screen"])
                    ],
                ),
                weight=0.72,
                reason="同时存在 UI 与组件意图时补充设计系统",
            ),
        ],
        blocked_expansions=["subject_person", "subject_cat"],
        platform_priority=_platform_priority("ui_designer"),
        prompt_context="仅在明确 UI 意图时关注界面、设备、组件和设计系统，保留原始主体。",
        version=1,
    ),
)

PERSONAS = {profile.id: profile for profile in PERSONA_PROFILES}
