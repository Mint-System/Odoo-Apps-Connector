{
    "name": "Stock Kardex Stock",
    "summary": """
        Module summary.
    """,
    "author": "Mint System GmbH, Odoo Community Association (OCA)",
    "website": "https://www.mint-system.ch",
    "category": "Stock",
    "version": "17.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["stock", "mrp"],
    "data": [
        #"security/ir.model.access.csv",
        #"report/invoice_document.xml",
        #"data/ir_sequence.xml",
        "views/kardex_stock_views.xml",
        "views/kardex_bom_views.xml",
        "views/kardex_production_views.xml"
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["images/screen.png"],
    "qweb": ["static/src/xml/board.xml"],
    "demo": ["demo/document_demo.xml"],
    "assets": {
        "web.assets_backend": [
            "stock_kardex_stock/static/src/js/action_refresh.js",
        ],
        "web.assets_qweb": [
            "stock_kardex_stock/static/src/xml/listview_refresh.xml",
        ],
    },
}
