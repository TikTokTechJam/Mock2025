# User Stories

## Purpose

These documents record approved user outcomes and planning intent. They are not the source of current implementation behavior.

Implementation issues can touch multiple user stories, and a technical issue is not automatically a separate user story. This directory groups the work by stable user/developer outcome so future issues can be planned without duplicating stories.

## Story Structure

Each story states the actor, desired outcome, value, acceptance criteria, scope, out-of-scope work, decisions, concerns, status boundary, and the issues that currently touch it.

## Touched Story Index

| ID | Story | Primary actor | Main issue coverage |
| --- | --- | --- | --- |
| [US-0001](US-0001-protected-media-session.md) | Start a protected media session | Creator | #2, #3, #4, #11, #12, #13, #17, #21, #22 |
| [US-0002](US-0002-creator-enrollment.md) | Enroll and manage creator identity | Creator | #3, #5, #12, #17, #18, #22 |
| [US-0003](US-0003-bystander-face-protection.md) | Protect non-creator faces | Creator | #3, #4, #5, #13, #15, #17, #18 |
| [US-0004](US-0004-license-plate-protection.md) | Protect visible license plates | Creator | #3, #4, #6, #13, #14, #15, #17, #19, #48, #49 |
| [US-0005](US-0005-visual-pii-protection.md) | Protect visual PII | Creator | #3, #4, #7, #13, #14, #15, #17, #19, #32 |
| [US-0006](US-0006-spoken-pii-protection.md) | Protect spoken PII | Creator | #3, #8, #9, #10, #11, #13, #14, #15, #17, #20, #32 |
| [US-0007](US-0007-av-sensitive-speech-protection.md) | Synchronize sensitive speech with visual protection | Creator | #4, #5, #9, #10, #13, #15, #17 |
| [US-0008](US-0008-protected-preview-readiness.md) | Inspect protected live preview and readiness | Creator | #2, #3, #5, #11, #12, #13, #17, #21, #22 |
| [US-0009](US-0009-panic-fail-closed.md) | Trigger panic mode and fail closed | Creator | #3, #4, #8-#13, #16, #17, #21, #22 |
| [US-0010](US-0010-reproducible-runtime.md) | Run PrivaStream reproducibly on supported hardware | Developer / operator | #2, #11, #14-#17, #21 |
| [US-0011](US-0011-benchmark-privacy-performance.md) | Evaluate privacy quality and performance | Developer / evaluator | #5-#7, #9, #10, #14-#17, #32, #48, #49 |
| [US-0012](US-0012-complete-privastream-demo.md) | Run the complete PrivaStream demonstration | Creator / operator | #1, #2, #5-#7, #9-#13, #15-#17, #21, #22 |
| [US-0013](US-0013-improve-license-plate-detector.md) | Benchmark, train, and improve the license-plate detector | ML teammate / evaluator | #14, #15, #48, #49 |

## Issue-to-Story Map

Use this when reviewing the implementation backlog. It shows which stable outcomes each issue advances. The backlog keeps ML work separate from backend/infrastructure work.

| Issue | User stories touched |
| --- | --- |
| #2 Foundation/rebrand + architecture | US-0001, US-0008, US-0010, US-0012 |
| #3 Privacy taxonomy/lifecycle/contracts | US-0001, US-0002, US-0003, US-0004, US-0005, US-0006, US-0009 |
| #4 Shared video orchestration/temporal masking/compositor | US-0001, US-0003, US-0004, US-0005, US-0007, US-0009 |
| #5 Face production integration | US-0002, US-0003, US-0008, US-0011, US-0012 |
| #6 Plate production integration | US-0004, US-0011, US-0012 |
| #7 OCR/visual-PII production integration | US-0005, US-0011, US-0012 |
| #8 VAD/transcription production audio integration | US-0006, US-0009 |
| #9 Spoken-PII production integration | US-0006, US-0007, US-0011, US-0012 |
| #10 A/V synchronized privacy | US-0007, US-0009, US-0011, US-0012 |
| #11 Production privacy-to-WebRTC integration | US-0001, US-0006, US-0008, US-0009, US-0010, US-0012 |
| #12 Production creator-console client integration | US-0001, US-0002, US-0008, US-0009, US-0012 |
| #13 Privacy readiness/panic/fail-closed gate | US-0001, US-0003-0009, US-0012 |
| #14 Model-artifact handoff, download/cache, and runtime path resolution | US-0004, US-0005, US-0006, US-0010, US-0011, US-0013 |
| #15 Evaluation tooling and standard metrics | US-0003-0007, US-0010, US-0011, US-0012, US-0013 |
| #16 CPU/GPU deployment packaging | US-0009, US-0010, US-0011, US-0012 |
| #17 Complete E2E verification | US-0001 through US-0012 |
| #18 Face source implementation | US-0002, US-0003 |
| #19 Completed plate + visual-PII source module | US-0004, US-0005 |
| #20 Completed VAD/transcription/spoken-PII source module | US-0006 |
| #21 Reusable WebRTC transport with mocks | US-0001, US-0008, US-0009, US-0010, US-0012 |
| #22 Creator-console UI shell with mock clients | US-0001, US-0002, US-0008, US-0009, US-0012 |
| #32 Shared text-PII recognizer | US-0005, US-0006, US-0011 |
| #48 ML plate baseline evaluation | US-0004, US-0011, US-0013 |
| #49 ML plate fine-tuning and best-model handoff | US-0004, US-0011, US-0013 |

## US-0013 role boundary

For the plate-model story, ownership is intentionally simple:

```text
BACKEND / INFRA
#15 provides evaluation tooling
        ↓
ML
#48 measures the current model
        ↓
#49 trains/fine-tunes and selects the best model
        ↓
BACKEND / INFRA
#14 makes the finished model artifact reproducibly loadable by the app
        ↓
#16 packages the runtime
```

ML teammates are expected to work with data, labels, training, evaluation, failure analysis, and model artifacts. They are not expected to implement application/backend infrastructure for US-0013.

## Planning Boundary

Approval of a story does not make a capability Implemented or Verified. Use the authoritative domain documents for current behavior and use the issue or approved solution for implementation scope.

The current touched-story range is **US-0001 through US-0013**. The next genuinely new user outcome should start at **US-0014** unless it is better represented as additional scope or acceptance criteria for an existing story.

Before creating US-0014+, check this index first. If a proposed issue only implements part of an existing outcome, link it to that story instead of creating a duplicate user story.

## Maintenance

Keep stories focused and independently reviewable. Do not rewrite historical requirements to claim implementation, and do not turn this directory into a completed-work diary.

When a new issue is added:
1. decide whether it advances an existing user story;
2. identify the issue that exclusively owns the implementation concern;
3. keep `[ML]` work separate from backend/infrastructure implementation where team ownership differs;
4. add the issue to the relevant story's `Touched By` section and this map;
5. create a new US file only when the actor/outcome/value is genuinely new;
6. use the next sequential US identifier for new stories.
