import logging
from unittest.mock import patch

from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class TestResCountry(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.index = cls.env.ref("meilisearch_base.demo_index_countries")
        cls.country_id = cls.env["res.country"].create(
            {"code": "TX", "name": "Taixan", "currency_id": cls.env.ref("base.TWD").id, "phone_code": 887}
        )

    # @patch("odoo.addons.meilisearch_base.models.meilisearch_document_mixin.MeilsearchDocumentMixin._update_documents")
    @patch("odoo.addons.meilisearch_base.models.res_country.Country._compute_index_document")
    def test_compute_index_document(self, mock):
        self.country_id.write({"code": "TX"})
        self.assertFalse(mock.called)
        self.country_id.write({"code": "TY"})
        self.assertFalse(mock.called)

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
        self.assertEqual(self.index.document_indexed_count, 250)

    def test_document_hash(self):
        country_id = self.country_id

        # This should trigger the compute method, but not a document upate
        last_index_document_hash = country_id.index_document_hash
        country_id.write({"code": "TX"})
        self.assertEqual(country_id.index_document_hash, last_index_document_hash)

        # This should trigger the compute method and a document update
        country_id.write({"code": "XX"})
        self.assertNotEqual(country_id.index_date, last_index_document_hash)

        # This should not trigger anything
        last_index_document_hash = country_id.index_document_hash
        country_id.write({"phone_code": 888})
        self.assertEqual(country_id.index_document_hash, last_index_document_hash)
