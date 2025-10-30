from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.logging import get_logger
from app.models import (
    Agent,
    AgentAlertKind,
    AgentAlertState,
    AgentAlertThreshold,
    AgentStatus,
    Notifier,
    NotifierEvent,
    NotifierEventType,
)
from app.tasks.notifications import dispatch_notifier_event

logger = get_logger().bind(component="agent-alerts")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AgentAlertEvaluator:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self._notifier_cache: dict[uuid.UUID, list[Notifier]] = defaultdict(list)
        self._events_to_dispatch: list[NotifierEvent] = []

    # ------------------------------------------------------------------
    # Loading helpers
    # ------------------------------------------------------------------

    def _load_agents(self) -> list[Agent]:
        stmt = (
            select(Agent)
            .where(Agent.is_deleted.is_(False))
            .options(
                joinedload(Agent.project),
                joinedload(Agent.environment),
                joinedload(Agent.alert_states),
            )
        )
        return self.session.execute(stmt).scalars().all()

    def _load_thresholds(self) -> dict[tuple[uuid.UUID, uuid.UUID | None], AgentAlertThreshold]:
        stmt = select(AgentAlertThreshold).where(AgentAlertThreshold.is_deleted.is_(False))
        thresholds = self.session.execute(stmt).scalars().all()
        mapping: dict[tuple[uuid.UUID, uuid.UUID | None], AgentAlertThreshold] = {}
        for threshold in thresholds:
            mapping[(threshold.project_id, threshold.environment_id)] = threshold
        return mapping

    def _defaults(self) -> dict[str, int]:
        return {
            "offline_seconds": int(self.settings.agent_offline_threshold_seconds),
            "backlog_threshold": int(self.settings.agent_backlog_threshold),
            "latency_threshold_ms": int(self.settings.agent_latency_threshold_ms),
        }

    def _resolve_threshold(self, agent: Agent, mapping: dict[tuple[uuid.UUID, uuid.UUID | None], AgentAlertThreshold]) -> dict[str, int]:
        defaults = self._defaults()
        if agent.project_id is None:
            return defaults
        specific = mapping.get((agent.project_id, agent.environment_id))
        if specific:
            return {
                "offline_seconds": specific.offline_seconds,
                "backlog_threshold": specific.backlog_threshold,
                "latency_threshold_ms": specific.latency_threshold_ms,
            }
        generic = mapping.get((agent.project_id, None))
        if generic:
            return {
                "offline_seconds": generic.offline_seconds,
                "backlog_threshold": generic.backlog_threshold,
                "latency_threshold_ms": generic.latency_threshold_ms,
            }
        return defaults

    def _get_notifiers(self, project_id: uuid.UUID | None) -> list[Notifier]:
        if project_id is None:
            return []
        if project_id in self._notifier_cache:
            return self._notifier_cache[project_id]
        stmt = select(Notifier).where(
            Notifier.project_id == project_id,
            Notifier.enabled.is_(True),
            Notifier.is_deleted.is_(False),
        )
        notifiers = self.session.execute(stmt).scalars().all()
        self._notifier_cache[project_id] = notifiers
        return notifiers

    def _get_alert_state(self, agent: Agent, kind: AgentAlertKind) -> AgentAlertState:
        for state in agent.alert_states:
            if state.kind == kind and not state.is_deleted:
                return state
        state = AgentAlertState(
            agent_id=agent.id,
            kind=kind,
            active=False,
            context={},
        )
        self.session.add(state)
        agent.alert_states.append(state)
        return state

    # ------------------------------------------------------------------
    # Notification helpers
    # ------------------------------------------------------------------

    def _build_alert_payload(
        self,
        *,
        agent: Agent,
        kind: AgentAlertKind,
        severity: str,
        message: str,
        observed_at: datetime,
        thresholds: dict[str, int],
        context: dict[str, object],
    ) -> dict[str, object]:
        project = agent.project
        environment = agent.environment
        payload: dict[str, object] = {
            "agent_id": str(agent.id),
            "agent_name": agent.name,
            "project_id": str(project.id) if project else None,
            "project_name": project.name if project else None,
            "environment_id": str(environment.id) if environment else None,
            "environment_name": environment.name if environment else None,
            "alert_type": kind.value,
            "severity": severity,
            "status": agent.status.value,
            "observed_at": observed_at.isoformat(),
            "thresholds": thresholds,
            "metrics": {
                "queue_depth": agent.last_queue_depth,
                "latency_ms": agent.last_latency_ms,
                "cpu_pct": agent.last_cpu_pct,
                "memory_pct": agent.last_memory_pct,
            },
            "message": message,
            "context": context,
        }
        return payload

    def _queue_alert_notification(
        self,
        *,
        agent: Agent,
        kind: AgentAlertKind,
        severity: str,
        message: str,
        observed_at: datetime,
        thresholds: dict[str, int],
        context: dict[str, object],
    ) -> None:
        if agent.project_id is None:
            return
        notifiers = self._get_notifiers(agent.project_id)
        if not notifiers:
            return
        payload = self._build_alert_payload(
            agent=agent,
            kind=kind,
            severity=severity,
            message=message,
            observed_at=observed_at,
            thresholds=thresholds,
            context=context,
        )
        events: list[NotifierEvent] = []
        for notifier in notifiers:
            event = NotifierEvent(
                project_id=notifier.project_id,
                notifier_id=notifier.id,
                event=NotifierEventType.AGENT_ALERT,
                payload=payload,
            )
            self.session.add(event)
            events.append(event)
        self.session.flush()
        self._events_to_dispatch.extend(events)

    # ------------------------------------------------------------------
    # Evaluation logic
    # ------------------------------------------------------------------

    def evaluate(self) -> None:
        agents = self._load_agents()
        thresholds = self._load_thresholds()
        now = _now()

        for agent in agents:
            agent.health_metadata = agent.health_metadata or {}
            agent.health_metadata["last_evaluated_at"] = now.isoformat()

            if not agent.enabled:
                agent.status = AgentStatus.DISABLED
                for kind in AgentAlertKind:
                    state = self._get_alert_state(agent, kind)
                    if state.active:
                        state.active = False
                        state.last_cleared_at = now
                        state.context = {"reason": "agent disabled"}
                continue

            thresholds_for_agent = self._resolve_threshold(agent, thresholds)

            last_heartbeat = agent.last_heartbeat_at
            if last_heartbeat is None:
                age_seconds = None
            else:
                age_seconds = max((now - last_heartbeat).total_seconds(), 0.0)

            offline_triggered = (
                last_heartbeat is None
                or age_seconds is None
                or age_seconds > thresholds_for_agent["offline_seconds"]
            )
            backlog_triggered = (
                agent.last_queue_depth is not None
                and agent.last_queue_depth > thresholds_for_agent["backlog_threshold"]
            )
            latency_triggered = (
                agent.last_latency_ms is not None
                and agent.last_latency_ms > thresholds_for_agent["latency_threshold_ms"]
            )

            if offline_triggered:
                backlog_triggered = False
                latency_triggered = False

            previous_status = agent.status
            if offline_triggered:
                agent.status = AgentStatus.OFFLINE
                agent.health_metadata["status_reason"] = "offline"
            elif backlog_triggered or latency_triggered:
                agent.status = AgentStatus.DEGRADED
                agent.health_metadata["status_reason"] = "backlog" if backlog_triggered else "latency"
            else:
                agent.status = AgentStatus.ONLINE
                agent.health_metadata["status_reason"] = "healthy"

            if previous_status != agent.status:
                logger.info(
                    "agent_status_changed",
                    agent_id=str(agent.id),
                    old_status=previous_status.value,
                    new_status=agent.status.value,
                )

            self._process_alert(agent, AgentAlertKind.OFFLINE, offline_triggered, now, thresholds_for_agent, {
                "age_seconds": age_seconds,
            })
            self._process_alert(agent, AgentAlertKind.BACKLOG, backlog_triggered, now, thresholds_for_agent, {
                "queue_depth": agent.last_queue_depth,
            })
            self._process_alert(agent, AgentAlertKind.LATENCY, latency_triggered, now, thresholds_for_agent, {
                "latency_ms": agent.last_latency_ms,
            })

        self.session.commit()

        for event in self._events_to_dispatch:
            dispatch_notifier_event.apply_async((str(event.id),))

    # ------------------------------------------------------------------
    # Alert state processing
    # ------------------------------------------------------------------

    def _process_alert(
        self,
        agent: Agent,
        kind: AgentAlertKind,
        triggered: bool,
        now: datetime,
        thresholds: dict[str, int],
        context: dict[str, object],
    ) -> None:
        state = self._get_alert_state(agent, kind)
        if triggered:
            severity = "critical" if kind == AgentAlertKind.OFFLINE else "warning"
            message = self._build_trigger_message(agent, kind, context)
            if not state.active:
                state.active = True
                state.last_triggered_at = now
                state.context = context
                self._queue_alert_notification(
                    agent=agent,
                    kind=kind,
                    severity=severity,
                    message=message,
                    observed_at=now,
                    thresholds=thresholds,
                    context=context,
                )
            else:
                state.context.update(context)
        else:
            if state.active:
                state.active = False
                state.last_cleared_at = now
                state.context = context
                recovery_message = self._build_recovery_message(agent, kind)
                self._queue_alert_notification(
                    agent=agent,
                    kind=kind,
                    severity="info",
                    message=recovery_message,
                    observed_at=now,
                    thresholds=thresholds,
                    context={**context, "recovered": True},
                )

    def _build_trigger_message(self, agent: Agent, kind: AgentAlertKind, context: dict[str, object]) -> str:
        if kind == AgentAlertKind.OFFLINE:
            age = context.get("age_seconds")
            if isinstance(age, (int, float)):
                return f"Agent {agent.name} is offline (last heartbeat {int(age)}s ago)."
            return f"Agent {agent.name} is offline."
        if kind == AgentAlertKind.BACKLOG:
            depth = context.get("queue_depth")
            return f"Agent {agent.name} backlog is {depth}."
        if kind == AgentAlertKind.LATENCY:
            latency = context.get("latency_ms")
            return f"Agent {agent.name} latency is {latency} ms."
        return f"Agent {agent.name} alert: {kind.value}."

    def _build_recovery_message(self, agent: Agent, kind: AgentAlertKind) -> str:
        if kind == AgentAlertKind.OFFLINE:
            return f"Agent {agent.name} has come back online."
        if kind == AgentAlertKind.BACKLOG:
            return f"Agent {agent.name} backlog is back within threshold."
        if kind == AgentAlertKind.LATENCY:
            return f"Agent {agent.name} latency is back within threshold."
        return f"Agent {agent.name} has recovered."


__all__ = ["AgentAlertEvaluator"]
