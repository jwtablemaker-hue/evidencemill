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

    def test_adjacent_component_temperatures_stay_attached(self):
        result = analyze_statement(
            "Reported 100 C controller / 88 C motor temperatures are contextual."
        )
        self.assertEqual(len(result.measurements), 2)
        self.assertEqual(result.measurements[0].component_kind, "controller")
        self.assertEqual(result.measurements[1].component_kind, "motor")

    def test_signed_temperature_preserves_sign(self):
        result = analyze_statement("Operating temperature is -5°C.")
        self.assertEqual(len(result.measurements), 1)
        self.assertEqual(result.measurements[0].value, -5.0)
        self.assertEqual(result.measurements[0].unit, "degC")

    def test_voltage_tolerance_is_one_measurement(self):
        result = analyze_statement("Low voltage protection is 31V +/- 0.5V.")
        self.assertEqual(len(result.measurements), 1)
        measurement = result.measurements[0]
        self.assertEqual(measurement.value, 31.0)
        self.assertEqual(measurement.unit, "V")
        self.assertEqual(measurement.value_kind, "tolerance")
        self.assertEqual(measurement.tolerance, 0.5)

    def test_dimension_triple_is_preserved(self):
        result = analyze_statement("Product dimensions are 1215 x 455 x 1185mm.")
        self.assertEqual(len(result.measurements), 1)
        measurement = result.measurements[0]
        self.assertEqual(measurement.value, (1215.0, 455.0, 1185.0))
        self.assertEqual(measurement.unit, "mm")
        self.assertEqual(measurement.value_kind, "tuple")

    def test_inch_mark_is_unit(self):
        result = analyze_statement('Tyres are 10" tubeless.')
        self.assertEqual(len(result.measurements), 1)
        self.assertEqual((result.measurements[0].value, result.measurements[0].unit), (10.0, "in"))

    def test_decimal_in_multi_measurement_component_does_not_break_attachment(self):
        result = analyze_statement("Battery: 36V 8.0Ah 288Wh.")
        self.assertEqual(len(result.measurements), 3)
        self.assertEqual(
            [item.component_kind for item in result.measurements],
            ["battery", "battery", "battery"],
        )

    def test_distance_unit_is_parsed(self):
        result = analyze_statement("Range is up to 25 km.")
        self.assertEqual(len(result.measurements), 1)
        self.assertEqual(
            (result.measurements[0].value, result.measurements[0].unit),
            (25.0, "km"),
        )


if __name__ == "__main__":
    unittest.main()
