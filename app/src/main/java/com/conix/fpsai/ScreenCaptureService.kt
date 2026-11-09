package com.conix.fpsai

import android.app.*
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.MediaRecorder
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import android.util.DisplayMetrics
import android.view.WindowManager
import java.io.File

class ScreenCaptureService : Service() {
    companion object {
        const val START="START_CAPTURE"; const val STOP="STOP_CAPTURE"; const val CODE="result_code"; const val DATA="result_data"
        private const val CHANNEL="conix_capture"
    }
    private var projection: MediaProjection?=null
    private var recorder: MediaRecorder?=null
    private var display: VirtualDisplay?=null
    override fun onBind(intent: Intent?): IBinder?=null
    override fun onStartCommand(i: Intent?, flags: Int, id: Int): Int {
        if (i?.action==STOP) { stopCapture(); return START_NOT_STICKY }
        if (i?.action==START) startCapture(i)
        return START_NOT_STICKY
    }
    private fun startCapture(i: Intent) {
        if (Build.VERSION.SDK_INT>=26) {
            getSystemService(NotificationManager::class.java).createNotificationChannel(NotificationChannel(CHANNEL,"Gameplay capture",NotificationManager.IMPORTANCE_LOW))
        }
        val n=Notification.Builder(this,CHANNEL).setContentTitle("Conix FPS AI").setContentText("Recording with your permission").setSmallIcon(android.R.drawable.presence_video_online).build()
        if (Build.VERSION.SDK_INT>=29) startForeground(7,n,ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION) else startForeground(7,n)
        val data=if (Build.VERSION.SDK_INT>=33) i.getParcelableExtra(DATA,Intent::class.java) else @Suppress("DEPRECATION") i.getParcelableExtra(DATA)
        if (data==null) { stopSelf(); return }
        val mgr=getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        projection=mgr.getMediaProjection(i.getIntExtra(CODE,Activity.RESULT_CANCELED),data)
        val dm=DisplayMetrics(); @Suppress("DEPRECATION") (getSystemService(WINDOW_SERVICE) as WindowManager).defaultDisplay.getRealMetrics(dm)
        val dir=File(getExternalFilesDir(null),"demonstrations").apply { mkdirs() }
        val file=File(dir,"${ProfileStore.game(this).replace(" ","_")}_${System.currentTimeMillis()}.mp4")
        recorder=if (Build.VERSION.SDK_INT>=31) MediaRecorder(this) else @Suppress("DEPRECATION") MediaRecorder()
        try {
            recorder?.apply { setVideoSource(MediaRecorder.VideoSource.SURFACE); setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                setVideoEncoder(MediaRecorder.VideoEncoder.H264); setVideoSize(dm.widthPixels-(dm.widthPixels%2),dm.heightPixels-(dm.heightPixels%2))
                setVideoFrameRate(24); setVideoEncodingBitRate(4_000_000); setOutputFile(file.absolutePath); prepare() }
            display=projection?.createVirtualDisplay("ConixCapture",dm.widthPixels,dm.heightPixels,dm.densityDpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,recorder?.surface,null,null)
            recorder?.start()
        } catch (e: Exception) { stopCapture() }
    }
    private fun stopCapture() {
        try { recorder?.stop() } catch (_:Exception) {}
        display?.release(); display=null
        try { recorder?.reset(); recorder?.release() } catch (_:Exception) {}
        recorder=null; projection?.stop(); projection=null
        stopForeground(STOP_FOREGROUND_REMOVE); stopSelf()
    }
    override fun onDestroy() { if (projection!=null) stopCapture(); super.onDestroy() }
}
