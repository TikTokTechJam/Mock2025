from __future__ import annotations

from privastream_api.pipeline.safety import (
    CapabilityObservation,
    CapabilityPolicy,
    MediaWindow,
    PrivacyGate,
    PrivacyGateConfig,
)


def _window() -> MediaWindow:
    return MediaWindow(start_ms=0, end_ms=100)


def _ready(
    capability_id: str, watermark_ms: int = 100, lag_ms: int = 0
) -> CapabilityObservation:
    return CapabilityObservation(
        capability_id=capability_id,
        state="ready",
        watermark_ms=watermark_ms,
        lag_ms=lag_ms,
    )


def test_gate_publishes_only_after_required_watermark_covers_window() -> None:
    gate = PrivacyGate((CapabilityPolicy("spoken_pii", required=True),))

    pending = gate.evaluate(_window(), (_ready("spoken_pii", watermark_ms=99),))
    safe = gate.evaluate(_window(), (_ready("spoken_pii"),))

    assert pending.action == "full_redact"
    assert pending.readiness == "unsafe"
    assert pending.reason_code == "required_watermark_pending"
    assert safe.action == "publish_protected"
    assert safe.safe_to_publish
    assert safe.processed_watermark_ms == 100


def test_configured_lag_limit_fails_closed() -> None:
    gate = PrivacyGate(
        (CapabilityPolicy("spoken_pii", required=True, max_lag_ms=5),)
    )

    decision = gate.evaluate(_window(), (_ready("spoken_pii", lag_ms=6),))

    assert decision.action == "full_redact"
    assert decision.reason_code == "required_lag_exceeded"


def test_optional_failure_degrades_but_required_failure_fails_closed() -> None:
    gate = PrivacyGate(
        (
            CapabilityPolicy("spoken_pii", required=True),
            CapabilityPolicy("visual_pii", required=False),
        )
    )

    degraded = gate.evaluate(
        _window(),
        (
            _ready("spoken_pii"),
            CapabilityObservation("visual_pii", state="unavailable"),
        ),
    )
    unsafe = gate.evaluate(
        _window(),
        (
            CapabilityObservation(
                "spoken_pii", state="failed", reason_code="model_failure"
            ),
            _ready("visual_pii"),
        ),
    )

    assert degraded.action == "publish_protected"
    assert degraded.readiness == "degraded"
    assert degraded.reason_code == "optional_unavailable"
    assert unsafe.action == "full_redact"
    assert unsafe.readiness == "unsafe"
    assert unsafe.reason_code == "required_failed"


def test_liveness_is_separate_and_unhealthy_liveness_fails_closed() -> None:
    gate = PrivacyGate((CapabilityPolicy("spoken_pii", required=True),))
    gate.set_liveness(False, "processor_disconnect")

    decision = gate.evaluate(_window(), (_ready("spoken_pii"),))

    assert decision.liveness == "unhealthy"
    assert decision.readiness == "unsafe"
    assert decision.reason_code == "processor_disconnect"
    assert gate.snapshot().liveness == "unhealthy"
    assert gate.snapshot().readiness == "unsafe"


def test_panic_requires_explicit_exit_and_consecutive_healthy_checks() -> None:
    gate = PrivacyGate(
        (CapabilityPolicy("spoken_pii", required=True),),
        PrivacyGateConfig(recovery_successes=2),
    )
    panic = gate.enter_panic()
    active = gate.evaluate(_window(), (_ready("spoken_pii"),))
    gate.exit_panic()
    pending = gate.evaluate(_window(), (_ready("spoken_pii"),))
    recovered = gate.evaluate(_window(), (_ready("spoken_pii"),))

    assert active.reason_code == "panic_active"
    assert active.action == "full_redact"
    assert panic.readiness == "unsafe"
    assert pending.reason_code == "panic_recovery_pending"
    assert pending.panic_active
    assert recovered.action == "publish_protected"
    assert not recovered.panic_active


def test_gate_can_choose_block_when_no_safe_fallback_is_available() -> None:
    gate = PrivacyGate(
        (CapabilityPolicy("spoken_pii", required=True),),
        PrivacyGateConfig(fallback_action="block"),
    )

    decision = gate.evaluate(_window(), ())

    assert decision.action == "block"
    assert decision.blocked
    assert decision.reason_code == "required_observation_missing"
