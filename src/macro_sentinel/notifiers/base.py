from __future__ import annotations

from abc import ABC, abstractmethod

from macro_sentinel.models import SendResult


class BaseNotifier(ABC):
    channel: str

    @abstractmethod
    async def send(self, message: str) -> SendResult:
        raise NotImplementedError
