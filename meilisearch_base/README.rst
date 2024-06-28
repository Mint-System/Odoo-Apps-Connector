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

* Inherit the Meilisearch document mixin in the model:

.. code-block:: python
  
    class Country(models.Model):
        _name = "res.country"
        _inherit = ["res.country", "meilisearch.document.mixin"]

* Modify the document schema for the model :

.. code-block:: python
  
    def _prepare_index_document(self):
        document = super()._prepare_index_document()
        document['code'] = self.code
        document['currency_name'] = self.currency_id.name
        return document

    @api.depends("code", "currency_id.name")
    def _compute_index_document(self):
        return super()._compute_index_document()

* Add actions for checking, updating and deleting the index document to the model:

.. code-block:: xml
  
    <record
        id="model_res_country_action_update_index_document"
        model="ir.actions.server"
    >
        <field name="name">Update Index Document</field>
        <field name="model_id" ref="base.model_res_country" />
        <field name="binding_model_id" ref="base.model_res_country" />
        <field name="binding_view_types">tree,form</field>
        <field name="state">code</field>
        <field name="code">records.update_index_document()</field>
        <field name="groups_id" eval="[(4, ref('base.group_erp_manager'))]" />
    </record>

    <record
        id="model_res_country_action_check_index_document"
        model="ir.actions.server"
    >
        <field name="name">Check Index Document</field>
        <field name="model_id" ref="base.model_res_country" />
        <field name="binding_model_id" ref="base.model_res_country" />
        <field name="binding_view_types">tree,form</field>
        <field name="state">code</field>
        <field name="code">records.check_index_document()</field>
        <field name="groups_id" eval="[(4, ref('base.group_erp_manager'))]" />
    </record>

    <record
        id="model_res_country_action_delete_index_document"
        model="ir.actions.server"
    >
        <field name="name">Delete Index Document</field>
        <field name="model_id" ref="base.model_res_country" />
        <field name="binding_model_id" ref="base.model_res_country" />
        <field name="binding_view_types">tree,form</field>
        <field name="state">code</field>
        <field name="code">records.delete_index_document()</field>
        <field name="groups_id" eval="[(4, ref('base.group_erp_manager'))]" />
    </record>

Usage
=====

* Setup Meilisearch API and Meilisearch Index

Maintainer
~~~~~~~~~~

.. image:: https://raw.githubusercontent.com/Mint-System/Wiki/master/assets/mint-system-logo.png
  :target: https://www.mint-system.ch

This module is maintained by Mint System GmbH.

For support and more information, please visit `our Website <https://www.mint-system.ch>`__.
