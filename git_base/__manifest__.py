{
    "name": "Git Base",
    "summary": """
        Manage git repositories with Odoo.
    """,
    "author": "Mint System GmbH",
    "website": "https://www.mint-system.ch/",
    "category": "Technical",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["ssh", "server_config_environment", "mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/data.xml",
        "views/git_forge_views.xml",
        "views/git_account_views.xml",
        "views/git_repo_views.xml",
        "views/git_repo_cmd_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["images/screen.png"],
    "demo": ["demo/demo.xml"],
    "external_dependencies": {"bin": ["git"]},
    "assets": {"web.assets_backend": ["git_base/static/src/css/style.css"]},
}
