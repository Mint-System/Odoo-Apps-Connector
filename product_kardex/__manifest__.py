{
    "name": "Product Kardex",
    "summary": """
        Module summary.
    """,
    "author": "Mint System GmbH, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/sale-workflow",
    "category": "Stock",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["product"],
    "data": [
        "views/product_kardex_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["images/screen.png"],
    "qweb": ["static/src/xml/board.xml"],
    "demo": ["demo/document_demo.xml"],
    "assets": {
        "web.assets_backend": [
            "product_kardex/static/src/js/*.js",
            "product_kardex/static/src/xml/*.xml",
        ],
    },
}
