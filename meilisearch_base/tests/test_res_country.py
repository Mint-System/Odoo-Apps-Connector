import logging

from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class TestResCountry(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.index = cls.env.ref("meilisearch_base.demo_index_countries")

    def test_setup_index(self):
        self.index.button_check_api_key()
        self.index.button_create_index()
        self.index.button_update_index()

    def test_update_all_documents(self):
        country_ids = self.env[self.index.model].search([])
        country_ids.update_index_document()

    def test_check_all_documents(self):
        country_ids = self.env[self.index.model].search([])
        country_ids.check_index_document()
        self.index.button_check_all_documents()
        self.assertEqual(self.index.document_indexed_count, 249)
