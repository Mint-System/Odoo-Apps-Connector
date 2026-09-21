{
    "name": "Stock Kardex Simulator",
    "summary": """
        Simulate the answer of Kardex for testing.
    """,
    "author": "Mint System GmbH",
    "website": "https://www.mint-system.ch/",
    "category": "Stock",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["stock_kardex"],
    "data": [
        "security/ir.model.access.csv",
        "views/base_external_mssql_views.xml",
        "views/stock_picking_views.xml",
        "wizard/kardex_simulator_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
