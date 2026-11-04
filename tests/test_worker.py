import unittest

from evidencemill.ingest.text import parse_text
from evidencemill.models import EvidenceObservation, SourceRef
from evidencemill.worker import READY, REVIEW, EVIDENCE_ONLY, FactPrepWorker, observation_to_candidate


class FactPrepWorkerTests(unittest.TestCase):
    def test_cleaning_guidance_is_searchable_evidence_without_review(self):
        text = "If you see stains on the scooter's body, wipe them off with a damp cloth."
        result = FactPrepWorker().run_document(parse_text(text, source_id="hiboy-es1"))
        statements = [c for c in result.candidates if c.observation_kind == "statement"]
        self.assertEqual(len(statements), 1)
        candidate = statements[0]
        self.assertEqual(candidate.readiness, EVIDENCE_ONLY)
        self.assertEqual(candidate.context["evidence_route"], "searchable_guidance")
        self.assertEqual(candidate.review_reasons, ())
        self.assertIn("wipe them off", candidate.source.raw_text)

    def test_mixed_cleaning_and_technical_content_remains_reviewable(self):
        text = "Clean the battery terminals and measure 48 V after charging."
        result = FactPrepWorker().run_document(parse_text(text, source_id="manual"))
        statements = [c for c in result.candidates if c.observation_kind == "statement"]
        self.assertTrue(statements)
        self.assertTrue(all(c.readiness == REVIEW for c in statements))
        self.assertTrue(any(c.observation_kind == "measurement" for c in result.candidates))

    def test_table_cell_is_ready_when_context_is_explicit(self):
        observation = EvidenceObservation(
            kind="table_cell",
            source=SourceRef("manual", "table-1:r2c2", "500"),
            value="500",
            unit="W",
            subject_hint="Base",
            property_hint="Rated power",
            context={"row_index": 1, "column_index": 1},
        )
        candidate = observation_to_candidate(observation)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.readiness, READY)
        self.assertEqual(candidate.subject_hint, "Base")
        self.assertEqual(candidate.predicate_hint, "rated.power")
        self.assertEqual(candidate.confidence, 0.98)

    def test_peak_motor_power_is_ready(self):
        observation = EvidenceObservation(
            kind="measurement",
            source=SourceRef("manual", "text-1:s1:m1", "2400 W"),
            value=2400.0,
            unit="W",
            subject_hint=None,
            qualifiers=("combined", "peak"),
            context={"scope": "system", "placement": None, "multiplicity": 2},
        )
        candidate = observation_to_candidate(observation)
        self.assertEqual(candidate.readiness, READY)
        self.assertEqual(candidate.predicate_hint, "peak.power")
        self.assertEqual(candidate.subject_hint, "system")

    def test_unrated_motor_power_is_review_not_guess(self):
        observation = EvidenceObservation(
            kind="measurement",
            source=SourceRef("manual", "text-1:s1:m1", "500 W"),
            value=500.0,
            unit="W",
            subject_hint="motor",
            context={"scope": "each", "placement": None, "multiplicity": 2},
        )
        candidate = observation_to_candidate(observation)
        self.assertEqual(candidate.readiness, REVIEW)
        self.assertEqual(candidate.review_reason, "power_rating_unspecified")

    def test_worker_report_counts_only_fact_candidates(self):
        observations = [
            EvidenceObservation(
                kind="heading",
                source=SourceRef("manual", "h1", "Specs"),
                value="Specs",
            ),
            EvidenceObservation(
                kind="table_cell",
                source=SourceRef("manual", "t1:r2c2", "48"),
                value="48",
                unit="V",
                subject_hint="Model A",
                property_hint="Battery voltage",
            ),
        ]
        result = FactPrepWorker().run_observations(observations, source_id="manual")
        self.assertEqual(result.report.observation_count, 2)
        self.assertEqual(result.report.candidate_count, 1)
        self.assertEqual(result.report.ready_count, 1)
        self.assertEqual(result.report.evidence_only_count, 1)


    def test_recurring_recharge_statement_is_preserved_and_scalar_is_held(self):
        sentence = (
            "Keep in mind to recharge it every 60 days to protect the battery "
            "from potential damage which is beyond limited warranty."
        )
        result = FactPrepWorker().run_document(parse_text(sentence, source_id="hiboy-es1"))
        statement = next(
            item for item in result.candidates
            if item.observation_kind == "statement"
        )
        interval = next(
            item for item in result.candidates
            if item.observation_kind == "measurement" and item.unit == "day"
        )

        instruction = statement.conditions["recurring_service_instruction"]
        self.assertEqual(instruction["action"], "recharge")
        self.assertEqual(instruction["target_component_kind"], "battery")
        self.assertEqual(instruction["recurrence_marker"], "every")
        self.assertEqual(instruction["recurrence_value"], 60.0)
        self.assertEqual(instruction["recurrence_unit"], "day")
        self.assertEqual(statement.subject_hint, "battery")

        self.assertEqual(interval.predicate_hint, "duration")
        self.assertEqual(interval.readiness, REVIEW)
        self.assertIn(
            "recurring_service_instruction_requires_interpretation",
            interval.review_reasons,
        )
        self.assertEqual(
            interval.conditions["recurring_service_instruction"]["action"],
            "recharge",
        )


    def test_after_every_use_becomes_battery_service_statement(self):
        sentence = "After every use, fully charge the battery to prolong its lifespan."
        result = FactPrepWorker().run_document(parse_text(sentence, source_id="hiboy-es1"))
        statement = next(
            item for item in result.candidates
            if item.observation_kind == "statement"
        )
        instruction = statement.conditions["recurring_service_instruction"]
        self.assertEqual(statement.subject_hint, "battery")
        self.assertEqual(instruction["action"], "charge")
        self.assertEqual(instruction["target_component_kind"], "battery")
        self.assertEqual(instruction["recurrence_event"], "use")
        self.assertEqual(instruction["recurrence_relation"], "after")
        self.assertIsNone(instruction["recurrence_value"])
        self.assertIsNone(instruction["recurrence_unit"])


    def test_before_every_use_becomes_machine_service_statement(self):
        sentence = "Check the scooter before every use."
        result = FactPrepWorker().run_document(parse_text(sentence, source_id="hiboy-es1"))
        statement = next(
            item for item in result.candidates
            if item.observation_kind == "statement"
        )
        instruction = statement.conditions["recurring_service_instruction"]
        self.assertEqual(statement.subject_hint, "machine")
        self.assertEqual(instruction["action"], "check")
        self.assertTrue(instruction["target_machine"])
        self.assertIsNone(instruction["target_component_kind"])
        self.assertEqual(instruction["recurrence_event"], "use")
        self.assertEqual(instruction["recurrence_relation"], "before")


    def test_direct_service_instruction_survives_worker_handoff(self):
        sentence = "Do not connect the charger if the charging port is wet."
        result = FactPrepWorker().run_document(parse_text(sentence, source_id="hiboy-es1"))
        statement = next(
            item for item in result.candidates
            if item.observation_kind == "statement"
        )
        instruction = statement.conditions["service_instruction"]
        self.assertEqual(instruction["actions"], ("connect",))
        self.assertTrue(instruction["negated"])
        self.assertEqual(
            tuple(instruction["mentioned_component_kinds"]),
            ("charger", "port"),
        )
        self.assertEqual(
            statement.conditions["source_clause"],
            "not connect the charger if the charging port is wet.",
        )

    def test_direct_machine_instruction_carries_machine_hint(self):
        sentence = "Do not wash the scooter with a high-pressure water spray."
        result = FactPrepWorker().run_document(parse_text(sentence, source_id="hiboy-es1"))
        statement = next(
            item for item in result.candidates
            if item.observation_kind == "statement"
        )
        self.assertEqual(statement.subject_hint, "machine")
        self.assertTrue(statement.conditions["service_instruction"]["target_machine"])


if __name__ == "__main__":
    unittest.main()
