.. image:: https://img.shields.io/badge/licence-GPL--3-blue.svg
    :target: http://www.gnu.org/licenses/gpl-3.0-standalone.html
    :alt: License: GPL-3

================
Meilisearch Base
================

Sets up meilisearch indexes and provides document mixin.

For a detailed documentation have a look at https://www.odoo-wiki.org/meilisearch-base.html

Configuration
~~~~~~~~~~~~~

* Setup Meilisearch API and Meilisearch index
* Inherit the Meilisearch document mixin in your model:

.. code-block:: python
  
    class Country(models.Model):
        _name = "res.country"
        _inherit = ["res.country", "meilisearch.document.mixin"]

* Modify the document schema for your model :

.. code-block:: python
  
    def _prepare_index_document(self):
        document = super()._prepare_index_document()
        document['code'] = self.code
        return document


* Add action for updating the index document to your model:

.. code-block:: xml
  
    <record id="model_res_country_action_update_index_document" model="ir.actions.server">
        <field name="name">Update Index Document</field>
        <field name="model_id" ref="base.model_res_country"/>
        <field name="binding_model_id" ref="base.model_res_country"/>
        <field name="binding_view_types">tree,form</field>
        <field name="state">code</field>
        <field name="code">records.update_index_document()</field>
    </record>

Maintainer
~~~~~~~~~~

.. image:: https://raw.githubusercontent.com/Mint-System/Wiki/master/assets/mint-system-logo.png
  :target: https://www.mint-system.ch

This module is maintained by Mint System GmbH.

For support and more information, please visit `our Website <https://www.mint-system.ch>`__.
