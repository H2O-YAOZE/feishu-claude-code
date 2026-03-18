import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional


@dataclass
class ActiveRun:
    user_id: str
    card_msg_id: str
    proc: object | None = None
    stop_requested: bool = False
    stop_announced: bool = False


class ActiveRunRegistry:
    def __init__(self):
        self._runs: dict[str, ActiveRun] = {}

    def start_run(self, user_id: str, card_msg_id: str) -> ActiveRun:
        active_run = ActiveRun(user_id=user_id, card_msg_id=card_msg_id)
        self._runs[user_id] = active_run
        return active_run

    def get_run(self, user_id: str) -> Optional[ActiveRun]:
        return self._runs.get(user_id)

    def attach_process(self, user_id: str, proc) -> Optional[ActiveRun]:
        active_run = self._runs.get(user_id)
        if active_run is None:
            return None
        active_run.proc = proc
        if active_run.stop_requested and getattr(proc, "returncode", None) is None:
            proc.terminate()
        return active_run

    def clear_run(self, user_id: str, active_run: Optional[ActiveRun] = None):
        current = self._runs.get(user_id)
        if current is None:
            return
        if active_run is not None and current is not active_run:
            return
        self._runs.pop(user_id, None)


async def _maybe_await(result):
    if asyncio.iscoroutine(result):
        await result


async def stop_run(
    registry: ActiveRunRegistry,
    user_id: str,
    on_stopped: Optional[Callable[[ActiveRun], Awaitable[None] | None]] = None,
    grace_seconds: float = 2.0,
) -> bool:
    active_run = registry.get_run(user_id)
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
