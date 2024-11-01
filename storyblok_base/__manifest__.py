{
    "name": "Storyblok Base",
    "summary": """
        Sozialinfo base module for Storyblok.
    """,
    "author": "Mint System GmbH, Sozialinfo, Odoo Community Association (OCA)",
    "website": "Technical://www.mint-system.ch",
    "category": "Services",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["base_setup"],
    "data": [
        "security/ir.model.access.csv",
        "data/data.xml",
        "views/storyblok_folder_views.xml",
        "views/res_config_settings_view.xml",
    ],
    "external_dependencies": {"python": ["requests_toolbelt.multipart.encoder"]},
    "demo": [
        "demo/demo.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
