package com.conix.fpsai

import android.content.Context
import android.os.SystemClock
import java.io.File

/**
 * Writes timestamped events to demonstrations/events.csv.
 * uptime_ms = SystemClock.uptimeMillis() = the same clock as the Linux input-event timestamps printed by
 * `adb shell getevent -t`, so touch logs from the PC can be aligned exactly with the screen recording.
 * RECORD_START is logged at the moment video recording starts.
 */
object EventLogger {
    const val PROFILE_VERSION = 1
    @Volatile var sessionId: String = "none"
    @Volatile var screenW: Int = 0
    @Volatile var screenH: Int = 0

    fun newSession() { sessionId = "s" + System.currentTimeMillis() }

    @Synchronized
    fun log(c: Context, event: String, x: Float? = null, y: Float? = null, source: String = "app") {
        val dir = File(c.getExternalFilesDir(null), "demonstrations").apply { mkdirs() }
        val file = File(dir, "events.csv")
        if (!file.exists()) {
            file.writeText("session_id,game_profile_id,timestamp_ms,uptime_ms,action_name,x_norm,y_norm,screen_width,screen_height,profile_version,label_source\n")
        }
        val game = ProfileStore.game(c).replace(",", " ")
        file.appendText("$sessionId,$game,${SystemClock.elapsedRealtime()},${SystemClock.uptimeMillis()},$event,${x ?: ""},${y ?: ""},$screenW,$screenH,$PROFILE_VERSION,$source\n")
    }
}
