import unittest

from evidencemill.sentence_structure import analyze_statement


class SentenceStructureTests(unittest.TestCase):
    def test_dual_motor_and_combined_peak(self):
        result = analyze_statement(
            "The scooter uses dual 500 W motors with a combined peak output of 2400 W."
        )
        self.assertEqual(len(result.measurements), 2)

        each_motor, combined_peak = result.measurements
        self.assertEqual(
            (each_motor.value, each_motor.unit, each_motor.component_kind,
             each_motor.scope, each_motor.multiplicity),
            (500.0, "W", "motor", "each", 2),
        )
        self.assertEqual(
            (combined_peak.value, combined_peak.unit, combined_peak.scope),
            (2400.0, "W", "system"),
        )
        self.assertIn("peak", combined_peak.qualifiers)
        self.assertIn("combined", combined_peak.qualifiers)


if __name__ == "__main__":
    unittest.main()
