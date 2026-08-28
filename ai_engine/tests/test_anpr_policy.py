import unittest
from anpr_policy import TrackANPRState, PlateObservation, normalize_indian_plate, plate_is_valid, quality_score, should_run_ocr

class ANPRPolicyTests(unittest.TestCase):
    def test_normalization_and_validation(self):
        self.assertEqual(normalize_indian_plate(" gj 01 ab 1234 "), "GJ01AB1234")
        self.assertTrue(plate_is_valid("GJ01AB1234"))
        self.assertFalse(plate_is_valid("GJ01AB123"))

    def test_consensus_requires_repeated_exact_evidence(self):
        state = TrackANPRState()
        state.add(PlateObservation("GJ01AB1234", .9, .9, .9, True, 1.0))
        self.assertIsNone(state.consensus(2)[0])
        state.add(PlateObservation("GJ01AB1234", .95, .9, .95, True, 2.0))
        plate, score = state.consensus(2)
        self.assertEqual(plate, "GJ01AB1234")
        self.assertGreater(score, 0)

    def test_conflicting_plate_is_not_merged_by_edit_distance(self):
        state = TrackANPRState()
        state.add(PlateObservation("GJ01AB1234", .99, .95, .95, True, 1.0))
        state.add(PlateObservation("GJ01AB1238", .99, .95, .95, True, 2.0))
        self.assertIsNone(state.consensus(2)[0])

    def test_invalid_observation_does_not_confirm(self):
        state = TrackANPRState()
        state.add(PlateObservation("NOTAPLATE", .99, .99, .99, False, 1.0))
        self.assertIsNone(state.consensus(2)[0])

    def test_quality_gate_is_bounded(self):
        self.assertEqual(quality_score(0, 0), 0.0)
        self.assertGreaterEqual(quality_score(100, 40), 0.0)
        self.assertLessEqual(quality_score(4000, 2000), 1.0)

    def test_ocr_is_rate_limited_until_confirmation(self):
        state = TrackANPRState()
        self.assertTrue(should_run_ocr(state, 1.0, .8))
        state.last_ocr_at = 1.0
        self.assertFalse(should_run_ocr(state, 1.5, .8))
        self.assertTrue(should_run_ocr(state, 1.81, .8))
        state.confirmed_plate = "GJ01AB1234"
        self.assertFalse(should_run_ocr(state, 10, .8))

if __name__ == "__main__":
    unittest.main()
