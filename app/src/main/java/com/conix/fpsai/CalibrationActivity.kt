package com.conix.fpsai

import android.app.Activity
import android.content.Intent
import android.widget.*

class CalibrationActivity : Activity() {

    private fun field(hint: String, value: String) = EditText(this).apply {
        this.hint = hint
        setText(value)
        inputType = 8194 // number | decimal
    }

    // Built in onResume so values refresh after returning from the screenshot picker.
    override fun onResume() {
        super.onResume()
        build()
    }

    private fun build() {
        val game = ProfileStore.game(this)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(20, 24, 20, 20) }
        root.addView(TextView(this).apply { text = "Control calibration - $game"; textSize = 20f })
        root.addView(TextView(this).apply {
            text = "EASY WAY: take a LANDSCAPE screenshot inside the game (buttons visible), then tap the button below and tap each control on that screenshot. Or type X/Y by hand (0.0-1.0). Size = button radius (fraction of screen width, 0.005-0.5)."
            textSize = 13f
        })
        root.addView(Button(this).apply { text = "Calibrate by tapping on a game screenshot"; setOnClickListener {
            startActivity(Intent(this@CalibrationActivity, TapCalibrationActivity::class.java))
        } })

        for (key in ProfileStore.controlNames(this)) {
            val saved = ProfileStore.control(this, key)
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            row.addView(TextView(this).apply { text = key }, LinearLayout.LayoutParams(0, -2, 1.4f))
            val x = field("X", (saved?.first ?: 0.5f).toString())
            val y = field("Y", (saved?.second ?: 0.5f).toString())
            val r = field("Size", (saved?.third ?: 0.06f).toString())
            row.addView(x, LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(y, LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(r, LinearLayout.LayoutParams(0, -2, 1f))
            root.addView(row)

            val parse: () -> Triple<Float, Float, Float>? = {
                val xv = x.text.toString().toFloatOrNull()
                val yv = y.text.toString().toFloatOrNull()
                val rv = r.text.toString().toFloatOrNull()
                if (xv == null || yv == null || rv == null || xv !in 0f..1f || yv !in 0f..1f || rv !in 0.005f..0.5f) {
                    Toast.makeText(this, "Use X/Y 0-1 and size 0.005-0.5", Toast.LENGTH_SHORT).show()
                    null
                } else Triple(xv, yv, rv)
            }

            val btns = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            btns.addView(Button(this).apply { text = "Save"; setOnClickListener {
                val p = parse()
                if (p != null) {
                    ProfileStore.saveControl(this@CalibrationActivity, key, p.first, p.second, p.third)
                    Toast.makeText(this@CalibrationActivity, "Saved $key", Toast.LENGTH_SHORT).show()
                }
            } }, LinearLayout.LayoutParams(0, -2, 1f))
            btns.addView(Button(this).apply { text = "Test tap"; setOnClickListener {
                val p = parse()
                if (p != null) {
                    val svc = GameAccessibilityService.instance
                    if (svc == null) {
                        Toast.makeText(this@CalibrationActivity, "Enable Conix in Accessibility settings first", Toast.LENGTH_LONG).show()
                    } else {
                        svc.tapNormalized(p.first, p.second)
                        EventLogger.log(this@CalibrationActivity, "CALIBRATION_TEST_$key", p.first, p.second, "calibration")
                    }
                }
            } }, LinearLayout.LayoutParams(0, -2, 1f))
            btns.addView(Button(this).apply { text = "Remove"; setOnClickListener {
                ProfileStore.removeControl(this@CalibrationActivity, key)
                build()
            } }, LinearLayout.LayoutParams(0, -2, 1f))
            root.addView(btns)
        }

        val newCtl = EditText(this).apply { hint = "New control name, e.g. SPRINT or HEAL" }
        root.addView(newCtl)
        root.addView(Button(this).apply { text = "Add custom control"; setOnClickListener {
            val n = ProfileStore.addControl(this@CalibrationActivity, newCtl.text.toString())
            if (n == null) Toast.makeText(this@CalibrationActivity, "Type a control name first", Toast.LENGTH_SHORT).show()
            else build()
        } })
        root.addView(TextView(this).apply {
            text = "Each game profile keeps its own controls. Positions are saved automatically to a profile file that the ML training uses."
            textSize = 13f
        })
        setContentView(ScrollView(this).apply { addView(root) })
    }
}
