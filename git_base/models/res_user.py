import subprocess
import tempfile
import os
from odoo import models

class ResUsers(models.Model):
    _inherit = "res.users"

    def run_git_command(self, git_command):
        """
        Run a Git command using the user's SSH private key and password.
        """
        self.ensure_one() 
        if not self.ssh_private_key or not self.ssh_private_key_password:
            raise ValueError("SSH private key or password is missing.")

        # Create a temporary file for the SSH private key
        with tempfile.NamedTemporaryFile(delete=False) as temp_key_file:
            temp_key_file.write(self.ssh_private_key.encode('utf-8'))
            temp_key_path = temp_key_file.name

        try:
            # Set appropriate permissions for the key file
            os.chmod(temp_key_path, 0o600)

            # Use ssh-agent to add the key
            ssh_agent = subprocess.Popen(
                ["ssh-agent", "-s"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            ssh_agent_output, _ = ssh_agent.communicate()
            ssh_env = dict(
                line.split("=")
                for line in ssh_agent_output.strip().split("\n")
                if "=" in line
            )

            # Add the private key to ssh-agent
            ssh_add = subprocess.run(
                ["ssh-add", temp_key_path],
                input=self.ssh_private_key_password + "\n",
                text=True,
                env=ssh_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if ssh_add.returncode != 0:
                raise RuntimeError(f"ssh-add failed: {ssh_add.stderr}")

            # Run the Git command with the SSH environment
            result = subprocess.run(
                git_command,
                env={**os.environ, **ssh_env},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Return the output of the Git command
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }

        finally:
            # Cleanup: Remove the temporary key file and kill the ssh-agent
            os.unlink(temp_key_path)
            subprocess.run(["ssh-agent", "-k"], env=ssh_env)

