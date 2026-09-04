import base64
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from backend.app.config import Settings
from backend.app.face_engine import FaceEngine, decode_base64_image, decode_image_bytes


class _FakeFaceAnalysis:
    created = 0

    def __init__(self, *args, **kwargs):
        type(self).created += 1
        self.prepared_size = None

    def prepare(self, ctx_id, det_size):
        self.prepared_size = det_size

    def get(self, _image):
        return []


class MemoryGuardTests(unittest.TestCase):
    def test_face_engine_reuses_one_model_for_all_detection_sizes(self):
        _FakeFaceAnalysis.created = 0
        settings = Settings(insightface_det_size=480, insightface_live_det_size=320)

        with patch("backend.app.face_engine.FaceAnalysis", _FakeFaceAnalysis):
            engine = FaceEngine(settings)
            first = engine._ensure_loaded(480)
            second = engine._ensure_loaded(320)

        self.assertIs(first, second)
        self.assertEqual(_FakeFaceAnalysis.created, 1)
        self.assertEqual(first.prepared_size, (480, 480))

    def test_decode_bounds_pixels_and_dimension(self):
        image = np.full((1200, 2000, 3), 127, dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        self.assertTrue(ok)

        decoded = decode_image_bytes(
            encoded.tobytes(),
            max_bytes=8 * 1024 * 1024,
            max_pixels=100_000,
            max_dimension=400,
        )

        height, width = decoded.shape[:2]
        self.assertLessEqual(width, 400)
        self.assertLessEqual(height, 400)
        self.assertLessEqual(width * height, 100_000)

    def test_base64_decode_uses_same_pixel_bound(self):
        image = np.zeros((500, 500, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)
        payload = "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")

        decoded = decode_base64_image(
            payload,
            max_bytes=8 * 1024 * 1024,
            max_pixels=40_000,
            max_dimension=256,
        )

        self.assertLessEqual(decoded.shape[0] * decoded.shape[1], 40_000)
        self.assertLessEqual(max(decoded.shape[:2]), 256)


if __name__ == "__main__":
    unittest.main()
