{
    "name": "Meilisearch Base",
    "summary": """
        Setup meilisearch connection and provide document mixin.
    """,
    "author": "Mint System GmbH, Odoo Community Association (OCA)",
    "website": "https://www.mint-system.ch",
    "category": "Technical",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["base", "queue_job"],
    "data": ["security/ir.model.access.csv", "views/meilisearch_index_views.xml"],
    "installable": True,
    "application": False,
    "auto_install": False,
    "images": ["images/screen.png"],
    "demo": ["demo/meilisearch_index_demo.xml"],
}
