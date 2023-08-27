from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel


class BaseAction(ABC, BaseModel):
    @abstractmethod
    def initialize(self) -> None:
        pass

    @abstractmethod
    def cleanup(self):
        pass

    @abstractmethod
    def execute(self, *args, context: Optional[dict[Any, Any]] = None) -> None:
        pass
