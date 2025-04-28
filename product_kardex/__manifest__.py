{
    "name": "Product Kardex",
    "summary": """
        Module summary.
    """,
    "author": "Mint System GmbH",
    "website": "https://www.mint-system.ch/",
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
    "demo": ["demo/document_demo.xml"],
    "assets": {
        "web.assets_backend": [
            "product_kardex/static/src/js/*.js",
            "product_kardex/static/src/xml/*.xml",
        ],
    },
}
