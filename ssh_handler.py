"""
ssh_handler.py
---------------
Thin wrapper around Paramiko for connecting to the target EC2 instance and
running shell commands. Every other module (diagnostics, remediation) goes
through this class instead of touching Paramiko directly.
"""

import socket
import paramiko

import config
import health_status
import retry_policy


class SSHHandler:
    """Manages a single SSH connection to the target server."""

    def __init__(self, host=None, username=None, key_path=None, port=None, timeout=None):
        self.host = host or config.EC2_HOST
        self.username = username or config.EC2_USERNAME
        self.key_path = key_path or config.EC2_KEY_PATH
        self.port = port or config.EC2_SSH_PORT
        self.timeout = timeout or config.SSH_TIMEOUT
        self.client = None
        self.os_type = None

    def connect(self):
        """
        Open the SSH connection. Raises ConnectionError with a human-readable
        message on any failure (bad key, auth failure, host unreachable, etc).
        """
        self.client = paramiko.SSHClient()
        # NOTE: AutoAddPolicy trusts the host key on first connect without
        # verification. Acceptable for a hackathon demo against a known EC2
        # box; for production, pin the host key instead.
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            # Load the private key explicitly. This avoids Paramiko treating a
            # legacy PEM RSA key as an OpenSSH-format key during auto-detection.
            private_key = paramiko.PKey.from_path(self.key_path)
            retry_policy.run(
                lambda: self.client.connect(
                    hostname=self.host, port=self.port, username=self.username,
                    pkey=private_key, look_for_keys=False, allow_agent=False, timeout=self.timeout,
                ),
                attempts=config.RETRY_ATTEMPTS, delay=config.RETRY_DELAY_SECONDS,
                retry_if=lambda exc: not isinstance(exc, (paramiko.AuthenticationException, paramiko.PasswordRequiredException)),
            )
            health_status.update("ssh", "healthy", f"Connected to {self.host}")
        except FileNotFoundError:
            raise ConnectionError(f"SSH key file not found at path: '{self.key_path}'.")
        except (paramiko.AuthenticationException, paramiko.PasswordRequiredException):
            health_status.update("ssh", "error", f"Authentication failed for {self.host}")
            raise ConnectionError(
                f"SSH authentication failed for {self.username}@{self.host}. "
                "Check EC2_USERNAME and EC2_KEY_PATH."
            )
        except (paramiko.SSHException, socket.error, socket.timeout, OSError) as e:
            health_status.update("ssh", "error", f"{self.host}: {e}")
            raise ConnectionError(f"Could not connect to {self.host}:{self.port} - {e}")

        return True

    def run_command(self, command, timeout=None):
        """
        Execute a command on the remote server and return a structured result.
        Never raises - failures are captured in the returned dict so callers
        (including the LLM agent) can reason about them programmatically.
        """
        if self.client is None:
            raise RuntimeError("SSH is not connected. Call connect() first.")

        timeout = timeout or config.SSH_COMMAND_TIMEOUT
        try:
            stdin, stdout, stderr = retry_policy.run(
                lambda: self.client.exec_command(command, timeout=timeout),
                attempts=config.RETRY_ATTEMPTS, delay=config.RETRY_DELAY_SECONDS,
            )
            exit_code = stdout.channel.recv_exit_status()
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            return {
                "command": command,
                "stdout": out,
                "stderr": err,
                "exit_code": exit_code,
                "success": exit_code == 0,
            }
        except (paramiko.SSHException, socket.timeout, socket.error) as e:
            return {
                "command": command,
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "success": False,
            }

    def close(self):
        """Close the SSH connection if open. Safe to call multiple times."""
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
            finally:
                self.client = None
