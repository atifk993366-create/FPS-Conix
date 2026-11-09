package com.conix.fpsai

import android.content.Context
import android.os.SystemClock
import java.io.File

/**
 * Writes timestamped events to demonstrations/actions.csv.
 * timestamp_ms uses SystemClock.elapsedRealtime() (monotonic). RECORD_START is logged at the
 * exact moment video recording starts, so frame_time = event.timestamp_ms - RECORD_START.timestamp_ms.
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
        val file = File(dir, "actions.csv")
        if (!file.exists()) {
            file.writeText("session_id,game_profile_id,timestamp_ms,action_name,x_norm,y_norm,screen_width,screen_height,profile_version,label_source\n")
        }
        val game = ProfileStore.game(c).replace(",", " ")
        file.appendText("$sessionId,$game,${SystemClock.elapsedRealtime()},$event,${x ?: ""},${y ?: ""},$screenW,$screenH,$PROFILE_VERSION,$source\n")
    }
}
