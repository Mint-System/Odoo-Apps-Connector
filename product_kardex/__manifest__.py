{
    "name": "Product Kardex",
    "summary": """
        Module summary.
    """,
    "author": "Mint System GmbH, Odoo Community Association (OCA)",
    "website": "https://www.mint-system.ch",
    "category": "Stock",
    "version": "17.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["product"],
    "data": [
        #"security/ir.model.access.csv",
        #"views/assets.xml",
        #"views/sale_order.xml"
        "views/product_kardex_views.xml"
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["images/screen.png"],
    "qweb": ["static/src/xml/board.xml"],
    "demo": ["demo/document_demo.xml"],
    "assets": {
        "web.assets_backend": [
            "stock_kardex_connection/static/src/js/action_refresh.js",
        ],
        "web.assets_qweb": [
            "stock_kardex_connection/static/src/xml/listview_refresh.xml",
        ],
    },
}
