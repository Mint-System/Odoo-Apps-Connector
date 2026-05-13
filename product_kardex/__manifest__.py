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
    "depends": ["stock", "base_kardex", "product_category_tracking"],
    "data": [
        "data/cron.xml",
        "views/product_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["images/screen.png"],
    "assets": {
        "web.assets_backend": [
            "product_kardex/static/src/js/*.js",
            "product_kardex/static/src/xml/*.xml",
        ],
    },
}
