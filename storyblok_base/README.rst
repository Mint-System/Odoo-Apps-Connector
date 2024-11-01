.. image:: https://img.shields.io/badge/licence-GPL--3-blue.svg
    :target: http://www.gnu.org/licenses/gpl-3.0-standalone.html
    :alt: License: GPL-3

==============
Storyblok Base
==============

Upload files to storyblok.

Configuration
=============

* Setup Storyblok API
* Add Storyblok folder and connect with API and model

Once the asset field is updated, the file will be uploaded to Storyblok folder. The asset url and id are stored on the record as 'document_url' and `storyblok_asset_id`.

Usage
=====

* Inherit the Storyblok asset mixin in model with asset field:

.. code-block:: python
  
    class Partner(models.Model):
        _name = "res.partner"
        _inherit = ["res.partner", "storyblok.asset.mixin"]

* Define an inverse method of the asset field:

.. code-block:: python
  
        image_1920 = fields.Image(inverse="_inverse_image_1920")

        def _inverse_image_1920(self):
            self.upload_asset(self.image_1920)

* To prevent upload use `storyblok_update` context.

.. code-block:: python

    self.with_context(storyblok_upload=False).write({"image_1920": filepath})

Maintainer
~~~~~~~~~~

.. image:: https://raw.githubusercontent.com/Mint-System/Wiki/master/assets/mint-system-logo.png
  :target: https://www.mint-system.ch

This module is maintained by Mint System GmbH.

For support and more information, please visit `our Website <https://www.mint-system.ch>`__.
