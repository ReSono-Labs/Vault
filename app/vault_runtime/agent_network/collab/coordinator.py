from __future__ import annotations

from .a2a_rpc import (
    A2aRpcError,
    TERMINAL_STATES,
    extract_context_id,
    extract_response_text,
    extract_task_id,
    extract_task_state,
    send_message,
    task_from_send_result,
    wait_for_task,
)
from .store import TurnStore
from .types import PeerEndpoint, TurnStatus


class TurnCoordinator:
    def __init__(self, store: TurnStore | None = None) -> None:
        self.store = store or TurnStore()

    def send(
        self,
        peer: PeerEndpoint,
        message: str,
        *,
        context_id: str | None = None,
        wait: bool = False,
        timeout: float = 120.0,
    ) -> dict:
        record = self.store.create(peer.name, message, context_id)
        try:
            send_result = send_message(peer.url, peer.token, message, context_id)
            task_id = extract_task_id(send_result)
            resolved_context = extract_context_id(send_result) or context_id
            self.store.update(
                record.turn_id,
                task_id=task_id,
                context_id=resolved_context,
            )
            if not wait:
                self.store.update(record.turn_id, status=TurnStatus.PENDING, response_text=None)
                final = self.store.get(record.turn_id)
                return self._public_turn(final)

            immediate_task = task_from_send_result(send_result)
            if immediate_task is not None:
                state = extract_task_state(immediate_task)
                response_text = extract_response_text(immediate_task)
                if state in TERMINAL_STATES:
                    if state.endswith("failed") or state.endswith("rejected") or state.endswith("cancelled") or state.endswith("canceled"):
                        self.store.update(
                            record.turn_id,
                            status=TurnStatus.FAILED,
                            response_text=response_text,
                            error=f"task ended in state {state}",
                            raw_task=immediate_task,
                        )
                    else:
                        self.store.update(
                            record.turn_id,
                            status=TurnStatus.COMPLETED,
                            response_text=response_text,
                            raw_task=immediate_task,
                        )
                    final = self.store.get(record.turn_id)
                    return self._public_turn(final)

            if not task_id:
                raise A2aRpcError("SendMessage did not return a task id")

            task = wait_for_task(peer.url, peer.token, task_id, timeout=timeout)
            state = extract_task_state(task)
            response_text = extract_response_text(task)
            if state in {"failed", "canceled", "cancelled", "rejected", "task_state_failed", "task_state_canceled", "task_state_cancelled", "task_state_rejected"}:
                self.store.update(
                    record.turn_id,
                    status=TurnStatus.FAILED,
                    response_text=response_text,
                    error=f"task ended in state {state}",
                    raw_task=task,
                )
            else:
                self.store.update(
                    record.turn_id,
                    status=TurnStatus.COMPLETED,
                    response_text=response_text,
                    raw_task=task,
                )
            final = self.store.get(record.turn_id)
            return self._public_turn(final)
        except A2aRpcError as exc:
            self.store.update(record.turn_id, status=TurnStatus.FAILED, error=str(exc))
            raise
        except Exception as exc:
            self.store.update(record.turn_id, status=TurnStatus.FAILED, error=str(exc))
            raise

    def list_turns(self, limit: int = 20) -> list[dict]:
        return [self._public_turn(record) for record in self.store.list_recent(limit)]

    @staticmethod
    def _public_turn(record) -> dict:
        return {
            "turn_id": record.turn_id,
            "peer": record.peer,
            "context_id": record.context_id,
            "task_id": record.task_id,
            "status": record.status.value,
            "request_text": record.request_text,
            "response_text": record.response_text,
            "error": record.error,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
