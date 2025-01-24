{
    "name": "Base Kardex Mixin",
    "summary": """
        Provides Basic Kardex Functionality.
    """,
    "author": "Mint System GmbH, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/sale-workflow",
    "category": "Purchase,Technical,Accounting,Invoicing,Sales,Human Resources,Services,Helpdesk,Manufacturing,Website,Inventory,Administration,Productivity",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["base_external_mssql"],
    "data": [
        "views/base_kardex_settings.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["images/screen.png"],
    "qweb": ["static/src/xml/board.xml"],
    "demo": ["demo/document_demo.xml"],
    "assets": {
        "web.assets_backend": [
            "base_kardex/static/src/js/*.js",
        ],
        "web.assets_qweb": [
            "base_kardex/static/src/xml/*.xml",
        ],
    },
}
