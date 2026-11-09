package com.conix.fpsai

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.view.accessibility.AccessibilityEvent

class GameAccessibilityService : AccessibilityService() {
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}
    override fun onInterrupt() {}

    // Explicitly invoked only by a user-approved app action. Coordinates are normalized 0..1.
    fun tapNormalized(x: Float, y: Float, durationMs: Long = 90L, callback: (() -> Unit)? = null) {
        val dm = resources.displayMetrics
        val path = Path().apply { moveTo(x.coerceIn(0f,1f)*dm.widthPixels, y.coerceIn(0f,1f)*dm.heightPixels) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, durationMs.coerceIn(40L, 500L)))
            .build()
        dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) { callback?.invoke() }
        }, null)
    }
}
