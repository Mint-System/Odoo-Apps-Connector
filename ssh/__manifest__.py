{
    "name": "SSH",
    "summary": """
        Manage SSH credentials.
    """,
    "author": "Mint System GmbH",
    "website": "https://www.mint-system.ch/",
    "category": "Technical",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["base_setup"],
    "data": [
        "views/res_users_views.xml",
        "views/res_config_settings_view.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["images/screen.png"],
    "external_dependencies": {"bin": ["ssh", "ssh-keygen", "openssl"]},
}
