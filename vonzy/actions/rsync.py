import shlex
import shutil
import typing

from pydantic import Field, SecretStr

from .shell import Action as ShellAction

if typing.TYPE_CHECKING:
    pass


class Action(ShellAction):
    ssh_user: SecretStr
    ssh_host: SecretStr
    ssh_port: typing.Optional[int]
    ssh_password: SecretStr
    source: str
    destination: str
    options: list[str]
    excludes: list[str] = Field(default_factory=list)

    # _process: typing.Optional[pexpect.spawn] = PrivateAttr(None)

    def line_callback(self, line: str):
        if isinstance(line, str) and "Permission denied, please try again." in line:
            raise RuntimeError(f"{__name__}: Invalid password!")

    def build_args(self) -> list[str]:
        options = []
        for opt in self.options:
            list_opt = shlex.split(opt)
            options.extend(list_opt)

        rsh_opts = ""
        if self.ssh_port is not None and self.ssh_port != 22:
            rsh_opts += "-p " + str(self.ssh_port)

        if len(rsh_opts) > 1:
            options.append("--rsh")
            options.append("ssh " + rsh_opts + "")

        for exclude_pattern in self.excludes:
            options.append(f"--exclude")
            options.append(exclude_pattern)

        return options

    def initialize(self) -> None:
        super().initialize()
        command = shutil.which("rsync")
        if not command:
            raise RuntimeError(f"{__name__}: rsync command not found")

        args = self.build_args()
        args.append(self.source)
        destination = f"{self.ssh_user.get_secret_value()}@{self.ssh_host.get_secret_value()}:{self.destination}"
        args.append(destination)
        command = shlex.join([command, *args])
        with self.control_output():
            self.execute(command)
            self.execute(
                self.ssh_password.get_secret_value(),
                expect="password:",
                line_callback=self.line_callback,
            )
