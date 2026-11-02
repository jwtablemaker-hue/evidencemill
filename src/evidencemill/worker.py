from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
import time
from typing import Any, Callable, Iterable, Protocol

from evidencemill.document import Document
from evidencemill.models import EvidenceObservation, SourceRef
from evidencemill.pipeline import process_document
from evidencemill.sentence_structure import analyze_statement


READY = "READY"
REVIEW = "REVIEW"
EVIDENCE_ONLY = "EVIDENCE_ONLY"


_UNIT_QUANTITIES = {
    "W": "power",
    "kW": "power",
    "V": "voltage",
    "A": "current",
    "Wh": "energy",
    "Ah": "capacity",
    "kmh": "speed",
    "mph": "speed",
    "km": "length",
    "mi": "length",
    "m": "length",
    "ft": "length",
    "kg": "mass",
    "lb": "mass",
    "mm": "length",
    "cm": "length",
    "in": "length",
    "h": "duration",
    "min": "duration",
    "percent": "percentage",
    "deg": "angle",
    "kPa": "pressure",
    "psi": "pressure",
    "bar": "pressure",
    "degC": "temperature",
    "degF": "temperature",
    "s": "duration",
    "day": "duration",
    "week": "duration",
    "month": "duration",
    "year": "duration",
}

_GENERIC_HEADINGS = {
    "specification",
    "specifications",
    "technical specifications",
    "parameter",
    "parameters",
    "specs",
    "overview",
    "features",
}


class SemanticResolver(Protocol):
    def __call__(self, candidate: "FactCandidate") -> "FactCandidate":
        ...


@dataclass(frozen=True)
class FactCandidate:
    candidate_id: str
    source: SourceRef
    observation_kind: str
    subject_hint: str | None
    predicate_hint: str | None
    value: Any
    unit: str | None = None
    qualifiers: tuple[str, ...] = ()
    conditions: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    readiness: str = REVIEW
    review_reason: str | None = None
    review_reasons: tuple[str, ...] = ()
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source"] = asdict(self.source)
        return payload


@dataclass(frozen=True)
class WorkerReport:
    source_id: str
    observation_count: int
    candidate_count: int
    ready_count: int
    review_count: int
    evidence_only_count: int
    elapsed_seconds: float

    @property
    def candidates_per_second(self) -> float:
        if self.elapsed_seconds <= 0:
            return float("inf")
        return self.candidate_count / self.elapsed_seconds

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates_per_second"] = self.candidates_per_second
        return payload


@dataclass(frozen=True)
class WorkerResult:
    candidates: tuple[FactCandidate, ...]
    report: WorkerReport


def _slug(value: str | None) -> str | None:
    if not value:
        return None
    parts = [
        part
        for part in re.split(r"[^a-z0-9]+", value.casefold())
        if part
    ]
    aliases = {
        "max": "maximum",
        "min": "minimum",
        "temp": "temperature",
    }
    text = ".".join(aliases.get(part, part) for part in parts)
    return text or None


