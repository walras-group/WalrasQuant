from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional
from flashduty_sdk import FlashDutyClient

import nexuslog as logging


EventStatus = Literal["Ok", "Info", "Warning", "Critical"]


class FlashDutyConfigError(RuntimeError):
    pass


@dataclass
class FlashDutyPushService:
    integration_key: str | None
    strategy_id: str | None
    user_id: str | None

    def __post_init__(self) -> None:
        self._log = logging.getLogger(name=type(self).__name__)
        self._client = None

        if not self.integration_key:
            return

        self._client = FlashDutyClient(self.integration_key)

    def _ensure_ready(self) -> None:
        if not self.integration_key:
            raise FlashDutyConfigError(
                "FlashDuty integration_key is not configured in Config"
            )
        if self._client is None:
            raise FlashDutyConfigError("FlashDuty client is not initialized")

    def send_alert(
        self,
        event_status: EventStatus,
        title_rule: str,
        alert_key: Optional[str] = None,
        description: Optional[str] = None,
        labels: Optional[dict[str, str]] = None,
        images: Optional[list[dict[str, str]]] = None,
    ) -> None:
        self._ensure_ready()

        merged_labels: dict[str, str] = {}
        if labels:
            merged_labels.update(labels)
        if self.strategy_id is not None:
            merged_labels["strategy_id"] = self.strategy_id
        if self.user_id is not None:
            merged_labels["user_id"] = self.user_id

        self._client.send_alert(
            event_status=event_status,
            title_rule=title_rule,
            alert_key=alert_key,
            description=description,
            labels=merged_labels or None,
            images=images,
        )

    def shutdown(self) -> None:
        if self._client is None:
            return
        try:
            self._client.shutdown()
        except Exception as exc:  # pragma: no cover - defensive shutdown
            self._log.debug(f"FlashDuty shutdown failed: {exc}")
