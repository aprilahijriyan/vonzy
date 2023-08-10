import sys
from .base import BaseAction

import jinja2
import string
import os
import shlex
import shutil
import pexpect
import typing

from pydantic import PrivateAttr, Field, validator
from ..logger import log
from ..errors import InvalidAction

if typing.TYPE_CHECKING:
    from ..schema import StepContext

DEFAULT_SHELL = os.environ.get("SHELL", shutil.which("bash"))

class Action(BaseAction):
    command: typing.Optional[str] = Field(f"{DEFAULT_SHELL} -i")
    debug: typing.Optional[bool] = False
    _process: typing.Optional[pexpect.spawn] = PrivateAttr(None)

    @validator("command", pre=True)
    def _validate_command(cls, v):
        parts = shlex.split(v)
        cmd = parts[0]
        args = parts[1:]
        fullcmd = shutil.which(cmd)
        if not fullcmd:
            raise RuntimeError(f"{__name__}: Command {cmd!r} not found.")
        return shlex.join([fullcmd, *args])

    def initialize(self) -> None:
        log.debug(f"Launches the command {self.command!r} into a background process.")
        if self._process is None:
            self._process = pexpect.spawn(self.command, encoding="utf-8", timeout=0.5, echo=False)
            # self._process.logfile = sys.stdout

    def cleanup(self) -> typing.Optional[int]:
        log.debug(f"Closing process {self.command!r}")
        exit_code = 0
        if self._process:
            self._process.close()
            exit_code = self._process.exitstatus
            self._process = None
        log.debug(f"Process {self.command!r} exited with code {exit_code!r}")

    def execute(self, cmd: str, *, expect: typing.Optional[str] = None, context: 'StepContext' = {}) -> None:
        if not isinstance(cmd, str):
            raise RuntimeError(f"Command {cmd!r} is not a string.")
        
        cmd = cmd.strip()
        if cmd.startswith("{{") and cmd.endswith("}}"):
            cmd = jinja2.Template(cmd).render(context)
        else:
            cmd = string.Template(cmd).substitute(context.ctx)
        
        if expect:
            log.debug(f"Expects {expect!r} on stdin")
            self._process.expect(expect)
        
        log.debug(f"Executing command {cmd!r}")
        self._process.sendline(cmd)
        should_print = False
        while True:
            try:
                line: str = self._process.readline()
                if should_print and self.debug:
                    print(line, end="") # FIXME: use logger or builtin ?
                else:
                    should_print = True
            except pexpect.TIMEOUT:
                break
            except Exception as e:
                log.error(f"Error executing command {cmd!r}: {e}")
