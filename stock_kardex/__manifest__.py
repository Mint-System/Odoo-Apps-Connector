{
    "name": "Stock Kardex Stock",
    "summary": """
        Module summary.
    """,
    "author": "Mint System GmbH",
    "website": "https://github.com/OCA/sale-workflow",
    "category": "Stock",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["stock", "mrp"],
    "data": [
        "security/ir.model.access.csv",
        "views/kardex_stock_views.xml",
        "views/kardex_bom_views.xml",
        "views/kardex_production_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["images/screen.png"],
    "qweb": ["static/src/xml/board.xml"],
    "demo": ["demo/document_demo.xml"],
    "assets": {
        "web.assets_backend": [
            "stock_kardex/static/src/js/*.js",
        ],
        "web.assets_qweb": [
            "stock_kardex/static/src/xml/*.xml",
        ],
    },
}
