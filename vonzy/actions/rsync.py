
from .shell import Action as ShellAction
from pydantic import PrivateAttr, Field
from ..logger import log

import os
import shlex
import shutil
import pexpect
import typing

if typing.TYPE_CHECKING:
    from ..schema import StepContext

class Action(ShellAction):
    ssh_user: str
    ssh_host: str
    ssh_port: typing.Optional[int]
    ssh_password: str
    source: str
    destination: str
    options: list[str]
    excludes: list[str] = Field(default_factory=list)
    
    # _process: typing.Optional[pexpect.spawn] = PrivateAttr(None)

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
        destination = f"{self.ssh_user}@{self.ssh_host}:{self.destination}"
        args.append(destination)
        command = shlex.join([command, *args])
        self.execute(command)
        for line in self.execute(self.ssh_password, expect="password:"):
            if isinstance(line, str) and "Permission denied, please try again." in line:
                raise RuntimeError(f"{__name__}: Invalid password!")
