"""Central privacy readiness and fail-closed publication decisions.

The gate consumes sanitized processor observations and returns a publication
decision. It does not inspect or mutate media; transport and modality-specific
renderers apply the selected protected or safe-fallback action at their own
boundaries.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from threading import RLock
from typing import Literal


PublicationAction = Literal["publish_protected", "full_redact", "block"]
PrivacyReadiness = Literal["ready", "degraded", "unsafe"]
LivenessState = Literal["alive", "unhealthy"]
CapabilityState = Literal["ready", "processing", "unavailable", "failed"]
FallbackAction = Literal["full_redact", "block"]


def _validate_code(value: str, field_name: str) -> None:
    if not value or len(value) > 64 or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789_-"
        for character in value
    ):
        raise ValueError(f"{field_name} must be a lowercase sanitized reason code")


@dataclass(frozen=True, slots=True)
class MediaWindow:
    """A source-timeline window whose publication safety is being decided."""

    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("media window timestamps must be non-negative and ordered")


@dataclass(frozen=True, slots=True)
class CapabilityPolicy:
    """Required/optional policy and watermark limits for one capability."""

    capability_id: str
    required: bool
    enabled: bool = True
    max_lag_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.capability_id.strip():
            raise ValueError("capability_id must not be empty")
        if self.required and not self.enabled:
            raise ValueError("required capabilities cannot be disabled")
        if self.max_lag_ms is not None and self.max_lag_ms < 0:
            raise ValueError("max_lag_ms must be non-negative when configured")


@dataclass(frozen=True, slots=True)
class CapabilityObservation:
    """Sanitized processor health and source-time progress."""

    capability_id: str
    state: CapabilityState
    watermark_ms: int | None = None
    lag_ms: int | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not self.capability_id.strip():
            raise ValueError("capability_id must not be empty")
        if self.state not in {"ready", "processing", "unavailable", "failed"}:
            raise ValueError("unsupported capability state")
        if self.watermark_ms is not None and self.watermark_ms < 0:
            raise ValueError("watermark_ms must be non-negative")
        if self.lag_ms is not None and self.lag_ms < 0:
            raise ValueError("lag_ms must be non-negative")
        if self.reason_code is not None:
            _validate_code(self.reason_code, "reason_code")


@dataclass(frozen=True, slots=True)
class PrivacyGateConfig:
    """Safe fallback and recovery policy for the central gate."""

    fallback_action: FallbackAction = "full_redact"
    recovery_successes: int = 2

    def __post_init__(self) -> None:
        if self.fallback_action not in {"full_redact", "block"}:
            raise ValueError("fallback_action must be full_redact or block")
        if self.recovery_successes <= 0:
            raise ValueError("recovery_successes must be positive")


@dataclass(frozen=True, slots=True)
class PublicationDecision:
    """Sanitized action returned to transport or protected-output consumers."""

    action: PublicationAction
    readiness: PrivacyReadiness
    liveness: LivenessState
    reason_code: str
    window: MediaWindow
    processed_watermark_ms: int | None
    processed_lag_ms: int | None
    panic_active: bool

    @property
    def safe_to_publish(self) -> bool:
        return self.action == "publish_protected"

    @property
    def uses_safe_fallback(self) -> bool:
        return self.action == "full_redact"

    @property
    def blocked(self) -> bool:
        return self.action == "block"


@dataclass(frozen=True, slots=True)
class PrivacyGateSnapshot:
    """Current sanitized gate state for readiness/status consumers."""

    readiness: PrivacyReadiness
    liveness: LivenessState
    panic_active: bool
    panic_exit_requested: bool
    recovery_streak: int
    reason_code: str
    capabilities: tuple[CapabilityObservation, ...] = ()


class PrivacyGate:
    """Own publication safety for one in-memory media-session boundary."""

    def __init__(
        self,
        policies: Sequence[CapabilityPolicy],
        config: PrivacyGateConfig | None = None,
    ) -> None:
        policy_values = tuple(policies)
        policy_ids = [policy.capability_id for policy in policy_values]
        if len(policy_ids) != len(set(policy_ids)):
            raise ValueError("capability policies must have unique ids")
        self.policies = policy_values
        self.config = config or PrivacyGateConfig()
        self._lock = RLock()
        self._liveness: LivenessState = "alive"
        self._liveness_reason = "liveness_ok"
        self._panic_active = False
        self._panic_exit_requested = False
        self._recovery_streak = 0
        self._last_snapshot = PrivacyGateSnapshot(
            readiness="unsafe",
            liveness="alive",
            panic_active=False,
            panic_exit_requested=False,
            recovery_streak=0,
            reason_code="not_evaluated",
        )

    def set_liveness(
        self, healthy: bool, reason_code: str | None = None
    ) -> PrivacyGateSnapshot:
        """Update process liveness without conflating it with privacy readiness."""

        with self._lock:
            if reason_code is not None:
                _validate_code(reason_code, "reason_code")
            if healthy:
                self._liveness = "alive"
                self._liveness_reason = "liveness_ok"
            else:
                self._liveness = "unhealthy"
                self._liveness_reason = reason_code or "process_unhealthy"
            readiness = "unsafe" if not healthy else None
            return self._snapshot(self._liveness_reason, readiness=readiness)

    def enter_panic(self, reason_code: str = "manual_panic") -> PrivacyGateSnapshot:
        """Enter immediate fail-closed panic without consulting detectors."""

        _validate_code(reason_code, "reason_code")
        with self._lock:
            self._panic_active = True
            self._panic_exit_requested = False
            self._recovery_streak = 0
            return self._snapshot(reason_code, readiness="unsafe")

    def exit_panic(self) -> PrivacyGateSnapshot:
        """Request explicit panic exit; healthy required checks still gate recovery."""

        with self._lock:
            if self._panic_active:
                self._panic_exit_requested = True
                self._recovery_streak = 0
            readiness = "unsafe" if self._panic_active else None
            return self._snapshot("panic_exit_requested", readiness=readiness)

    def snapshot(self) -> PrivacyGateSnapshot:
        """Return the latest sanitized state without evaluating a new window."""

        with self._lock:
            return self._last_snapshot

    def evaluate(
        self,
        window: MediaWindow,
        observations: Sequence[CapabilityObservation],
    ) -> PublicationDecision:
        """Decide whether one source window may publish normally."""

        with self._lock:
            observation_values = tuple(observations)
            observation_map: dict[str, CapabilityObservation] = {}
            invalid = False
            policy_ids = {policy.capability_id for policy in self.policies}
            for observation in observation_values:
                if observation.capability_id not in policy_ids:
                    invalid = True
                elif observation.capability_id in observation_map:
                    invalid = True
                else:
                    observation_map[observation.capability_id] = observation

            processed_watermark = self._processed_watermark(observation_map)
            processed_lag = self._processed_lag(observation_map)
            if invalid:
                return self._finish(
                    self._decision(
                        window,
                        action=self.config.fallback_action,
                        readiness="unsafe",
                        reason_code="invalid_observation",
                        processed_watermark_ms=processed_watermark,
                        processed_lag_ms=processed_lag,
                    ),
                    observation_values,
                )

            required_issue: str | None = None
            optional_issue: str | None = None
            for policy in self.policies:
                if not policy.enabled:
                    continue
                issue = self._observation_issue(
                    policy, observation_map.get(policy.capability_id), window
                )
                if issue is None:
                    continue
                if policy.required and required_issue is None:
                    required_issue = issue
                elif not policy.required and optional_issue is None:
                    optional_issue = issue

            liveness_issue = None if self._liveness == "alive" else self._liveness_reason
            if self._panic_active:
                if (
                    self._panic_exit_requested
                    and liveness_issue is None
                    and required_issue is None
                ):
                    self._recovery_streak += 1
                    if self._recovery_streak >= self.config.recovery_successes:
                        self._panic_active = False
                        self._panic_exit_requested = False
                        self._recovery_streak = 0
                    else:
                        return self._finish(
                            self._decision(
                                window,
                                action=self.config.fallback_action,
                                readiness="unsafe",
                                reason_code="panic_recovery_pending",
                                processed_watermark_ms=processed_watermark,
                                processed_lag_ms=processed_lag,
                            ),
                            observation_values,
                        )
                else:
                    self._recovery_streak = 0
                    reason = (
                        "panic_recovery_blocked"
                        if self._panic_exit_requested
                        else "panic_active"
                    )
                    return self._finish(
                        self._decision(
                            window,
                            action=self.config.fallback_action,
                            readiness="unsafe",
                            reason_code=reason,
                            processed_watermark_ms=processed_watermark,
                            processed_lag_ms=processed_lag,
                        ),
                        observation_values,
                    )

            if liveness_issue is not None or required_issue is not None:
                return self._finish(
                    self._decision(
                        window,
                        action=self.config.fallback_action,
                        readiness="unsafe",
                        reason_code=liveness_issue or required_issue or "unsafe",
                        processed_watermark_ms=processed_watermark,
                        processed_lag_ms=processed_lag,
                    ),
                    observation_values,
                )

            readiness: PrivacyReadiness = "degraded" if optional_issue else "ready"
            reason_code = optional_issue or "ready"
            return self._finish(
                self._decision(
                    window,
                    action="publish_protected",
                    readiness=readiness,
                    reason_code=reason_code,
                    processed_watermark_ms=processed_watermark,
                    processed_lag_ms=processed_lag,
                ),
                observation_values,
            )

    def _observation_issue(
        self,
        policy: CapabilityPolicy,
        observation: CapabilityObservation | None,
        window: MediaWindow,
    ) -> str | None:
        prefix = "required" if policy.required else "optional"
        if observation is None:
            return f"{prefix}_observation_missing"
        if observation.state != "ready":
            return f"{prefix}_{observation.state}"
        if observation.watermark_ms is None:
            return f"{prefix}_watermark_missing"
        if observation.watermark_ms < window.end_ms:
            return f"{prefix}_watermark_pending"
        if observation.lag_ms is None:
            return f"{prefix}_lag_missing"
        if policy.max_lag_ms is not None and observation.lag_ms > policy.max_lag_ms:
            return f"{prefix}_lag_exceeded"
        return None

    def _processed_watermark(
        self, observations: dict[str, CapabilityObservation]
    ) -> int | None:
        active_required = tuple(
            policy for policy in self.policies if policy.enabled and policy.required
        )
        active_policies = active_required or tuple(
            policy for policy in self.policies if policy.enabled
        )
        values = [
            observation.watermark_ms
            for policy in active_policies
            for observation in (observations.get(policy.capability_id),)
            if observation is not None and observation.watermark_ms is not None
        ]
        return min(values) if values else None

    def _processed_lag(self, observations: dict[str, CapabilityObservation]) -> int | None:
        active_required = tuple(
            policy for policy in self.policies if policy.enabled and policy.required
        )
        active_policies = active_required or tuple(
            policy for policy in self.policies if policy.enabled
        )
        values = [
            observation.lag_ms
            for policy in active_policies
            for observation in (observations.get(policy.capability_id),)
            if observation is not None and observation.lag_ms is not None
        ]
        return max(values) if values else None

    def _decision(
        self,
        window: MediaWindow,
        *,
        action: PublicationAction,
        readiness: PrivacyReadiness,
        reason_code: str,
        processed_watermark_ms: int | None,
        processed_lag_ms: int | None,
    ) -> PublicationDecision:
        _validate_code(reason_code, "reason_code")
        return PublicationDecision(
            action=action,
            readiness=readiness,
            liveness=self._liveness,
            reason_code=reason_code,
            window=window,
            processed_watermark_ms=processed_watermark_ms,
            processed_lag_ms=processed_lag_ms,
            panic_active=self._panic_active,
        )

    def _finish(
        self,
        decision: PublicationDecision,
        observations: tuple[CapabilityObservation, ...],
    ) -> PublicationDecision:
        self._last_snapshot = PrivacyGateSnapshot(
            readiness=decision.readiness,
            liveness=self._liveness,
            panic_active=self._panic_active,
            panic_exit_requested=self._panic_exit_requested,
            recovery_streak=self._recovery_streak,
            reason_code=decision.reason_code,
            capabilities=tuple(
                sorted(observations, key=lambda observation: observation.capability_id)
            ),
        )
        return decision

    def _snapshot(
        self,
        reason_code: str,
        *,
        readiness: PrivacyReadiness | None = None,
    ) -> PrivacyGateSnapshot:
        self._last_snapshot = PrivacyGateSnapshot(
            readiness=readiness or self._last_snapshot.readiness,
            liveness=self._liveness,
            panic_active=self._panic_active,
            panic_exit_requested=self._panic_exit_requested,
            recovery_streak=self._recovery_streak,
            reason_code=reason_code,
            capabilities=self._last_snapshot.capabilities,
        )
        return self._last_snapshot


__all__ = [
    "CapabilityObservation",
    "CapabilityPolicy",
    "CapabilityState",
    "LivenessState",
    "MediaWindow",
    "PrivacyGate",
    "PrivacyGateConfig",
    "PrivacyGateSnapshot",
    "PrivacyReadiness",
    "PublicationAction",
    "PublicationDecision",
]
