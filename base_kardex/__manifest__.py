{
    "name": "Base Kardex Mixin",
    "summary": """
        Provides Basic Kardex Functionality.
    """,
    "author": "Mint System GmbH",
    "website": "https://www.mint-system.ch/",
    "category": "Purchase,Technical,Accounting,Invoicing,Sales,Human Resources,Services,Helpdesk,Manufacturing,Website,Inventory,Administration,Productivity",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["base_external_mssql"],
    "data": [],
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["images/screen.png"],
    "assets": {
        "web.assets_backend": [
            "base_kardex/static/src/js/*.js",
        ],
    },
}
