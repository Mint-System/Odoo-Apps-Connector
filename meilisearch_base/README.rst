.. image:: https://img.shields.io/badge/licence-GPL--3-blue.svg
    :target: http://www.gnu.org/licenses/gpl-3.0-standalone.html
    :alt: License: GPL-3

================
Meilisearch Base
================

Sets up meilisearch indexes and provides a document mixin.

For a detailed documentation have a look at https://www.odoo-wiki.org/meilisearch-base.html

Configuration
~~~~~~~~~~~~~

* Inherit the Meilisearch document mixin for the model:

.. code-block:: python
  
    class Country(models.Model):
        _name = "res.country"
        _inherit = ["res.country", "meilisearch.document.mixin"]

* Modify the document schema:

.. code-block:: python
  
    def _prepare_index_document(self):
        document = super()._prepare_index_document()
        document['code'] = self.code
        document['currency_name'] = self.currency_id.name
        return document

    @api.depends("code", "currency_id.name")
    def _compute_index_document(self):
        return super()._compute_index_document()

* Modify the search domain:

.. code-block:: python

    def _get_index_document_domain(self):
        return [("code", "=", "CH")]

* Modify the search domain:

.. code-block:: python

    def _get_index_document_domain(self):
        return lambda r: r.code != "CH"

* Hook into meilisearch tasks:

.. code-block:: python

    class MeilisearchTask(models.Model):
        _inherit = ["meilisearch.task"]

        def task_succeeded(self):
            _logger.warning("Succeeded documents: %s" % self.document_ids)
            return super().task_succeeded()

        def task_failed(self):
            _logger.error("Failed documents: %s" % self.document_ids)
            return super().task_failed()

Usage
=====

* Open "Settings > Integration" and set Meiliesarch API url and key
* Add user to the "Meilisearch Index Manager" group
* Create entries in "Settings > Technical > Meilisearch Indexes"

Maintainer
~~~~~~~~~~

.. image:: https://raw.githubusercontent.com/Mint-System/Wiki/master/assets/mint-system-logo.png
  :target: https://www.mint-system.ch

This module is maintained by Mint System GmbH.

For support and more information, please visit `our Website <https://www.mint-system.ch>`__.
