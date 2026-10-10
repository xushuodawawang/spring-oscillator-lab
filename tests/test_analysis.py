"""独立的合成波形真值验证：python -m unittest discover -s tests -v。"""
import json
import unittest

import cv2
import numpy as np
from fastapi.testclient import TestClient

from analysis import AnalysisError, Settings, analyze, mapping, transform
from app import app, demo_image, demo_settings


def config(**changes):
    values = {k: v for k, v in demo_settings().items() if k != "truth"}
    values.update(changes)
    return Settings(**values)


class PhysicsTests(unittest.TestCase):
    def test_ideal_recovers_known_amplitude_period_phase(self):
        r = analyze(demo_image(0), config())
        self.assertEqual(len(r["cycles"]), 4)
        self.assertAlmostEqual(r["standard"]["amplitude"], 1, delta=.015)
        self.assertAlmostEqual(r["standard"]["period"], 2, delta=.035)
        self.assertAlmostEqual(r["standard"]["phase"], .25, delta=.08)
        self.assertLess(r["metrics"]["all_observed"]["rmse"], .04)
        self.assertGreater(r["metrics"]["all_observed"]["r2"], .995)

    def test_damping_is_reported_not_fitted_away(self):
        r = analyze(demo_image(), config())
        first = r["cycles"][0]
        for c in r["cycles"]:
            ratio = np.exp(-.045 * (c["start"] - first["start"]))
            self.assertAlmostEqual(c["amplitude"] / first["amplitude"], ratio, delta=.02)
        self.assertGreater(r["metrics"]["all_observed"]["rmse"], r["metrics"]["first_cycle"]["rmse"] * 3)
        self.assertGreater(r["summary"]["last_amplitude_decay_pct"], 20)

    def test_rotation_and_shear_are_rectified_before_column_scan(self):
        affine = np.array([[.94, -.12, 150], [.12, .94, 80]], float)
        h = np.vstack((affine, [0, 0, 1]))
        image = cv2.warpAffine(demo_image(0), affine, (1400, 900), borderValue=(255, 255, 255))
        changes = {k: dict(zip(("x", "y"), transform([[getattr(config(), k).x, getattr(config(), k).y]], h)[0]))
                   for k in ("origin", "x_point", "y_point")}
        r = analyze(image, config(roi=None, **changes))
        self.assertAlmostEqual(r["standard"]["period"], 2, delta=.04)
        self.assertAlmostEqual(r["standard"]["amplitude"], 1, delta=.03)
        self.assertGreater(r["metrics"]["all_observed"]["r2"], .99)

    def test_four_point_perspective_correction(self):
        src = np.float32([[0, 0], [1099, 0], [1099, 599], [0, 599]])
        dst = np.float32([[80, 40], [1200, 85], [1050, 740], [50, 650]])
        h = cv2.getPerspectiveTransform(src, dst)
        image = cv2.warpPerspective(demo_image(0), h, (1260, 780), borderValue=(255, 255, 255))
        coords = {"origin": [80, 300], "x_point": [580, 300], "y_point": [80, 120], "fourth_point": [580, 120]}
        changes = {k: dict(zip(("x", "y"), transform([v], h)[0])) for k, v in coords.items()}
        r = analyze(image, config(roi=None, **changes))
        self.assertEqual(r["calibration"]["mode"], "perspective")
        self.assertAlmostEqual(r["standard"]["period"], 2, delta=.05)
        self.assertAlmostEqual(r["standard"]["amplitude"], 1, delta=.03)
        self.assertGreater(r["metrics"]["all_observed"]["r2"], .99)

    def test_long_missing_interval_never_becomes_a_cycle(self):
        image = demo_image(0)
        image[:, 500:560] = 255
        r = analyze(image, config())
        self.assertFalse(any(c["start"] < 4.2 and c["end"] > 4.8 for c in r["cycles"]))
        self.assertTrue(any("长缺口" in w for w in r["warnings"]))

    def test_short_gaps_do_not_enter_error_metrics(self):
        image = demo_image(0)
        image[:, 600:603] = 255
        r = analyze(image, config())
        self.assertTrue(any(c["interpolated_points"] > 0 for c in r["cycles"]))
        self.assertEqual(r["metrics"]["all_observed"]["n"], sum(v is not None for v in r["data"]["residual"]))
        self.assertTrue(all(res is None for obs, res in zip(r["data"]["observed"], r["data"]["residual"]) if not obs))

    def test_clipped_extrema_are_rejected(self):
        with self.assertRaisesRegex(AnalysisError, "完整周期"):
            analyze(demo_image(0), config(roi=[82, 200, 1078, 400]))

    def test_cropped_picture_can_use_nonzero_known_intersection(self):
        image = demo_image(0)[:, 280:]
        # 裁掉 t=0 后，在 t=3 秒处建立已知交点，不能把它冒充 t=0。
        cfg = config(origin={"x": 100, "y": 300}, x_point={"x": 400, "y": 300},
                     y_point={"x": 100, "y": 120}, t0=3, x_value=6,
                     roi=[0, 65, 798, 535])
        r = analyze(image, cfg)
        self.assertGreater(r["data"]["t"][0], 1.99)
        self.assertAlmostEqual(r["standard"]["period"], 2, delta=.04)

    def test_collinear_calibration_rejected(self):
        with self.assertRaisesRegex(AnalysisError, "共线"):
            mapping(config(y_point={"x": 180, "y": 300}), 1100, 600)

    def test_empty_mask_reports_actionable_failure(self):
        with self.assertRaisesRegex(AnalysisError, "像素不足"):
            analyze(np.full((600, 1100, 3), 255, np.uint8), config())


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_home_and_demo_end_to_end(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        image = self.client.get("/api/demo.png")
        response = self.client.post("/api/analyze", files={"file": ("demo.png", image.content, "image/png")},
            data={"settings": config().model_dump_json()})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["summary"]["cycle_count"], 4)
        json.dumps(response.json(), allow_nan=False)

    def test_bad_settings_and_invalid_images_return_422(self):
        response = self.client.post("/api/analyze", files={"file": ("bad.png", b"invalid")}, data={"settings": "{}"})
        self.assertEqual(response.status_code, 422)
        response = self.client.post("/api/analyze", files={"file": ("bad.png", b"invalid")}, data={"settings": config().model_dump_json()})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
