import importlib.util
from io import BytesIO
from pathlib import Path
import unittest

from PIL import Image
from funzug_pipeline import is_portrait_4_5


class ImageRatioTests(unittest.TestCase):
    def test_native_sizes(self):
        for size in [(1080, 1350), (1024, 1280), (1200, 1500), (1600, 2000), (1122, 1402), (1121, 1401)]:
            with self.subTest(size=size):
                self.assertTrue(is_portrait_4_5(size))

    def test_other_ratios_outside_nearest_pixel_are_rejected(self):
        for size in [(1123, 1402), (1121, 1402), (1080, 1080), (1350, 1080), (0, 0), (1, 1)]:
            with self.subTest(size=size):
                self.assertFalse(is_portrait_4_5(size))

    def test_media_conversion_preserves_alternate_native_size(self):
        spec = importlib.util.spec_from_file_location('ratio_media_server', Path(__file__).parents[1] / 'media-host/server.py')
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        data = BytesIO()
        Image.new('RGB', (1122, 1402)).save(data, format='PNG')
        output = server.normalize_image(data.getvalue(), 'image/png')
        with Image.open(BytesIO(output)) as image:
            self.assertEqual(image.size, (1122, 1402))
