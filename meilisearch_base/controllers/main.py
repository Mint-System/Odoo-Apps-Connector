import gzip
import json
import logging
import time
from io import BytesIO

from odoo import _, http
from odoo.http import request

logger = logging.getLogger(__name__)


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
            logger.debug("Received data from meilisearch task webhook: %s", data_str)

            ndjson_lines = data_str.strip().split("\n")
            for line in ndjson_lines:
                data = json.loads(line)
                task_uid = data["uid"]

                # Search for task with retry logic
                task = None
                for attempt in range(3):
                    task = request.env["meilisearch.task"].sudo().search([("uid", "=", task_uid)])
                    if task:
                        break
                    time.sleep(0.5)

                if task:
                    if data["status"] == "succeeded":
                        task.task_succeeded()
                    elif data["status"] == "failed":
                        task.task_failed()
                else:
                    logger.debug("Meilisearch task with uid %s not found after 3 retries", task_uid)
                    return request.make_response(
                        _("Task with id %s not found", task_uid), status=404, headers={"Content-Type": "text/plain"}
                    )

            return request.make_response("OK", status=200)

        elif request.httprequest.method == "GET":
            return "Send me a POST request to this endpoint"
