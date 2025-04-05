{
    "name": "Kubectl",
    "summary": """
        Manage kubectl configuration.
    """,
    "author": "Mint System GmbH",
    "website": "https://www.mint-system.ch/",
    "category": "Repository",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["base"],
    "data": ["views/res_users_views.xml"],
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["images/screen.png"],
    "external_dependencies": {"bin": ["kubectl"]},
}
