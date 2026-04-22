import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional


@dataclass
class ActiveRun:
    user_id: str
    chat_id: str
    card_msg_id: str
    proc: object | None = None
    stop_requested: bool = False
    stop_announced: bool = False


class ActiveRunRegistry:
    def __init__(self):
        self._runs: dict[str, ActiveRun] = {}

    def start_run(self, user_id: str, card_msg_id: str, chat_id: str = "") -> ActiveRun:
        key = chat_id or user_id
        active_run = ActiveRun(user_id=user_id, chat_id=chat_id, card_msg_id=card_msg_id)
        self._runs[key] = active_run
        return active_run

    def get_run(self, user_id: str, chat_id: str = "") -> Optional[ActiveRun]:
        key = chat_id or user_id
        return self._runs.get(key)

    def attach_process(self, user_id: str, proc, chat_id: str = "") -> Optional[ActiveRun]:
        key = chat_id or user_id
        active_run = self._runs.get(key)
        if active_run is None:
            return None
        active_run.proc = proc
        if active_run.stop_requested and getattr(proc, "returncode", None) is None:
            proc.terminate()
        return active_run

    def clear_run(self, user_id: str, active_run: Optional[ActiveRun] = None, chat_id: str = ""):
        key = chat_id or user_id
        current = self._runs.get(key)
        if current is None:
            return
        if active_run is not None and current is not active_run:
            return
        self._runs.pop(key, None)


async def _maybe_await(result):
    if asyncio.iscoroutine(result):
        await result


async def stop_run(
    registry: ActiveRunRegistry,
    user_id: str,
    on_stopped: Optional[Callable[[ActiveRun], Awaitable[None] | None]] = None,
    grace_seconds: float = 2.0,
    chat_id: str = "",
) -> bool:
    active_run = registry.get_run(user_id, chat_id=chat_id)
    if active_run is None:
        return False

    active_run.stop_requested = True
    proc = active_run.proc
    if proc is not None and getattr(proc, "returncode", None) is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=grace_seconds)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()

    if on_stopped is not None and not active_run.stop_announced:
        await _maybe_await(on_stopped(active_run))
        active_run.stop_announced = True

    return True
