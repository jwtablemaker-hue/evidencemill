from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Iterable


_NUMBER_FULL_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")

_TOKEN_RE = re.compile(
    r"(?<=approx\.)[+-]?\d+(?:\.\d+)?"
    r"|(?<=approximately\.)[+-]?\d+(?:\.\d+)?"
    r"|(?<=approximate\.)[+-]?\d+(?:\.\d+)?"
    r"|(?<![A-Za-z0-9.])[+-]?\d+(?:\.\d+)?"
    r"|(?<![A-Za-z])(?:km/h|kph|mph|km|mi|ft|kpa|psi|bar|wh|ah|kw|mm|cm|kg|lbs?|"
    r"inches?|inch|hours?|hrs?|hr|minutes?|mins?|min|seconds?|secs?|sec|"
    r"days?|weeks?|months?|years?|deg|degrees?|degree|°c|°f)(?![A-Za-z])"
    r"|(?<![A-Za-z])(?:w|v|a|h|s|c|f|in|m)(?![A-Za-z])"
    r"|(?:\+/-|±)"
    r"|[A-Za-z]+(?:-[A-Za-z]+)?"
    r"|[×/%°\"″]|[-–—]"
    r"|(?<![A-Za-z])x(?![A-Za-z])",
    re.I,
)

_UNIT_MAP = {
    "km/h": "kmh", "kph": "kmh", "mph": "mph",
    "km": "km", "mi": "mi", "m": "m", "ft": "ft",
    "kpa": "kPa", "psi": "psi", "bar": "bar",
    "wh": "Wh", "ah": "Ah", "kw": "kW", "w": "W", "v": "V", "a": "A",
    "mm": "mm", "cm": "cm", "kg": "kg",
    "lb": "lb", "lbs": "lb", "in": "in", "inch": "in", "inches": "in",
    "\"": "in", "″": "in",
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

_SERVICE_ACTIONS = {
    "recharge": "recharge",
    "re-charge": "recharge",
    "charge": "charge",
    "inspect": "inspect",
    "check": "check",
    "replace": "replace",
    "lubricate": "lubricate",
    "tighten": "tighten",
    "clean": "clean",
    "open": "open",
    "insert": "insert",
    "fill": "fill",
    "fix": "fix",
    "connect": "connect",
    "cover": "cover",
    "leave": "leave",
    "wipe": "wipe",
    "wash": "wash",
    "wear": "wear",
    "turn": "turn",
    "step": "step",
    "glide": "glide",
    "use": "use",
    "ensure": "ensure",
    "locate": "locate",
    "ride": "ride",
    "keep": "keep",
    "press": "press",
    "hold": "hold",
    "start": "start",
    "fold": "fold",
    "attach": "attach",
    "test": "test",
    "find": "find",
    "unfold": "unfold",
    "follow": "follow",
    "operate": "operate",
    "secure": "secure",
    "remove": "remove",
    "pull": "pull",
    "push": "push",
    "release": "release",
    "loosen": "loosen",
    "contact": "contact",
    "discontinue": "discontinue",
    "repeat": "repeat",
    "click": "click",
    "grab": "grab",
    "put": "put",
    "add": "add",
    "adjust": "adjust",
    "avoid": "avoid",
    "stop": "stop",
    "place": "place",
    "refer": "refer",
    "visit": "visit",
    "activate": "activate",
    "unlock": "unlock",
    "inflate": "inflate",
    "reattach": "reattach",
    "align": "align",
    "perform": "perform",
}

_SERVICE_GERUNDS = {
    "using": "use",
    "checking": "check",
    "doing": "perform",
    "starting": "start",
    "riding": "ride",
    "keeping": "keep",
    "charging": "charge",
    "tightening": "tighten",
    "cleaning": "clean",
    "testing": "test",
    "adjusting": "adjust",
    "inflating": "inflate",
}

_INSTRUCTION_PREFACES = frozenset({
    "to", "first", "next", "then", "finally", "if", "when", "after",
    "before", "with", "using", "additionally", "in",
})

_RECURRENCE_UNITS = frozenset({"min", "h", "day", "week", "month", "year"})
_RECURRENCE_EVENTS = {
    "use": "use",
    "ride": "ride",
    "trip": "trip",
}
_MACHINE_WORDS = frozenset({"scooter", "escooter", "vehicle"})


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
    value: float | tuple[float, ...]
    unit: str
    text: str
    token_index: int
    value_kind: str = "scalar"
    tolerance: float | None = None
    comparison: str | None = None
    local_label: str | None = None
    component_kind: str | None = None
    placement: str | None = None
    scope: str = "unknown"
    multiplicity: int | None = None
    qualifiers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ServiceInstruction:
    actions: tuple[str, ...]
    action_text: str
    negated: bool
    mentioned_component_kinds: tuple[str, ...]
    target_machine: bool


@dataclass(frozen=True)
class RecurringServiceInstruction:
    action: str
    action_text: str
    target_component_kind: str | None
    recurrence_marker: str
    target_machine: bool = False
    recurrence_value: float | tuple[float, ...] | None = None
    recurrence_unit: str | None = None
    recurrence_event: str | None = None
    recurrence_relation: str | None = None


@dataclass(frozen=True)
class StatementStructure:
    text: str
    tokens: tuple[Token, ...]
    components: tuple[ComponentMention, ...]
    measurements: tuple[Measurement, ...]
    recurring_service_instructions: tuple[RecurringServiceInstruction, ...]
    service_instructions: tuple[ServiceInstruction, ...]
    flags: frozenset[str]

    def to_dict(self) -> dict:
        return {
            "components": [asdict(item) for item in self.components],
            "measurements": [asdict(item) for item in self.measurements],
            "recurring_service_instructions": [
                asdict(item) for item in self.recurring_service_instructions
            ],
            "service_instructions": [
                asdict(item) for item in self.service_instructions
            ],
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
    segment = text[start:end]
    return re.search(r"[,;!?]|(?<!\d)\.(?!\d)", segment) is None


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


def _value_suffix_multiplicity(text: str, unit_end: int) -> tuple[int | None, int]:
    """Preserve source forms such as 2500W*2 or 500 W × 2 as repeated units."""
    match = re.match(r"\s*(?:\*|x|×)\s*(\d+)\b", text[unit_end:], re.I)
    if not match:
        return None, unit_end
    count = int(match.group(1))
    if count <= 1:
        return None, unit_end
    return count, unit_end + match.end()


def _local_measurement_context(
    text: str,
    number_start: int,
) -> tuple[str | None, str | None]:
    boundary = max(
        text.rfind("|", 0, number_start),
        text.rfind(";", 0, number_start),
        text.rfind("\n", 0, number_start),
    )
    prefix = text[boundary + 1:number_start]

    comparison_match = re.search(
        r"(<=|>=|<|>|≤|≥)\s*$",
        prefix,
    )
    comparison = comparison_match.group(1) if comparison_match else None
    if comparison == "≤":
        comparison = "<="
    elif comparison == "≥":
        comparison = ">="

    label_match = re.search(
        r"([A-Za-z][A-Za-z0-9_-]*)\s*:\s*"
        r"(?:(?:<=|>=|<|>|≤|≥)\s*)?$",
        prefix,
    )
    nested_label_context = boundary >= 0 or prefix.count(":") >= 2
    local_label = (
        label_match.group(1)
        if label_match and nested_label_context
        else None
    )
    return comparison, local_label


def _recurring_service_instructions(
    text: str,
    tokens: list[Token],
    components: list[ComponentMention],
    measurements: list[Measurement],
) -> list[RecurringServiceInstruction]:
    """Recognize explicit recurring service actions without inventing a target.

    A duration becomes a recurrence only when the source literally uses "every"
    and a supported service action appears in the same clause.
    """
    out: list[RecurringServiceInstruction] = []
    for measurement in measurements:
        if measurement.unit not in _RECURRENCE_UNITS:
            continue
        number_index = measurement.token_index
        if number_index < 2 or tokens[number_index - 1].norm != "every":
            continue

        action_index = None
        action = None
        for index in range(number_index - 2, -1, -1):
            if not _same_clause(text, tokens[index], tokens[number_index]):
                break
            normalized = _SERVICE_ACTIONS.get(tokens[index].norm)
            if normalized:
                action_index = index
                action = normalized
                break
        if action_index is None or action is None:
            continue

        clause_components = {
            item.kind
            for item in components
            if _same_clause(text, tokens[number_index], tokens[item.token_index])
        }
        target_component_kind = (
            next(iter(clause_components)) if len(clause_components) == 1 else None
        )

        target_machine = (
            target_component_kind is None
            and any(token.norm in _MACHINE_WORDS for token in tokens)
        )
        unit_token = tokens[number_index + 1]
        out.append(RecurringServiceInstruction(
            action=action,
            action_text=text[tokens[action_index].start:unit_token.end],
            target_component_kind=target_component_kind,
            recurrence_marker="every",
            target_machine=target_machine,
            recurrence_value=measurement.value,
            recurrence_unit=measurement.unit,
        ))
    return out


def _event_recurring_service_instructions(
    text: str,
    tokens: list[Token],
    components: list[ComponentMention],
) -> list[RecurringServiceInstruction]:
    """Recognize explicit before/after-every-event service recurrence.

    Event recurrence is preserved separately from time duration. It does not
    synthesize a numeric interval or invent a component target.
    """
    out: list[RecurringServiceInstruction] = []
    for index in range(len(tokens) - 2):
        relation = tokens[index].norm
        if relation not in {"before", "after"}:
            continue
        if tokens[index + 1].norm != "every":
            continue
        event = _RECURRENCE_EVENTS.get(tokens[index + 2].norm)
        if event is None:
            continue

        action_index = None
        action = None

        # Suffix form: "check ... before every use"
        for candidate in range(index - 1, -1, -1):
            segment = text[tokens[candidate].end:tokens[index].start]
            if re.search(r"[;!?]|(?<!\\d)\\.(?!\\d)", segment):
                break
            normalized = _SERVICE_ACTIONS.get(tokens[candidate].norm)
            if normalized:
                action_index = candidate
                action = normalized
                break

        # Prefix form: "after every use, charge ..."
        if action_index is None:
            for candidate in range(index + 3, len(tokens)):
                segment = text[tokens[index + 2].end:tokens[candidate].start]
                if re.search(r"[;!?]|(?<!\\d)\\.(?!\\d)", segment):
                    break
                normalized = _SERVICE_ACTIONS.get(tokens[candidate].norm)
                if normalized:
                    action_index = candidate
                    action = normalized
                    break

        if action_index is None or action is None:
            continue

        component_kinds = {
            item.kind
            for item in components
            if not re.search(
                r"[;!?]|(?<!\\d)\\.(?!\\d)",
                text[
                    min(tokens[action_index].end, tokens[item.token_index].end):
                    max(tokens[action_index].start, tokens[item.token_index].start)
                ],
            )
        }
        target_component_kind = (
            next(iter(component_kinds)) if len(component_kinds) == 1 else None
        )
        target_machine = (
            target_component_kind is None
            and any(token.norm in _MACHINE_WORDS for token in tokens)
        )

        out.append(RecurringServiceInstruction(
            action=action,
            action_text=text.strip(),
            target_component_kind=target_component_kind,
            recurrence_marker="every",
            target_machine=target_machine,
            recurrence_event=event,
            recurrence_relation=relation,
        ))
    return out


def _direct_service_instructions(
    text: str,
    tokens: list[Token],
    components: list[ComponentMention],
) -> list[ServiceInstruction]:
    """Recognize source-explicit direct imperatives/prohibitions only."""
    if not tokens:
        return []

    index = 0
    if _NUMBER_FULL_RE.fullmatch(tokens[index].norm):
        index += 1
        if index >= len(tokens):
            return []

    negated = False
    while index < len(tokens) and tokens[index].norm in {"always", "please"}:
        index += 1
    if (
        index < len(tokens)
        and tokens[index].norm == "do"
        and index + 1 < len(tokens)
        and tokens[index + 1].norm == "not"
    ):
        negated = True
        index += 2
    elif index < len(tokens) and tokens[index].norm == "never":
        negated = True
        index += 1

    if index >= len(tokens):
        return []
    # A component label can start with a word that also names an action.
    if [token.norm for token in tokens[index:]] in (["turn", "signal"], ["turn", "signals"]):
        return []
    if (
        tokens[index].norm == "make"
        and index + 1 < len(tokens)
        and tokens[index + 1].norm == "sure"
    ):
        first_action = "ensure"
    else:
        first_action = _SERVICE_ACTIONS.get(tokens[index].norm)
    if first_action is None:
        return []

    actions = [first_action]
    if (
        index + 2 < len(tokens)
        and tokens[index + 1].norm == "and"
        and tokens[index + 2].norm in _SERVICE_ACTIONS
    ):
        actions.append(_SERVICE_ACTIONS[tokens[index + 2].norm])

    mentioned = tuple(sorted({item.kind for item in components}))
    target_machine = any(token.norm in _MACHINE_WORDS for token in tokens)
    return [ServiceInstruction(
        actions=tuple(actions),
        action_text=text.strip(),
        negated=negated,
        mentioned_component_kinds=mentioned,
        target_machine=target_machine,
    )]


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
    consumed_measurement_numbers: set[int] = set()
    for index in range(len(tokens) - 1):
        if index in consumed_measurement_numbers:
            continue
        number, unit_token = tokens[index], tokens[index + 1]
        if not _NUMBER_FULL_RE.fullmatch(number.norm):
            continue
        unit = _UNIT_MAP.get(unit_token.norm)
        if unit is None:
            continue

        qualifier_words = _near_tokens(
            tokens,
            index,
            {
                "combined", "total", "system", "peak", "maximum", "max",
                "rated", "continuous", "nominal", "minimum", "min", "each", "per",
            },
            text,
            4,
        )
        qualifiers = set()
        for word in qualifier_words:
            if word in {"maximum", "max"}:
                qualifiers.add("maximum")
            elif word in {"minimum", "min"}:
                qualifiers.add("minimum")
            elif word == "continuous":
                qualifiers.add("rated")
            else:
                qualifiers.add(word)

        prior_words = words[max(0, index - 5):index]
        if len(prior_words) >= 2 and prior_words[-2:] == ["up", "to"]:
            qualifiers.update({"maximum", "up_to"})
        if len(prior_words) >= 2 and prior_words[-2:] == ["at", "least"]:
            qualifiers.update({"minimum", "at_least"})
        if len(prior_words) >= 2 and prior_words[-2:] == ["at", "most"]:
            qualifiers.update({"maximum", "at_most"})
        if any(
            word in {"around", "about", "approximately", "approx"}
            for word in prior_words
        ):
            qualifiers.add("approximate")

        comparison, local_label = _local_measurement_context(
            text,
            number.start,
        )
        if comparison in {"<", "<="}:
            qualifiers.update({"maximum", "upper_bound"})
        elif comparison in {">", ">="}:
            qualifiers.update({"minimum", "lower_bound"})

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

        # Coordinated quantities can share the immediately preceding component.
        # Require one explicit component in this clause and an "and" connector;
        # never use a heading alone or cross a clause boundary.
        if nearest is None and measurements and not ({"combined", "total", "system"} & qualifier_words):
            previous = measurements[-1]
            clause_components = [item for item in components
                                 if _same_clause(text, tokens[index], tokens[item.token_index])]
            between = words[previous.token_index + 2:index]
            if (previous.component_kind and len(clause_components) == 1
                    and clause_components[0].kind == previous.component_kind
                    and between == ["and"]):
                nearest = clause_components[0]

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

        value: float | tuple[float, ...] = float(number.norm)
        value_kind = "scalar"
        value_start = number.start
        value_end = unit_token.end
        tolerance: float | None = None

        suffix_multiplicity, suffix_end = _value_suffix_multiplicity(
            text, unit_token.end
        )
        if suffix_multiplicity is not None:
            multiplicity = suffix_multiplicity
            value_end = suffix_end
            if nearest is not None and scope != "system":
                scope = "each"

        if (
            index >= 4
            and _NUMBER_FULL_RE.fullmatch(tokens[index - 4].norm)
            and tokens[index - 3].norm in {"x", "×"}
            and _NUMBER_FULL_RE.fullmatch(tokens[index - 2].norm)
            and tokens[index - 1].norm in {"x", "×"}
        ):
            value = (
                float(tokens[index - 4].norm),
                float(tokens[index - 2].norm),
                float(number.norm),
            )
            value_kind = "tuple"
            value_start = tokens[index - 4].start
        elif index >= 2 and _NUMBER_FULL_RE.fullmatch(tokens[index - 2].norm):
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

        if (
            value_kind == "scalar"
            and index + 4 < len(tokens)
            and tokens[index + 2].norm in {"+/-", "±"}
            and _NUMBER_FULL_RE.fullmatch(tokens[index + 3].norm)
            and _UNIT_MAP.get(tokens[index + 4].norm) == unit
        ):
            tolerance = abs(float(tokens[index + 3].norm))
            value_kind = "tolerance"
            qualifiers.add("tolerance")
            value_end = tokens[index + 4].end
            consumed_measurement_numbers.add(index + 3)

        measurements.append(Measurement(
            value=value,
            unit=unit,
            text=text[value_start:value_end],
            token_index=index,
            value_kind=value_kind,
            tolerance=tolerance,
            comparison=comparison,
            local_label=local_label,
            component_kind=nearest.kind if nearest else None,
            placement=nearest.placement if nearest else None,
            scope=scope,
            multiplicity=multiplicity,
            qualifiers=tuple(sorted(qualifiers)),
        ))

    recurring_service_instructions = _recurring_service_instructions(
        text, tokens, components, measurements
    )
    recurring_service_instructions.extend(
        _event_recurring_service_instructions(text, tokens, components)
    )
    service_instructions = (
        []
        if recurring_service_instructions
        else _direct_service_instructions(text, tokens, components)
    )

    return StatementStructure(
        text=text,
        tokens=tuple(tokens),
        components=tuple(components),
        measurements=tuple(measurements),
        recurring_service_instructions=tuple(recurring_service_instructions),
        service_instructions=tuple(service_instructions),
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
