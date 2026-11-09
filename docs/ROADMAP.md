# Conix FPS AI — Universal implementation roadmap

## Profiles
- Separate profiles for FPS Strike Ops and Cover Fire.
- User manually calibrates normalized positions for joystick, fire, ADS/scope, reload, jump, crouch, left/right, weapon switch, grenade.
- Profiles are independent; never assume identical HUD layouts or touch semantics.

## Phase 1 — Android foundation
Project shell, explicit permissions, screen capture service, app-specific demonstration storage.

## Phase 2 — Calibration
Normalized coordinates per game profile. Add a visual calibration screen and confirm every control manually in the target game's training/offline mode.

## Phase 3 — Demonstration capture
Record screen video plus timestamped user-labelled events. For genuine imitation learning, labels must be synchronized with frames. The starter app offers event logging; raw touches inside another app are not generally readable by normal Android apps.

## Phase 4 — Dataset
Extract frames, align labels by monotonic timestamps, split by match/session (not random adjacent frames), inspect label balance, redact personal notifications.

## Phase 5 — Vision
Train/validate detection for enemies, friendly units, crosshair, health, ammo, objective markers and relevant HUD. Per-game HUD profiles may be needed.

## Phase 6 — Behavioral cloning
Start with a small discrete action space. Add continuous joystick/camera outputs only after reliable synchronized input labels exist. Evaluate held-out matches.

## Phase 7 — Safe autonomous control
User explicitly enables Android Accessibility service. Use only visible, user-configured controls in offline environments where automation is permitted. Add a kill switch, action-rate limits and a foreground status indicator. Never attempt anti-cheat evasion.

## Phase 8 — Reinforcement learning
Prefer a custom simulator or game-provided training API. Avoid uncontrolled self-training in a live third-party game. Use reward shaping, episode limits and regression tests.

## Phase 9 — On-device inference
Convert a validated model to a mobile runtime (e.g. LiteRT/TFLite or ONNX Runtime Mobile). Profile latency, heat, battery and memory on the target phone.

## Phase 10 — Evaluation
Measure task completion, survival, missed detections, unnecessary actions, latency, crash rate and performance by map/weapon/profile. Keep a human-approved rollback model.

## Phase 11 — UI and packaging
Dashboard, profiles, data export/delete, training status, model version, permissions status and APK release.

## Important reality checks
- 2–3 matches are a proof-of-concept dataset, not enough to generalize to all maps and encounters.
- Video-only learning cannot infer exact joystick/button actions reliably.
- Accessibility gesture dispatch is device/game dependent and may not work with every game or protected surface.
- This project does not guarantee that third-party games permit automation. Use offline modes and check each game's rules.
- The included code is a multi-phase starter foundation, not a finished trained AI or verified universal controller.
