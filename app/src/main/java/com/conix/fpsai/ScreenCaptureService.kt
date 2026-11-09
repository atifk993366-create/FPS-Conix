package com.conix.fpsai

import android.app.Activity
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.drawable.Icon
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.MediaRecorder
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.DisplayMetrics
import android.view.WindowManager
import java.io.File

class ScreenCaptureService : Service() {
    companion object {
        const val START = "START_CAPTURE"
        const val STOP = "STOP_CAPTURE"
        const val CODE = "result_code"
        const val DATA = "result_data"
        private const val CHANNEL = "conix_capture"
    }

    private var projection: MediaProjection? = null
    private var recorder: MediaRecorder? = null
    private var display: VirtualDisplay? = null
    private var active = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(i: Intent?, flags: Int, id: Int): Int {
        if (i?.action == START) startCapture(i)
        else if (i?.action == STOP) stopCapture()
        else stopSelf()
        return START_NOT_STICKY
    }

    private fun buildNotification(): Notification {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, "Gameplay capture", NotificationManager.IMPORTANCE_LOW))
        val stopPi = PendingIntent.getService(
            this, 1, Intent(this, ScreenCaptureService::class.java).setAction(STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val stopAction = Notification.Action.Builder(
            Icon.createWithResource(this, android.R.drawable.ic_media_pause), "STOP", stopPi
        ).build()
        return Notification.Builder(this, CHANNEL)
            .setContentTitle("Conix FPS AI")
            .setContentText("Recording with your permission")
            .setSmallIcon(android.R.drawable.presence_video_online)
            .setOngoing(true)
            .addAction(stopAction)
            .build()
    }

    @Suppress("DEPRECATION")
    private fun startCapture(i: Intent) {
        if (active) return
        val n = buildNotification()
        if (Build.VERSION.SDK_INT >= 29) startForeground(7, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        else startForeground(7, n)

        val data: Intent? = if (Build.VERSION.SDK_INT >= 33) i.getParcelableExtra(DATA, Intent::class.java)
        else i.getParcelableExtra<Intent>(DATA)
        if (data == null) { stopCapture(); return }

        val mgr = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        val proj = mgr.getMediaProjection(i.getIntExtra(CODE, Activity.RESULT_CANCELED), data)
        if (proj == null) { stopCapture(); return }
        projection = proj
        // Required on Android 14+: register a callback before creating the virtual display.
        proj.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() { stopCapture() }
        }, Handler(Looper.getMainLooper()))

        val dm = DisplayMetrics()
        (getSystemService(WINDOW_SERVICE) as WindowManager).defaultDisplay.getRealMetrics(dm)
        // Games are landscape: always record landscape-sized frames (long side = width).
        val w = maxOf(dm.widthPixels, dm.heightPixels).let { it - it % 2 }
        val h = minOf(dm.widthPixels, dm.heightPixels).let { it - it % 2 }

        val dir = File(getExternalFilesDir(null), "demonstrations").apply { mkdirs() }
        EventLogger.newSession()
        EventLogger.screenW = w
        EventLogger.screenH = h
        val file = File(dir, "${ProfileStore.game(this).replace(" ", "_")}_${EventLogger.sessionId}.mp4")
        val rec = if (Build.VERSION.SDK_INT >= 31) MediaRecorder(this) else MediaRecorder()
        recorder = rec
        try {
            rec.setVideoSource(MediaRecorder.VideoSource.SURFACE)
            rec.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            rec.setVideoEncoder(MediaRecorder.VideoEncoder.H264)
            rec.setVideoSize(w, h)
            rec.setVideoFrameRate(24)
            rec.setVideoEncodingBitRate(4_000_000)
            rec.setOutputFile(file.absolutePath)
            rec.prepare()
            display = proj.createVirtualDisplay(
                "ConixCapture", w, h, dm.densityDpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, rec.surface, null, null
            )
            rec.start()
            active = true
            EventLogger.log(this, "RECORD_START", source = "system")
        } catch (e: Exception) {
            stopCapture()
        }
    }

    private fun stopCapture() {
        if (active) EventLogger.log(this, "RECORD_STOP", source = "system")
        active = false
        try { recorder?.stop() } catch (_: Exception) {}
        display?.release(); display = null
        try { recorder?.reset(); recorder?.release() } catch (_: Exception) {}
        recorder = null
        val p = projection
        projection = null
        try { p?.stop() } catch (_: Exception) {}
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        if (projection != null || recorder != null) stopCapture()
        super.onDestroy()
    }
}
