{
    "name": "Meilisearch Base",
    "summary": """
        Sets up meilisearch indexes and provides a document mixin.
    """,
    "author": "Mint System GmbH",
    "website": "https://www.mint-system.ch",
    "category": "Technical",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["base_setup"],
    "data": [
        "data/cron.xml",
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/res_config_settings_view.xml",
        "views/meilisearch_index_views.xml",
        "views/meilisearch_task_views.xml",
        "views/meilisearch_document_views.xml",
        "views/res_country_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["images/screen.png"],
    "demo": ["demo/meilisearch_index_demo.xml"],
    "external_dependencies": {
        "python": [
            "meilisearch",
        ],
    },
    "assets": {"web.assets_backend": ["meilisearch_base/static/src/css/style.css"]},
}
