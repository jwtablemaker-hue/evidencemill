from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Iterable


_NUMBER_FULL_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")

_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9.])[+-]?\d+(?:\.\d+)?"
    r"|(?<![A-Za-z])(?:km/h|kph|mph|kpa|psi|bar|wh|ah|kw|mm|cm|kg|lbs?|"
    r"inches?|inch|hours?|hrs?|hr|minutes?|mins?|min|seconds?|secs?|sec|"
    r"days?|weeks?|months?|years?|deg|degrees?|degree|°c|°f)(?![A-Za-z])"
    r"|(?<![A-Za-z])(?:w|v|a|h|s|c|f|in)(?![A-Za-z])"
    r"|(?:\+/-|±)"
    r"|[A-Za-z]+(?:-[A-Za-z]+)?"
    r"|[×/%°\"″]|[-–—]"
    r"|(?<![A-Za-z])x(?![A-Za-z])",
    re.I,
)

_UNIT_MAP = {
    "km/h": "kmh", "kph": "kmh", "mph": "mph",
    "kpa": "kPa", "psi": "psi", "bar": "bar",
    "wh": "Wh", "ah": "Ah", "kw": "kW", "w": "W", "v": "V", "a": "A",
    "mm": "mm", "cm": "cm", "kg": "kg",
    "lb": "lb", "lbs": "lb", "in": "in", "inch": "in", "inches": "in",
    "h": "h", "hr": "h", "hrs": "h", "hour": "h", "hours": "h",
    "min": "min", "mins": "min", "minute": "min", "minutes": "min",
    "s": "s", "sec": "s", "secs": "s", "second": "s", "seconds": "s",
    "day": "day", "days": "day", "week": "week", "weeks": "week",
    "month": "month", "months": "month", "year": "year", "years": "year",
    "percent": "percent", "%": "percent",
    "deg": "deg", "degree": "deg", "degrees": "deg", "°": "deg",
    "c": "degC", "°c": "degC", "f": "degF", "°f": "degF",
}

_COMPONENT_WORDS = {
    "motor": "motor", "motors": "motor",
    "battery": "battery", "batteries": "battery",
    "pack": "battery", "packs": "battery",
    "brake": "brake", "brakes": "brake",
    "charger": "charger", "chargers": "charger",
    "tire": "tire", "tires": "tire", "tyre": "tire", "tyres": "tire",
    "wheel": "wheel", "wheels": "wheel",
    "suspension": "suspension", "shock": "suspension", "shocks": "suspension",
    "light": "lighting", "lights": "lighting", "lighting": "lighting",
    "controller": "controller", "controllers": "controller",
    "display": "display", "displays": "display",
    "connector": "connector", "connectors": "connector",
    "port": "port", "ports": "port",
    "throttle": "throttle", "throttles": "throttle",
    "caliper": "caliper", "calipers": "caliper",
    "rotor": "rotor", "rotors": "rotor",
    "drum": "drum", "drums": "drum",
}

_PHRASE_FLAGS = {
    ("per", "motor"): "per_motor",
    ("each", "motor"): "each_motor",
    ("per", "battery"): "per_battery",
    ("each", "battery"): "each_battery",
    ("front", "only"): "front_only",
    ("rear", "only"): "rear_only",
    ("sport", "mode"): "sport_mode",
    ("eco", "mode"): "eco_mode",
    ("dual", "mode"): "dual_mode",
    ("depending", "on"): "depending",
    ("variant", "only"): "variant_only",
    ("rating", "unspecified"): "rating_unspecified",
    ("rating", "unknown"): "rating_unspecified",
}

_SINGLE_FLAGS = {
    "optional": "optional", "alternative": "alternative",
    "replacement": "replacement", "aftermarket": "aftermarket",
    "either": "either", "conflict": "conflict", "conflicting": "conflict",
    "unresolved": "unresolved", "combined": "combined", "total": "combined",
    "system": "system", "peak": "peak", "maximum": "maximum", "max": "maximum",
    "rated": "rated", "continuous": "rated", "nominal": "nominal",
    "dual": "dual", "two": "two", "pair": "pair", "front": "front", "rear": "rear",
}

_SCOPED_REVIEW_FLAGS = frozenset({
    "optional", "alternative", "replacement", "aftermarket", "either", "depending",
    "conflict", "unresolved", "front_only", "rear_only", "sport_mode", "eco_mode",
    "dual_mode", "variant_only", "per_motor", "each_motor", "per_battery", "each_battery",
})


@dataclass(frozen=True)
class Token:
    text: str
    norm: str
    start: int
    end: int


@dataclass(frozen=True)
class ComponentMention:
    kind: str
    text: str
    token_index: int
    placement: str | None = None
    multiplicity: int | None = None


@dataclass(frozen=True)
class Measurement:
    value: float | tuple[float, float]
    unit: str
    text: str
    token_index: int
    value_kind: str = "scalar"
    component_kind: str | None = None
    placement: str | None = None
    scope: str = "unknown"
    multiplicity: int | None = None
    qualifiers: tuple[str, ...] = ()


@dataclass(frozen=True)
class StatementStructure:
    text: str
    tokens: tuple[Token, ...]
    components: tuple[ComponentMention, ...]
    measurements: tuple[Measurement, ...]
    flags: frozenset[str]

    def to_dict(self) -> dict:
        return {
            "components": [asdict(item) for item in self.components],
            "measurements": [asdict(item) for item in self.measurements],
            "flags": sorted(self.flags),
        }


def _tokens(text: str) -> list[Token]:
    return [
        Token(m.group(0), m.group(0).casefold(), m.start(), m.end())
        for m in _TOKEN_RE.finditer(text)
    ]


