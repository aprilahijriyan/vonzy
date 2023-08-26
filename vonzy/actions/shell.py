import ast
import functools
import os
import re
import shutil
import typing

import pexpect
import pexpect.popen_spawn
from pydantic import PrivateAttr

from ..logger import log
from ..utils import render_step_context
from .base import BaseAction

if typing.TYPE_CHECKING:
    from ..schema import StepContext

if os.name == "nt":
    raise RuntimeError("Windows is not supported.")

DEFAULT_SHELL = shutil.which("bash")


def clean(s):
    """
    Taken from: https://github.com/kennethreitz/crayons/blob/b1b78c9a357e0c348a1288ee5ef0318f08ccf257/crayons.py#L135C1-L139C15
    """
    strip = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]")
    txt = strip.sub("", s)
    return txt.replace("\r", "").replace("\n", "")


def _validate_return_code(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        instance: Action = args[0]
        rv = fn(*args, **kwargs)
        if not kwargs.get("expect"):
            log.debug(f"Getting return code for cmd={args[1]}")
            results = fn(
                instance,
                cmd="echo $?",
            )
            log.debug(f"cmd={args[1]} results={results!r}")
            results = clean("".join(results))
            returncode = None
            try:
                returncode = ast.literal_eval(results)
            except Exception:
                pass

            if isinstance(returncode, int) and returncode != 0:
                raise RuntimeError(f"cmd={args[1]} returncode={returncode!r}")
        return rv

    return wrapper


class Action(BaseAction):
    cwd: typing.Optional[str] = None
    debug: typing.Optional[bool] = False
    timeout: typing.Optional[float] = 2
    _command: str = PrivateAttr(DEFAULT_SHELL)
    _process: typing.Optional[pexpect.spawn] = PrivateAttr(None)

    def initialize(self) -> None:
        log.debug(f"Launches the command {self._command!r} into a background process.")
        if self._process is None:
            self._process = pexpect.spawn(
                self._command,
                encoding="utf-8",
                timeout=self.timeout,
                cwd=self.cwd,
                env=os.environ,
            )
            self._process.delaybeforesend = 0.1
            # self._process.logfile = sys.stdout

    def cleanup(self) -> typing.Optional[int]:
        log.debug(f"Closing process {self._command!r}")
        exit_code = 0
        if self._process:
            self._process.close()
            exit_code = self._process.exitstatus
            self._process = None
        log.debug(f"Process {self._command!r} exited with code {exit_code!r}")

    @_validate_return_code
    def execute(
        self,
        cmd: str,
        *,
        expect: typing.Optional[str] = None,
        context: typing.Optional["StepContext"] = None,
        line_callback: typing.Optional[typing.Callable[[str], None]] = None,
    ):
        if not isinstance(cmd, str):
            raise RuntimeError(f"{__name__}: Command {cmd!r} is not a string.")

        if context is not None:
            cmd = render_step_context(cmd.strip(), context=context)
        if expect:
            log.debug(f"Expects {expect!r} on stdin")
            self._process.expect(expect)

        if not expect:
            # Hide the log if it has the `expect` param. To prevent displaying unwanted text/data on the console.
            log.debug(f"Executing command {cmd!r}")
            expect = ["\r", "\n"]

        self._process.sendline(cmd)
        should_print = False
        lines = []
        while True:
            try:
                self._process.expect(expect)
                if should_print:
                    line = self._process.before + self._process.after
                    if self.debug:
                        print(line, end="")
                    if callable(line_callback):
                        line_callback(line)
                    lines.append(line)

                if self._process.before == "\x1b[?2004l":
                    should_print = True
            except (pexpect.TIMEOUT, pexpect.EOF) as e:
                # log.error(f"Command {cmd!r} timed out/eof. {e}")
                break
            except Exception as e:
                log.error(f"Error executing command {cmd!r}: {e}")
                break

        return lines
