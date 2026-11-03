import unittest
from evidencemill.document import Document, TableBlock
from evidencemill.ingest.text import parse_text
from evidencemill.worker import FactPrepWorker, REVIEW

class SemanticHandoffTests(unittest.TestCase):
    def candidates(self, text):
        return FactPrepWorker().run_document(parse_text(text, source_id='fixture')).candidates

    def test_manual_a(self):
        cs=self.candidates('# Drive\nThe scooter uses dual 500 W motors with a combined peak output of 2400 W.\n# Battery\nThe battery is rated at 48 V and 15 Ah.')
        ms=[c for c in cs if c.observation_kind=='measurement']
        self.assertEqual([(c.value,c.subject_hint) for c in ms],[(500,'motor'),(2400,'system'),(48,'battery'),(15,'battery')])
        self.assertEqual(ms[0].conditions['multiplicity'],2)
        self.assertEqual(ms[0].conditions['scope'],'each')
        self.assertIn('power_rating_unspecified',ms[0].review_reasons)
        self.assertEqual(ms[1].predicate_hint,'peak.power')
        self.assertEqual(ms[1].conditions['scope'],'system')
        self.assertEqual(len([c for c in cs if c.observation_kind=='statement']),2)

    def test_manual_b(self):
        doc=Document('b',(TableBlock((('Component','Rated power (W)','Peak power (W)'),('Motor','500','1200'),('Charger','100','150')),'t'),))
        ms=[c for c in FactPrepWorker().run_document(doc).candidates if c.observation_kind=='measurement']
        self.assertEqual([(c.subject_hint,c.predicate_hint,c.value) for c in ms],[('motor','rated.power',500),('motor','peak.power',1200),('charger','rated.power',100),('charger','peak.power',150)])

    def test_manual_c(self):
        cs=self.candidates('# Drive\nThe motor is rated at 600 W. The motor is rated at 500 W according to an older manual.\n# Conditions\nMaximum speed is 25 mph under ideal conditions.')
        ms=[c for c in cs if c.observation_kind=='measurement']
        self.assertEqual([c.value for c in ms],[600,500,25])
        self.assertNotIn('source_clause',ms[0].conditions)
        self.assertEqual(ms[1].conditions['source_clause'],'according to an older manual.')
        self.assertEqual(ms[2].conditions['source_clause'],'under ideal conditions.')
        self.assertEqual(ms[1].readiness,REVIEW)
        self.assertEqual(ms[2].readiness,REVIEW)
        self.assertEqual(len({c.candidate_id for c in cs}),len(cs))

    def test_behavior_and_negation_are_not_discarded(self):
        text='After leaving the scooter for 10 seconds, the scooter will automatically shut down. Do not charge the battery when wet.'
        cs=self.candidates(text)
        statements=[c for c in cs if c.observation_kind=='statement']
        self.assertEqual(len(statements),2)
        self.assertTrue(all(c.readiness==REVIEW for c in statements))
        self.assertEqual(statements[1].source.raw_text,'Do not charge the battery when wet.')
        measurement=next(c for c in cs if c.observation_kind=='measurement')
        self.assertIn('statement_modifier_requires_interpretation',measurement.review_reasons)

    def test_coordination_does_not_cross_subject_or_clause(self):
        for text in ['The battery is rated at 48 V. Capacity is 15 Ah.', 'The battery is rated at 48 V and the controller uses 15 A.']:
            ms=[c for c in self.candidates(text) if c.observation_kind=='measurement']
            self.assertNotEqual(ms[-1].subject_hint,'battery')

    def test_minimum_is_not_lost(self):
        ms=[c for c in self.candidates('Minimum battery temperature is -10 °C.') if c.observation_kind=='measurement']
        self.assertIn('minimum',ms[0].qualifiers)
