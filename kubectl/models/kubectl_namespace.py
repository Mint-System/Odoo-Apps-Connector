import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class KubectlNamespace(models.Model):
    _name = "kubectl.namespace"
    _description = "Kubectl Namespace"
    _resource = "namespace"

    uid = fields.Char()
    name = fields.Char(required=True)
    display_name = fields.Char(compute="_compute_display_name")
    cluster_id = fields.Many2one("kubectl.cluster", required=True)

    _sql_constraints = [
        (
            "unique_name_by_cluster_id",
            "UNIQUE(name, cluster_id)",
            "Namespace must be unique per cluster.",
        ),
    ]

    @api.model
    def get_or_create(self, values):
        namespace_id = self.search(
            [
                ("name", "=", values["name"]),
                ("cluster_id", "=", values["cluster_id"]),
            ]
        )
        if namespace_id:
            return namespace_id
        else:
            return self.create(values)

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.name} ({rec.cluster_id.name})"

    def _get_uid(self):
        """
        Get uid of the record
        """
        for rec in self.filtered(lambda r: not r.uid):
            command = f"kubectl get {self._resource} {rec.name} -o jsonpath='{{.metadata.uid}}'"
            response = rec
            rec.uid = response

    def action_get_namespaces(self):
        """
        Load all namespaces from the current context.
        Creat missing namespace entries.
        """

        context_id = self.env["kubectl.context"].search([]).filtered("is_current")
        cluster_id = context_id.cluster_id

        command = f"kubectl get {self._resource} -o json".split(" ")
        result = context_id.run(command)

        data = json.loads(result.stdout)
        for item in data["items"]:
            name = item["metadata"]["name"]
            uid = item["metadata"]["uid"]
            namespace_id = self.search([("name", "=", name), ("cluster_id", "=", cluster_id.id)])
            if namespace_id:
                namespace_id.write({"uid": uid})
            else:
                self.create({"name": name, "uid": uid, "cluster_id": cluster_id.id})
