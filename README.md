# Conix FPS AI — Universal Android starter (v0.3.0)

Supports separate profile names for **FPS Strike Ops** and **Cover Fire**, user-entered normalized control coordinates, explicit Android screen-capture consent, timestamped event CSV logging, and a user-enabled AccessibilityService gesture foundation. Includes an ML data preparation and behavior-cloning starter pipeline.

## Build APK
GitHub Actions workflow: `.github/workflows/build-apk.yml`
1. Upload the extracted project contents to a GitHub repository.
2. Open Actions and run **Build Conix FPS AI APK**.
3. Download `conix-fps-ai-debug-apk` artifact.

Requirements: JDK 17, Gradle 8.9, Android Gradle Plugin 8.7.3, Kotlin 2.0.21, Android API 35.

## Current functionality vs future work
Working foundation: profile selection, coordinate calibration storage, explicit screen capture, event CSV logger, AccessibilityService declaration and gesture method, ML scripts.
Not complete: automatic reading of arbitrary gameplay touch events, live vision model, synchronized automatic joystick recording, trained policy, autonomous match orchestration, on-device model inference, visual overlay calibration. Those require device-specific integration and validation.

## Safety / permissions
Screen capture uses Android's system consent prompt. Gesture dispatch requires the user to manually enable Conix FPS AI under Android Accessibility settings. Use only in offline game modes where automation is permitted. A visible stop mechanism and user supervision should be retained during testing.
