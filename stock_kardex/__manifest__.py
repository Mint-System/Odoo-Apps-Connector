{
    "name": "Stock Kardex Stock",
    "summary": """
        Module summary.
    """,
    "author": "Mint System GmbH",
    "website": "https://www.mint-system.ch/",
    "category": "Stock",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["base", "stock", "mrp", "purchase", "sale"],
    "data": [
        "security/ir.model.access.csv",
        "views/kardex_stock_views.xml",
        "views/kardex_bom_views.xml",
        "views/kardex_production_views.xml",
        "views/kardex_purchase_views.xml",
        "views/kardex_sale_views.xml",
        "views/kardex_sync_report.xml",
        "views/kardex_picking_type_views.xml",
        "views/kardex_move_line_views.xml",
        "views/res_config_settings_views.xml",
        "views/stock_quant_delete_wizard_view.xml",
        "views/stock_quant_delete_wizard_action.xml",
        "views/stock_lot_delete_wizard_view.xml",
        "views/stock_lot_delete_wizard_action.xml",
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