def _stable_id(
    source: SourceRef,
    observation_kind: str,
    subject_hint: str | None,
    predicate_hint: str | None,
    value: Any,
    unit: str | None,
) -> str:
    payload = json.dumps(
        {
            "source_id": source.source_id,
            "location": source.location,
            "kind": observation_kind,
            "subject": subject_hint,
            "predicate": predicate_hint,
            "value": value,
            "unit": unit,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return "emfc-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _meaningful_heading(context: dict[str, Any]) -> str | None:
    path = context.get("heading_path")
    if not isinstance(path, list):
        return None
    for item in reversed(path):
        text = str(item).strip()
        if text and text.casefold() not in _GENERIC_HEADINGS:
            return text
    return None


def _measurement_predicate(observation: EvidenceObservation, resolved_subject: str | None = None) -> tuple[str | None, str | None]:
    quantity = _UNIT_QUANTITIES.get(observation.unit or "")
    if quantity is None:
        return None, "unit_has_no_generic_quantity"

    explicit_property = _slug(
        observation.property_hint
        or observation.context.get("table_property")
    )
    subject_slug = _slug(resolved_subject or observation.subject_hint)

    if explicit_property and subject_slug:
        if explicit_property == subject_slug:
            explicit_property = None
        elif explicit_property.startswith(subject_slug + "."):
            explicit_property = explicit_property[len(subject_slug) + 1:] or None

    qualifiers = {str(q).casefold() for q in observation.qualifiers}
    prefix = None
    if "peak" in qualifiers:
        prefix = "peak"
    elif "maximum" in qualifiers:
        prefix = "peak" if quantity == "power" else "maximum"
    elif "minimum" in qualifiers:
        prefix = "minimum"
    elif "rated" in qualifiers:
        prefix = "rated"
    elif "nominal" in qualifiers:
        prefix = "nominal"

    if explicit_property:
        predicate = (
            ".".join((prefix, quantity))
            if prefix and explicit_property == quantity
            else explicit_property
        )
        terminal = predicate.split(".")[-1]
        has_rating_basis = any(
            part in {"rated", "nominal", "peak", "maximum", "output", "input"}
            for part in predicate.split(".")
        )
        if terminal in {"power", "voltage"} and not has_rating_basis:
            return predicate, f"{terminal}_rating_unspecified"
        return predicate, None

    predicate = ".".join(part for part in (prefix, quantity) if part)

    if quantity in {"power", "voltage"} and prefix is None:
        return predicate, f"{quantity}_rating_unspecified"
    if quantity == "angle":
        return predicate, "angle_semantics_unspecified"
    return predicate, None


def _candidate_from_table(observation: EvidenceObservation) -> FactCandidate:
    subject = observation.subject_hint
    context = dict(observation.context)

    if subject is None:
        hint_text = " ".join(
            str(item).strip()
            for item in (
                context.get("section_heading"),
                context.get("table_subject"),
                observation.property_hint,
            )
            if item and str(item).strip()
        )
        if hint_text:
            structure = analyze_statement(hint_text)
            kinds = sorted({item.kind for item in structure.components})
            if len(kinds) == 1:
                subject = kinds[0]
                context["table_component_hint"] = subject

    predicate = _slug(observation.property_hint)
    if subject and predicate:
        subject_prefix = _slug(subject)
        if predicate == subject_prefix:
            predicate = None
        elif subject_prefix and predicate.startswith(subject_prefix + "."):
            predicate = predicate[len(subject_prefix) + 1:] or None

    reason = None
    confidence = 0.98

    if not predicate:
        reason = "table_property_missing"
        confidence = 0.45
    elif subject is None:
        reason = "table_subject_missing"
        confidence = 0.70

    readiness = READY if reason is None and not observation.ambiguous else REVIEW
    if observation.ambiguous and reason is None:
        reason = "source_marked_ambiguous"
        confidence = min(confidence, 0.65)

    return FactCandidate(
        candidate_id=_stable_id(
            observation.source,
            observation.kind,
            subject,
            predicate,
            observation.value,
            observation.unit,
        ),
        source=observation.source,
        observation_kind=observation.kind,
        subject_hint=subject,
        predicate_hint=predicate,
        value=observation.value,
        unit=observation.unit,
        qualifiers=tuple(observation.qualifiers),
        conditions={
            "source_caveats": context.get("source_caveats", []),
        } if context.get("source_caveats") else {},
        context=context,
        readiness=readiness,
        review_reason=reason,
        review_reasons=(reason,) if reason else (),
        confidence=confidence,
    )


def _candidate_from_measurement(observation: EvidenceObservation) -> FactCandidate:
    scope = observation.context.get("scope")
    heading_hint = _meaningful_heading(observation.context)
    subject = observation.subject_hint
    table_component_hint = None

    if subject is None:
        property_text = observation.context.get("table_property")
        section_text = observation.context.get("table_section")
        hint_text = " ".join(
            str(item).strip()
            for item in (section_text, property_text)
            if item and str(item).strip()
        )
        if hint_text:
            structure = analyze_statement(hint_text)
            kinds = sorted({item.kind for item in structure.components})
            if len(kinds) == 1:
                table_component_hint = kinds[0]
                subject = table_component_hint
                if scope == "unknown":
                    scope = "component"

    if subject is None and scope == "system":
        subject = "system"

    predicate, predicate_reason = _measurement_predicate(observation, subject)
    confidence = 0.94
    reasons: list[str] = []
    if predicate_reason:
        reasons.append(predicate_reason)

    if subject is None:
        reasons.append(
            "subject_from_heading_requires_confirmation"
            if heading_hint
            else "subject_unresolved"
        )
        confidence -= 0.22
    if predicate is None:
        reasons.append("predicate_unresolved")
        confidence -= 0.25
    if observation.ambiguous:
        reasons.append("source_marked_ambiguous")
        confidence -= 0.15

    if scope == "unknown":
        reasons.append("scope_unresolved")
        confidence -= 0.15

    value_kind = observation.context.get("value_kind", "scalar")
    if value_kind == "alternatives":
        reasons.append("alternative_values_require_applicability")
        confidence -= 0.15
    elif value_kind == "tolerance":
        reasons.append("tolerance_requires_semantic_handling")
        confidence -= 0.10
    elif value_kind == "tuple":
        reasons.append("tuple_axes_require_semantic_handling")
        confidence -= 0.15

    review_reasons = tuple(dict.fromkeys(reasons))
    readiness = READY if not review_reasons else REVIEW

    return FactCandidate(
        candidate_id=_stable_id(
            observation.source,
            observation.kind,
            subject,
            predicate,
            observation.value,
            observation.unit,
        ),
        source=observation.source,
        observation_kind=observation.kind,
        subject_hint=subject,
        predicate_hint=predicate,
        value=observation.value,
        unit=observation.unit,
        qualifiers=tuple(observation.qualifiers),
        conditions={
            "scope": scope,
            "placement": observation.context.get("placement"),
            "multiplicity": observation.context.get("multiplicity"),
            "comparison": observation.context.get("comparison"),
            "local_label": observation.context.get("local_label"),
            "source_caveats": observation.context.get("source_caveats"),
        },
        context={
            **dict(observation.context),
            "heading_subject_hint": heading_hint,
            "table_component_hint": table_component_hint,
        },
        readiness=readiness,
        review_reason=review_reasons[0] if review_reasons else None,
        review_reasons=review_reasons,
        confidence=max(0.0, min(1.0, confidence)),
    )

def _candidate_from_figure_callout(observation: EvidenceObservation) -> FactCandidate:
    reason = None if observation.subject_hint else "callout_target_unresolved"
    return FactCandidate(
        candidate_id=_stable_id(
            observation.source,
            observation.kind,
            observation.subject_hint,
            "diagram.callout",
            observation.value,
            observation.unit,
        ),
        source=observation.source,
        observation_kind=observation.kind,
        subject_hint=observation.subject_hint,
        predicate_hint="diagram.callout",
        value=observation.value,
        context=dict(observation.context),
        readiness=READY if reason is None else REVIEW,
        review_reason=reason,
        review_reasons=(reason,) if reason else (),
        confidence=0.90 if reason is None else 0.55,
    )


def observation_to_candidate(observation: EvidenceObservation) -> FactCandidate | None:
    if observation.kind == "table_cell":
        return _candidate_from_table(observation)
    if observation.kind == "measurement":
        return _candidate_from_measurement(observation)
    if observation.kind == "figure_callout":
        return _candidate_from_figure_callout(observation)
    return None


class FactPrepWorker:
    """Cheap structural worker that prepares evidence-backed fact candidates.

    It deliberately stops before domain-specific truth, identity, or canonical
    schema decisions. A resolver may refine REVIEW candidates at the boundary.
    """

    def __init__(self, resolver: SemanticResolver | None = None):
        self.resolver = resolver

    def run_observations(
        self,
        observations: Iterable[EvidenceObservation],
        *,
        source_id: str,
        elapsed_start: float | None = None,
    ) -> WorkerResult:
        start = elapsed_start if elapsed_start is not None else time.perf_counter()
        observations = tuple(observations)
        candidates: list[FactCandidate] = []

        for observation in observations:
            candidate = observation_to_candidate(observation)
            if candidate is None:
                continue
            if candidate.readiness == REVIEW and self.resolver is not None:
                candidate = self.resolver(candidate)
            candidates.append(candidate)

        elapsed = time.perf_counter() - start
        ready = sum(item.readiness == READY for item in candidates)
        review = sum(item.readiness == REVIEW for item in candidates)
        evidence_only = len(observations) - len(candidates)

        return WorkerResult(
            candidates=tuple(candidates),
            report=WorkerReport(
                source_id=source_id,
                observation_count=len(observations),
                candidate_count=len(candidates),
                ready_count=ready,
                review_count=review,
                evidence_only_count=evidence_only,
                elapsed_seconds=elapsed,
            ),
        )

    def run_document(self, document: Document) -> WorkerResult:
        start = time.perf_counter()
        observations = process_document(document)
        return self.run_observations(
            observations,
            source_id=document.source_id,
            elapsed_start=start,
        )


def run_documents(
    documents: Iterable[Document],
    *,
    resolver: SemanticResolver | None = None,
) -> tuple[WorkerResult, ...]:
    worker = FactPrepWorker(resolver=resolver)
    return tuple(worker.run_document(document) for document in documents)
