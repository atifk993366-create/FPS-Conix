package com.conix.fpsai

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.*

/** Shows a landscape game screenshot; the user taps each control in turn. */
class TapCalibrationActivity : Activity() {
    private val REQ_IMG = 2001
    private lateinit var cal: CalView
    private lateinit var label: TextView
    private var names: List<String> = emptyList()
    private var idx = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN)
        names = ProfileStore.controlNames(this)

        cal = CalView(this)
        label = TextView(this).apply {
            setTextColor(Color.WHITE); setBackgroundColor(0xAA000000.toInt()); textSize = 16f; setPadding(16, 8, 16, 8)
        }
        val bar = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setBackgroundColor(0xAA000000.toInt()) }
        bar.addView(Button(this).apply { text = "Back"; setOnClickListener { idx = maxOf(0, idx - 1); showCurrent() } })
        bar.addView(Button(this).apply { text = "Skip"; setOnClickListener { idx++; showCurrent() } })
        bar.addView(Button(this).apply { text = "Done"; setOnClickListener { finish() } })

        val frame = FrameLayout(this)
        frame.addView(cal, FrameLayout.LayoutParams(-1, -1))
        frame.addView(label, FrameLayout.LayoutParams(-2, -2, Gravity.TOP or Gravity.CENTER_HORIZONTAL))
        frame.addView(bar, FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL))
        setContentView(frame)

        cal.onTap = { x, y -> handleTap(x, y) }
        label.text = "Pick a landscape screenshot of the game..."

        val pick = Intent(Intent.ACTION_GET_CONTENT).apply { type = "image/*"; addCategory(Intent.CATEGORY_OPENABLE) }
        @Suppress("DEPRECATION")
        startActivityForResult(Intent.createChooser(pick, "Pick a LANDSCAPE game screenshot"), REQ_IMG)
    }

    private fun handleTap(x: Float, y: Float) {
        if (cal.bitmap == null || idx >= names.size) return
        val name = names[idx]
        val old = ProfileStore.control(this, name)
        ProfileStore.saveControl(this, name, x.coerceIn(0f, 1f), y.coerceIn(0f, 1f), old?.third ?: 0.06f)
        idx++
        showCurrent()
    }

    private fun showCurrent() {
        cal.marks = names.mapNotNull { n -> ProfileStore.control(this, n)?.let { Triple(n, it.first, it.second) } }
        if (idx >= names.size) {
            label.text = "All controls done. Press Done."
        } else {
            label.text = "Tap the ${names[idx]} button  (${idx + 1}/${names.size})"
        }
        cal.invalidate()
    }

    @Suppress("DEPRECATION")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQ_IMG) return
        val uri = data?.data
        if (resultCode != RESULT_OK || uri == null) { finish(); return }
        val b = loadBitmap(uri)
        if (b == null) {
            Toast.makeText(this, "Could not open that image", Toast.LENGTH_LONG).show(); finish(); return
        }
        if (b.height > b.width) {
            Toast.makeText(this, "That screenshot is portrait. Take it with the game in LANDSCAPE.", Toast.LENGTH_LONG).show(); finish(); return
        }
        cal.bitmap = b
        idx = 0
        showCurrent()
    }

    private fun loadBitmap(uri: Uri): Bitmap? {
        return try {
            val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, opts) }
            var sample = 1
            while (opts.outWidth / sample > 2400 || opts.outHeight / sample > 2400) sample *= 2
            val o2 = BitmapFactory.Options().apply { inSampleSize = sample }
            contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, o2) }
        } catch (e: Exception) {
            null
        }
    }
}

private class CalView(ctx: Context) : View(ctx) {
    var bitmap: Bitmap? = null
    var marks: List<Triple<String, Float, Float>> = emptyList()
    var onTap: ((Float, Float) -> Unit)? = null
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val b = bitmap
        if (b != null) canvas.drawBitmap(b, Rect(0, 0, b.width, b.height), Rect(0, 0, width, height), null)
        else canvas.drawColor(Color.BLACK)
        paint.color = Color.RED
        paint.textSize = 28f
        for (m in marks) {
            val cx = m.second * width
            val cy = m.third * height
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = 4f
            canvas.drawCircle(cx, cy, 0.03f * width, paint)
            paint.style = Paint.Style.FILL
            canvas.drawText(m.first, cx + 0.035f * width, cy, paint)
        }
    }

    override fun onTouchEvent(e: MotionEvent): Boolean {
        if (e.action == MotionEvent.ACTION_UP && width > 0 && height > 0) {
            onTap?.invoke(e.x / width, e.y / height)
            performClick()
        }
        return true
    }

    override fun performClick(): Boolean = super.performClick()
}
