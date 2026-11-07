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

    def test_value_suffix_multiplier_marks_each_repeated_component(self):
        for text in (
            "Motor nominal power: 2500W*2.",
            "Motor nominal power: 2500 W × 2.",
            "Motor nominal power: 2500 W x2.",
        ):
            with self.subTest(text=text):
                result = analyze_statement(text)
                self.assertEqual(len(result.measurements), 1)
                measurement = result.measurements[0]
                self.assertEqual(measurement.value, 2500.0)
                self.assertEqual(measurement.unit, "W")
                self.assertEqual(measurement.component_kind, "motor")
                self.assertEqual(measurement.scope, "each")
                self.assertEqual(measurement.multiplicity, 2)
                self.assertTrue(measurement.text.endswith((" *2", "*2", " × 2", " x2")))

    def test_unmultiplied_component_value_keeps_single_occurrence_unspecified(self):
        result = analyze_statement("Motor nominal power: 2500W.")
        measurement = result.measurements[0]
        self.assertEqual(measurement.scope, "component")
        self.assertIsNone(measurement.multiplicity)

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


    def test_up_to_and_approximate_qualifiers(self):
        upper = analyze_statement("Range is up to 25 km.")
        self.assertIn("maximum", upper.measurements[0].qualifiers)
        self.assertIn("up_to", upper.measurements[0].qualifiers)

        approximate = analyze_statement("Charging time is around 6 h.")
        self.assertIn("approximate", approximate.measurements[0].qualifiers)



    def test_approximate_abbreviation_without_space_keeps_measurement(self):
        for text, value in (
            ("Wheelbase: Approx.970mm", 970.0),
            ("Ground Clearance: Approx.180mm", 180.0),
            ("Wheelbase: Approximately.970mm", 970.0),
        ):
            with self.subTest(text=text):
                result = analyze_statement(text)
                self.assertEqual(len(result.measurements), 1)
                measurement = result.measurements[0]
                self.assertEqual((measurement.value, measurement.unit), (value, "mm"))
                self.assertIn("approximate", measurement.qualifiers)

    def test_mode_labels_and_upper_bounds_are_preserved(self):
        result = analyze_statement(
            "Speed: L1: <= 6km/h | L2: <= 20km/h | L3: <= 25km/h"
        )
        self.assertEqual(
            [item.value for item in result.measurements],
            [6.0, 20.0, 25.0],
        )
        self.assertEqual(
            [item.local_label for item in result.measurements],
            ["L1", "L2", "L3"],
        )
        self.assertEqual(
            [item.comparison for item in result.measurements],
            ["<=", "<=", "<="],
        )
        self.assertTrue(
            all(
                "upper_bound" in item.qualifiers
                and "maximum" in item.qualifiers
                for item in result.measurements
            )
        )



    def test_ordinary_property_label_is_not_local_label(self):
        result = analyze_statement("Max gradient: 16%")
        self.assertEqual(len(result.measurements), 1)
        self.assertIsNone(result.measurements[0].local_label)

        motor = analyze_statement("Motor: 350W")
        self.assertIsNone(motor.measurements[0].local_label)

    def test_nested_and_delimited_labels_still_work(self):
        result = analyze_statement(
            "Speed: L1: <= 6km/h | L2: <= 20km/h"
        )
        self.assertEqual(
            [item.local_label for item in result.measurements],
            ["L1", "L2"],
        )



    def test_sentence_boundary_stops_qualifier_leakage(self):
        result = analyze_statement(
            "Maximum speed is 20 km/h. Tire pressure is 2 bar."
        )
        pressure = [item for item in result.measurements if item.unit == "bar"][0]
        self.assertNotIn("maximum", pressure.qualifiers)

    def test_recurring_recharge_retains_action_target_and_interval(self):
        result = analyze_statement(
            "Keep in mind to recharge it every 60 days to protect the battery from potential damage."
        )
        self.assertEqual(len(result.recurring_service_instructions), 1)
        instruction = result.recurring_service_instructions[0]
        self.assertEqual(instruction.action, "recharge")
        self.assertEqual(instruction.action_text, "recharge it every 60 days")
        self.assertEqual(instruction.target_component_kind, "battery")
        self.assertEqual(instruction.recurrence_marker, "every")
        self.assertEqual(instruction.recurrence_value, 60.0)
        self.assertEqual(instruction.recurrence_unit, "day")

    def test_charge_duration_is_not_a_recurring_instruction(self):
        result = analyze_statement("Charge the battery for 60 minutes.")
        self.assertEqual(result.recurring_service_instructions, ())

    def test_recurrence_without_target_does_not_invent_component(self):
        result = analyze_statement("Inspect every 60 days.")
        self.assertEqual(len(result.recurring_service_instructions), 1)
        instruction = result.recurring_service_instructions[0]
        self.assertEqual(instruction.action, "inspect")
        self.assertIsNone(instruction.target_component_kind)
        self.assertFalse(instruction.target_machine)


    def test_after_every_use_retains_event_recurrence_and_battery_target(self):
        result = analyze_statement(
            "After every use, fully charge the battery to prolong its lifespan."
        )
        self.assertEqual(len(result.recurring_service_instructions), 1)
        instruction = result.recurring_service_instructions[0]
        self.assertEqual(instruction.action, "charge")
        self.assertEqual(instruction.target_component_kind, "battery")
        self.assertEqual(instruction.recurrence_marker, "every")
        self.assertEqual(instruction.recurrence_event, "use")
        self.assertEqual(instruction.recurrence_relation, "after")
        self.assertIsNone(instruction.recurrence_value)
        self.assertIsNone(instruction.recurrence_unit)

    def test_before_every_use_retains_explicit_machine_target(self):
        result = analyze_statement("Check the scooter before every use.")
        self.assertEqual(len(result.recurring_service_instructions), 1)
        instruction = result.recurring_service_instructions[0]
        self.assertEqual(instruction.action, "check")
        self.assertEqual(instruction.recurrence_event, "use")
        self.assertEqual(instruction.recurrence_relation, "before")
        self.assertIsNone(instruction.target_component_kind)
        self.assertTrue(instruction.target_machine)

    def test_event_without_every_is_not_recurring(self):
        result = analyze_statement("Charge the battery after use.")
        self.assertEqual(result.recurring_service_instructions, ())


    def test_direct_charging_steps_retain_actions_without_recurrence(self):
        samples = (
            ("Open the rubber cover", ("open",), False),
            ("Insert the charger plug in", ("insert",), False),
            ("Fill and fix the rubber plug after the charging", ("fill", "fix"), False),
            ("Do not connect the charger if the charging port is wet.", ("connect",), True),
            ("Always charge before exhausting the battery to prolong the battery's lifespan.", ("charge",), False),
        )
        for text, actions, negated in samples:
            with self.subTest(text=text):
                result = analyze_statement(text)
                self.assertEqual(len(result.service_instructions), 1)
                instruction = result.service_instructions[0]
                self.assertEqual(instruction.actions, actions)
                self.assertEqual(instruction.negated, negated)
                self.assertEqual(instruction.action_text, text)

    def test_direct_instruction_preserves_mentions_without_claiming_target(self):
        result = analyze_statement(
            "Do not connect the charger if the charging port is wet."
        )
        instruction = result.service_instructions[0]
        self.assertEqual(
            instruction.mentioned_component_kinds,
            ("charger", "port"),
        )
        self.assertFalse(instruction.target_machine)

    def test_declarative_charging_statement_is_not_promoted_to_instruction(self):
        result = analyze_statement(
            "Your scooter will be fully charged when the LED light changes to green."
        )
        self.assertEqual(result.service_instructions, ())

    def test_recurring_instruction_is_not_duplicated_as_direct_instruction(self):
        result = analyze_statement("Check the scooter before every use.")
        self.assertEqual(len(result.recurring_service_instructions), 1)
        self.assertEqual(result.service_instructions, ())


if __name__ == "__main__":
    unittest.main()
