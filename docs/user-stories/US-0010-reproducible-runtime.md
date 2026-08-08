# US-0010 — Run PrivaStream reproducibly on supported hardware

## Actor
Developer / demo operator

## Story
As a developer or demo operator, I want to start PrivaStream reproducibly on a clean machine with documented CPU/GPU options so that the privacy behavior does not depend on undocumented local setup.

## Value
A hackathon/demo system is difficult to maintain if model artifacts, CUDA dependencies, ports, or startup steps differ per machine.

## Acceptance Criteria
- A clean checkout has documented commands to obtain required public model artifacts and verify checksums.
- Runtime models are selected by logical artifact/configuration identifiers rather than developer-specific absolute paths.
- A CPU-compatible profile exists where supported capabilities can run without NVIDIA hardware.
- An NVIDIA GPU profile uses pinned compatible runtime dependencies and exposes only required GPU devices.
- Model caches survive normal container restarts without committing large weights to Git.
- Missing/corrupt required models make privacy readiness fail explicitly.
- WebRTC/signaling ports and announced-IP behavior are documented.
- Process health is not confused with privacy readiness.

## Scope
- Model/dataset manifests as required for runtime reproducibility, bootstrap/cache, Docker images, Compose profiles, networking, environment configuration, and operations documentation.

## Out of Scope
- Cloud autoscaling/orchestration.
- Multi-region production deployment.
- Training every model from scratch.

## Decisions
- Pretrained baselines are valid when provenance/license are documented.
- Model downloads are checksum verified.
- CPU/GPU profiles share application contracts rather than separate implementations.

## Concerns
- GPU/CUDA/driver compatibility.
- Model artifact licenses and download availability.
- CPU performance may be insufficient for every real-time configuration.

## Status Boundary
Planned operational story until a clean-checkout CPU flow and the available GPU flow are validated.

## Touched By
Issues #2, #11, #14, #15, #16, #17.