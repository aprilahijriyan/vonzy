import typing

from pydantic import PrivateAttr, SecretStr

from .base import BaseAction

if typing.TYPE_CHECKING:
    from ..schema import StepContext

from ..utils import render_step_context

try:
    import paramiko
except ImportError:
    raise ImportError("paramiko module not found. try: pip install paramiko")


class Action(BaseAction):
    ssh_host: SecretStr
    ssh_user: SecretStr
    ssh_port: typing.Optional[int] = 22
    ssh_password: SecretStr

    _ssh_client: typing.Optional[paramiko.SSHClient] = PrivateAttr(None)

    def handle_commands(
        self,
        commands: list[typing.Any],
        *,
        context: typing.Optional["StepContext"] = None,
    ) -> None:
        cmd_list = []
        for cmd in commands:
            if not isinstance(cmd, str):
                raise RuntimeError(f"{__name__}: Command {cmd!r} is not a string.")

            cmd = render_step_context(cmd.strip(), context=context)
            cmd_list.append(cmd)

        return [";".join(cmd_list)]

    def initialize(self) -> None:
        self._ssh_client = paramiko.SSHClient()
        self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self._ssh_client.connect(
                hostname=self.ssh_host.get_secret_value(),
                port=self.ssh_port,
                username=self.ssh_user.get_secret_value(),
                password=self.ssh_password.get_secret_value(),
            )
        except Exception as e:
            raise RuntimeError(f"{__name__}: {e}")

    def cleanup(self):
        try:
            self._ssh_client.close()
        except AttributeError as e:
            if "'NoneType' object has no attribute 'time'" in str(e):
                pass

        self._ssh_client = None

    def execute(
        self,
        cmd: str,
        *,
        context: typing.Optional["StepContext"] = None,
    ) -> None:
        stdin, stdout, stderr = self._ssh_client.exec_command(cmd)
        stdin.close()
        stdout.channel.set_combine_stderr(True)
        for line in stdout:
            print(line, end="")

        returncode = stdout.channel.recv_exit_status()
        if isinstance(returncode, int) and returncode != 0:
            raise RuntimeError(f"{__name__}: cmd={cmd!r} returncode={returncode!r}")
