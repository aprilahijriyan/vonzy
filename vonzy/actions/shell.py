import ast
import contextlib
import functools
import os
import re
import shutil
import typing

import pexpect
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
    return txt  # .replace("\r", "").replace("\n", "")


def _validate_return_code(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        instance: Action = args[0]
        rv = fn(*args, **kwargs)
        if not instance.is_controlled:
            log.debug(f"Getting return code for cmd={args[1]}")
            results = fn(instance, cmd="echo $?", print_fn=None)
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
    timeout: typing.Optional[float] = 5
    _command: str = PrivateAttr(DEFAULT_SHELL)
    _process: typing.Optional[pexpect.pty_spawn.spawn] = PrivateAttr(None)
    _control_output: bool = PrivateAttr(False)
    _should_print: bool = PrivateAttr(False)

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
            self._process.delayafterread = 0.1
            # self._process.logfile = sys.stdout

    def cleanup(self) -> typing.Optional[int]:
        log.debug(f"Closing process {self._command!r}")
        exit_code = 0
        if self._process:
            self._process.close()
            exit_code = self._process.exitstatus
            self._process = None
        log.debug(f"Process {self._command!r} exited with code {exit_code!r}")
        return exit_code

    @contextlib.contextmanager
    def control_output(self):
        self._control_output = True
        try:
            yield self
        finally:
            self._control_output = False

    @property
    def is_controlled(self) -> bool:
        return self._control_output

    @_validate_return_code
    def execute(
        self,
        cmd: str,
        *,
        expect: typing.Optional[str] = None,
        context: typing.Optional["StepContext"] = None,
        line_callback: typing.Optional[typing.Callable[[str], None]] = None,
        print_fn: typing.Optional[typing.Callable] = print,
    ):
        if not isinstance(cmd, str):
            raise RuntimeError(f"{__name__}: Command {cmd!r} is not a string.")

        if context is not None:
            cmd = render_step_context(cmd.strip(), context=context)

        default_expect = ["\r\n", "\n"]
        if expect:
            log.debug(f"Expects {expect!r} on stdin")
            self._process.expect(expect)
        else:
            # Hide the log if it has the `expect` param. To prevent displaying unwanted text/data on the console.
            log.debug(f"Executing command {cmd!r}")

        self._process.sendline(cmd)
        lines = []
        _should_print = self._should_print if self.is_controlled else False
        while True:
            try:
                self._process.expect(default_expect)
                line = self._process.before + self._process.after
                # print(f"should_print={_should_print} match_idx={match_idx!r} line={line!r}")
                if _should_print:
                    if isinstance(line, str):
                        line = clean(line)
                    if self.debug and callable(print_fn):
                        print_fn(line, end="")
                    if callable(line_callback):
                        line_callback(line)
                    lines.append(line)

                if self._process.before and self._process.before.startswith(
                    "\x1b[?2004h"
                ):
                    _should_print = True
                    if self.is_controlled:
                        self._should_print = _should_print
            except (pexpect.TIMEOUT, pexpect.EOF) as e:
                # log.error(f"Command {cmd!r} timed out/eof. {e}")
                break

        return lines
