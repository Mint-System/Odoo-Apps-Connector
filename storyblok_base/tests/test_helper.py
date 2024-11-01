import logging

from odoo.tests import common
from odoo.tools import file_open

from odoo.addons.storyblok_base.models.helper import get_image_file_type

_logger = logging.getLogger(__name__)


class TestResPartner(common.TransactionCase):
    def test_get_image_file_type(self):
        sample_files = [
            "sample.bmp",
            "sample.gif",
            "sample.jpg",
            "sample.png",
            "sample.pdf",
            "sample.svg",
            "sample.tif",
            "sample.webp",
            "sample2.svg",
        ]
        for sample_file in sample_files:
            extension = sample_file.split(".")[1]
            with file_open(f"storyblok_base/tests/sample.{extension}", "rb") as file:
                self.assertEqual(get_image_file_type(file.read()), extension)
