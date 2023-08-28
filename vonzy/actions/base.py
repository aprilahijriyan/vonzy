import typing
from abc import ABC, abstractmethod

from pydantic import BaseModel

if typing.TYPE_CHECKING:
    from vonzy.schema import StepContext

T = typing.TypeVar("T")


class BaseAction(ABC, BaseModel):
    @abstractmethod
    def initialize(self) -> None:
        pass

    @abstractmethod
    def cleanup(self):
        pass

    @abstractmethod
    def execute(
        self, *args, context: typing.Optional[dict[typing.Any, typing.Any]] = None
    ) -> None:
        pass

    def handle_commands(
        self, commands: T, *, context: typing.Optional["StepContext"] = None
    ) -> T:
        return commands
