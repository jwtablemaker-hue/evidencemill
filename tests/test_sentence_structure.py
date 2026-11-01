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

    def test_alphanumeric_parameter_does_not_become_duration(self):
        result = analyze_statement("P04 hour/minute contradiction remains unresolved.")
        self.assertEqual(result.measurements, ())

    def test_word_initial_does_not_become_unit(self):
        result = analyze_statement("Mode limits are 6/12 versus 9/15 km/h.")
        self.assertFalse(any(item.unit == "V" for item in result.measurements))

    def test_numeric_range_is_preserved_as_range(self):
        result = analyze_statement("Recommended tire pressure is 29-52 psi.")
        self.assertEqual(len(result.measurements), 1)
        measurement = result.measurements[0]
        self.assertEqual(measurement.value, (29.0, 52.0))
        self.assertEqual(measurement.value_kind, "range")
        self.assertEqual(measurement.unit, "psi")

    def test_qualifier_does_not_cross_clause_boundary(self):
        result = analyze_statement("Maximum speed is 20 km/h, tire pressure is 2-3 bar.")
        pressure = [item for item in result.measurements if item.unit == "bar"][0]
        self.assertNotIn("maximum", pressure.qualifiers)


if __name__ == "__main__":
    unittest.main()
