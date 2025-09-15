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
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/res_users_views.xml",
        "views/kubectl_cluster_views.xml",
        "views/kubectl_context_views.xml",
        "views/res_partner_views.xml",
        "views/kubectl_namespace_views.xml",
        "data/data.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["images/screen.png"],
    "external_dependencies": {"bin": ["kubectl"]},
    "demo": ["demo/demo.xml"],
    "assets": {"web.assets_backend": ["kubectl/static/src/css/style.css"]},
}
