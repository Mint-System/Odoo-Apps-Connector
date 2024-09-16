import gzip
import json
import logging
from io import BytesIO

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class MeilissearchController(http.Controller):
    @http.route(
        "/meilisearch/task-webhook/",
        type="http",
        methods=["GET", "POST"],
        auth="public",
        csrf=False,
    )
    def meilisearch_task_webhook(self, **kwargs):
        if request.httprequest.method == "POST" and request.httprequest.data:

            # Decode compressed ndjson
            compressed_data = request.httprequest.data
            with gzip.GzipFile(fileobj=BytesIO(compressed_data)) as gz:
                decompressed_data = gz.read()
            data_str = decompressed_data.decode("utf-8")
            _logger.debug("Received data from meilisearch task webhook: %s", data_str)
            ndjson_lines = data_str.strip().split("\n")
            for line in ndjson_lines:
                data = json.loads(line)

                # Get task by uid
                task = (
                    request.env["meilisearch.task"]
                    .sudo()
                    .search([("uid", "=", data["uid"])])
                )
                # _logger.warning(
                #     [
                #         "webhook",
                #         data["uid"],
                #         task,
                #         request.env["meilisearch.task"]
                #         .sudo()
                #         .search([], limit=10)
                #         .mapped("uid"),
                #     ]
                # )

                if task:
                    if data["status"] == "succeeded":
                        task.task_succeeded()
                    elif data["status"] == "failed":
                        task.task_failed()
                else:
                    raise NotFound()

        elif request.httprequest.method == "GET":
            return "Send me a POST request to this endpoint."
