{
    "name": "Meilisearch Base",
    "summary": """
        Sets up meilisearch indexes and provides document mixin.
    """,
    "author": "Mint System GmbH, Odoo Community Association (OCA)",
    "website": "https://www.mint-system.ch",
    "category": "Technical",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["base", "queue_job"],
    "data": [
        "security/ir.model.access.csv",
        "views/meilisearch_api_views.xml",
        "views/meilisearch_index_views.xml",
        "views/meilisearch_document_views.xml",
        "views/res_country_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["images/screen.png"],
    "demo": ["demo/meilisearch_api_demo.xml", "demo/meilisearch_index_demo.xml"],
}
