import logging
import os

from odoo import fields, models
from odoo.tools import config

_logger = logging.getLogger(__name__)


class GitForge(models.Model):
    _name = "git.forge"
    _description = "Git Forge"

    name = fields.Char(required=True)
    hostname = fields.Char(required=True)
    http_url = fields.Char(
        string="HTTP Url", compute="_compute_http_url", readonly=True
    )
    local_path = fields.Char(compute="_compute_local_path")

    def _compute_http_url(self):
        for rec in self:
            rec.http_url = f"https://{rec.hostname}"

    def _compute_local_path(self):
        for rec in self:
            rec.local_path = f"{config['data_dir']}/git/{rec.hostname}"

    def _import_repos_from_local_path(self):
        imported_repos = []
        for forge_id in self:

            # First level in local path are accounts
            accounts = [
                f
                for f in os.listdir(forge_id.local_path)
                if os.path.isdir(os.path.join(forge_id.local_path, f))
            ]
            for account in accounts:
                local_path = os.path.join(forge_id.local_path, account)
                account_id = self.env["git.account"].search(
                    [("name", "=", account)], limit=1
                )
                if not account_id:
                    account_id = self.env["git.account"].create(
                        {"name": account, "forge_id": forge_id.id}
                    )

                # Second level in local path are repos
                repos = [
                    f
                    for f in os.listdir(local_path)
                    if os.path.isdir(os.path.join(local_path, f))
                ]
                for repo in repos:
                    repo_id = self.env["git.repo"].search(
                        [("name", "=", repo)], limit=1
                    )
                    if not repo_id:
                        repo_id = self.env["git.repo"].create(
                            {"name": repo, "account_id": account_id.id}
                        )
                        imported_repos.append(repo_id.name)

        return imported_repos

    def action_import_repos_from_local_path(self):
        import_repos = self._import_repos_from_local_path()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Repositories Imported",
                "message": f"Successfully imported {len(import_repos)} repositorie(s).",
                "type": "success",
            },
        }
