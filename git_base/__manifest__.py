{
    "name": "Git Base",
    "summary": """
        Manage git repositories with Odoo.
    """,
    "author": "Mint System GmbH, Odoo Community Association (OCA)",
    "website": "https://www.mint-system.ch",
    "category": "Technical",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["base"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/data.xml",
        "views/git_forge_views.xml",
        "views/git_account_views.xml",
        "views/git_repo_views.xml",
        "views/res_users_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["images/screen.png"],
    "demo": ["demo/demo.xml"],
    "external_dependencies": {
        "binary": ["git"],
        "python": [
            "GitPython",
        ],
    },
}
