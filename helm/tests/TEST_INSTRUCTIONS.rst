Prepare Kubernetes:

- Start local kindd cluster "kind-kind"
- Setup hostnames cloud.local, odoo.cloud.local and restic.cloud.local

Setup chart:

- Open "Helm > Repos" and click on "kubernetes-build"
- Click on "Add" and refresh the page
- Ensure the repo has been added
- Do the same for "ingress-nginx"

Install charts

- Open "Helm > Releases > ingress-nginx" and click "Install"
- Open "odoo" release and click "Install"
- Check if containers are ready
- Forward nginx port and open url

Uninstall charts

- Open "Helm > Releases > odoo" and click "Uninstall"
- Open "ingress-nginx" release and click "Uninstall"
