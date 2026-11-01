from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import statistics
import time
from typing import Iterable

from evidencemill.pipeline import ingest_path
from evidencemill.worker import FactPrepWorker


@dataclass(frozen=True)
class BenchmarkResult:
    paths: tuple[str, ...]
    repeats: int
    documents_per_run: int
    candidates_per_run: int
    ready_per_run: int
    review_per_run: int
    median_seconds: float
    min_seconds: float
    max_seconds: float
    median_candidates_per_second: float

    def to_dict(self) -> dict:
        return asdict(self)


def benchmark_paths(
    paths: Iterable[str | Path],
    *,
    repeats: int = 5,
    ocr: bool = False,
) -> BenchmarkResult:
    path_list = tuple(str(Path(path)) for path in paths)
    if repeats < 1:
        raise ValueError("repeats must be at least 1")

    elapsed_values: list[float] = []
    candidate_count = ready_count = review_count = 0

    for repeat in range(repeats):
        start = time.perf_counter()
        worker = FactPrepWorker()
        candidates = ready = review = 0
        for path in path_list:
            document = ingest_path(path, ocr=ocr)
            result = worker.run_document(document)
            candidates += result.report.candidate_count
            ready += result.report.ready_count
            review += result.report.review_count
        elapsed = time.perf_counter() - start
        elapsed_values.append(elapsed)
        if repeat == 0:
            candidate_count = candidates
            ready_count = ready
            review_count = review

    median_seconds = statistics.median(elapsed_values)
    rate = candidate_count / median_seconds if median_seconds else float("inf")
    return BenchmarkResult(
        paths=path_list,
        repeats=repeats,
        documents_per_run=len(path_list),
        candidates_per_run=candidate_count,
        ready_per_run=ready_count,
        review_per_run=review_count,
        median_seconds=median_seconds,
        min_seconds=min(elapsed_values),
        max_seconds=max(elapsed_values),
        median_candidates_per_second=rate,
    )
