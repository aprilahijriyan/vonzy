from abc import ABC, abstractmethod

from pydantic import BaseModel


class BaseAction(ABC, BaseModel):
    @abstractmethod
    def initialize(self) -> None:
        pass

    @abstractmethod
    def cleanup(self):
        pass

    @abstractmethod
    def execute(self, *args, context: dict = None) -> None:
        pass