def _phrase_flags(words: list[str]) -> set[str]:
    out = {_SINGLE_FLAGS[word] for word in words if word in _SINGLE_FLAGS}
    for phrase, flag in _PHRASE_FLAGS.items():
        size = len(phrase)
        if any(tuple(words[i:i + size]) == phrase for i in range(len(words) - size + 1)):
            out.add(flag)
    for i in range(len(words) - 1):
        if words[i] == "2" and words[i + 1] in {"x", "×"}:
            out.add("two")
    return out


def _near(words: list[str], index: int, candidates: Iterable[str], radius: int = 4) -> set[str]:
    lo = max(0, index - radius)
    hi = min(len(words), index + radius + 1)
    wanted = set(candidates)
    return {word for word in words[lo:hi] if word in wanted}


def _same_clause(text: str, left: Token, right: Token) -> bool:
    start = min(left.end, right.end)
    end = max(left.start, right.start)
    if end <= start:
        return True
    return re.search(r"[,;.!?]", text[start:end]) is None


def _near_tokens(
    tokens: list[Token],
    index: int,
    candidates: Iterable[str],
    text: str,
    radius: int = 4,
) -> set[str]:
    lo = max(0, index - radius)
    hi = min(len(tokens), index + radius + 1)
    wanted = set(candidates)
    anchor = tokens[index]
    return {
        tokens[i].norm
        for i in range(lo, hi)
        if tokens[i].norm in wanted and _same_clause(text, anchor, tokens[i])
    }


def _placement(words: list[str], index: int) -> str | None:
    for distance in range(1, 4):
        candidate = index - distance
        if candidate >= 0 and words[candidate] in {"front", "rear"}:
            return words[candidate]
    for distance in range(1, 4):
        candidate = index + distance
        if candidate < len(words) and words[candidate] in {"front", "rear"}:
            return words[candidate]
    return None


def _multiplicity(words: list[str], index: int) -> int | None:
    if _near(words, index, {"dual", "two", "pair"}, 3):
        return 2
    lo = max(0, index - 4)
    hi = min(len(words), index + 2)
    window = words[lo:hi]
    for i in range(len(window) - 1):
        if window[i] == "2" and window[i + 1] in {"x", "×"}:
            return 2
    return None


def analyze_statement(text: str) -> StatementStructure:
    tokens = _tokens(text)
    words = [token.norm for token in tokens]
    flags = _phrase_flags(words)

    components: list[ComponentMention] = []
    for index, token in enumerate(tokens):
        kind = _COMPONENT_WORDS.get(token.norm)
        if kind:
            components.append(ComponentMention(
                kind=kind,
                text=token.text,
                token_index=index,
                placement=_placement(words, index),
                multiplicity=_multiplicity(words, index),
            ))

    measurements: list[Measurement] = []
    for index in range(len(tokens) - 1):
        number, unit_token = tokens[index], tokens[index + 1]
        if not re.fullmatch(r"\d+(?:\.\d+)?", number.norm):
            continue
        unit = _UNIT_MAP.get(unit_token.norm)
        if unit is None:
            continue

        qualifier_words = _near_tokens(
            tokens,
            index,
            {
                "combined", "total", "system", "peak", "maximum", "max",
                "rated", "continuous", "nominal", "each", "per",
            },
            text,
            4,
        )
        qualifiers = set()
        for word in qualifier_words:
            if word in {"maximum", "max"}:
                qualifiers.add("maximum")
            elif word == "continuous":
                qualifiers.add("rated")
            else:
                qualifiers.add(word)

        nearest = None
        if components and not ({"combined", "total", "system"} & qualifier_words):
            local_components = [
                item
                for item in components
                if abs(item.token_index - index) <= 6
                and _same_clause(text, tokens[index], tokens[item.token_index])
            ]
            if local_components:
                nearest = min(
                    local_components,
                    key=lambda item: (
                        abs(item.token_index - index),
                        0 if item.token_index > index else 1,
                    ),
                )

        scope = "unknown"
        multiplicity = nearest.multiplicity if nearest else None
        if {"combined", "total", "system"} & qualifier_words:
            scope = "system"
        elif "per" in qualifier_words or "each" in qualifier_words:
            scope = "each"
        elif nearest and nearest.multiplicity and nearest.token_index > index:
            scope = "each"
        elif nearest:
            scope = "component"

        value: float | tuple[float, float] = float(number.norm)
        value_kind = "scalar"
        value_start = number.start

        if index >= 2 and re.fullmatch(r"\\d+(?:\\.\\d+)?", tokens[index - 2].norm):
            separator = tokens[index - 1].norm
            if separator in {"-", "–", "—", "to"}:
                value = (float(tokens[index - 2].norm), float(number.norm))
                value_kind = "range"
                value_start = tokens[index - 2].start
            elif separator == "/":
                value = (float(tokens[index - 2].norm), float(number.norm))
                value_kind = "alternatives"
                value_start = tokens[index - 2].start
                qualifiers.add("alternative")

        measurements.append(Measurement(
            value=value,
            unit=unit,
            text=text[value_start:unit_token.end],
            token_index=index,
            value_kind=value_kind,
            component_kind=nearest.kind if nearest else None,
            placement=nearest.placement if nearest else None,
            scope=scope,
            multiplicity=multiplicity,
            qualifiers=tuple(sorted(qualifiers)),
        ))

    return StatementStructure(
        text=text,
        tokens=tuple(tokens),
        components=tuple(components),
        measurements=tuple(measurements),
        flags=frozenset(flags),
    )


def requires_scoped_review(structure: StatementStructure) -> bool:
    return bool(structure.flags & _SCOPED_REVIEW_FLAGS)


def component_placements(structure: StatementStructure, kind: str) -> set[str]:
    return {
        item.placement
        for item in structure.components
        if item.kind == kind and item.placement is not None
    }
