import unittest
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from analysis import AnalysisError, decode_image
from app import app, demo_image
from auto_calibration import auto_analyze, fit_ticks


class AutoTests(unittest.TestCase):
    def test_actual_experiment_needs_no_calibration_arguments(self):
        image = decode_image((Path(__file__).parents[1] / "examples" / "experiment.jpg").read_bytes())
        r = auto_analyze(image)
        self.assertEqual(r["summary"]["cycle_count"], 3)
        self.assertAlmostEqual(r["standard"]["period"], 1.35545, delta=.02)
        self.assertAlmostEqual(r["standard"]["amplitude"], 1.11745, delta=.03)
        self.assertGreaterEqual(len(r["automatic"]["x_ticks"]), 8)
        self.assertGreaterEqual(len(r["automatic"]["y_ticks"]), 4)

    def test_resized_picture_keeps_physical_units(self):
        image = decode_image((Path(__file__).parents[1] / "examples" / "experiment.jpg").read_bytes())
        image = cv2.resize(image, None, fx=1.5, fy=1.5)
        r = auto_analyze(image)
        self.assertAlmostEqual(r["standard"]["period"], 1.35545, delta=.025)
        self.assertAlmostEqual(r["standard"]["amplitude"], 1.11745, delta=.03)

    def test_modified_time_labels_change_recovered_period(self):
        image = demo_image(0)
        image[545:] = 255
        for tick in range(11):
            cv2.putText(image, str(tick * 2), (74 + tick * 100, 565), cv2.FONT_HERSHEY_SIMPLEX, .55, (65, 65, 65), 1)
        r = auto_analyze(image)
        self.assertAlmostEqual(r["standard"]["period"], 4, delta=.06)
        self.assertAlmostEqual(r["standard"]["amplitude"], 1, delta=.03)

    def test_blank_and_missing_axis_labels_fail_instead_of_guessing(self):
        with self.assertRaises(AnalysisError):
            auto_analyze(np.full((400, 700, 3), 255, np.uint8))
        image = demo_image(0)
        image[:, :70] = 255
        with self.assertRaisesRegex(AnalysisError, "刻度"):
            auto_analyze(image)

    def test_nonlinear_tick_numbers_rejected(self):
        records = [{"x": i * 100., "y": 300., "text": str(value), "value": value, "confidence": .99}
                   for i, value in enumerate([1, 10, 100, 1000])]
        with self.assertRaisesRegex(AnalysisError, "线性"):
            fit_ticks(records, "x", np.array([]), 300)

    def test_a_misread_tick_is_excluded_by_consistency_check(self):
        records = [{"x": i * 100., "y": 300., "text": str(value), "value": value, "confidence": .99}
                   for i, value in enumerate([0, 1, 8, 3, 4])]
        slope, _, used, _ = fit_ticks(records, "x", np.array([]), 400)
        self.assertAlmostEqual(slope, .01)
        self.assertEqual(len(used), 4)

    def test_auto_api_accepts_only_the_image(self):
        client = TestClient(app)
        image = client.get("/api/demo.png").content
        r = client.post("/api/auto-analyze", files={"file": ("demo.png", image, "image/png")})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["summary"]["cycle_count"], 4)
        self.assertIn("automatic", r.json())


if __name__ == "__main__":
    unittest.main()
