# ML training (Google Colab, no terminal)
1. In the app: Developer options -> **Show taps ON**. Record gameplay.
2. Copy BOTH `Game_session.mp4` and `Game_session.profile.json` to Google Drive: `ConixData/<Game_Name>/`.
3. Open `Conix_Training.ipynb` in Google Colab (upload it), choose a T4 GPU, run cells top to bottom.
4. Output: `policy.pt`, `policy_ts.pt` (TorchScript), `model_report.json` (held-out precision/recall/F1 per control).

How it works: see the docstring in `conix_pipeline.py`. Taps are read from the visible "Show taps" dots in each calibrated
control's screen region; the control regions are greyed out in the model input so it cannot cheat by reading the dots.
Not included yet: aim/look (camera drag) labels, on-device inference, autonomous control.
