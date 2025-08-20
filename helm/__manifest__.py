{
    "name": "Helm",
    "summary": """
        Apply Helm charts.
    """,
    "author": "Mint System GmbH",
    "website": "https://www.mint-system.ch/",
    "category": "Repository",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["product", "kubectl"],
    "data": [
        "views/helm_repo_views.xml",
        "views/product_template.xml",
        "views/helm_chart_views.xml",
        "views/helm_release_views.xml",
        "views/helm_chart_value_views.xml",
        "security/security.xml",
        "security/ir.model.access.csv",
        "wizards/helm_chart_install.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["images/screen.png"],
    "demo": ["demo/demo.xml"],
    "external_dependencies": {"bin": ["helm"]},
}
