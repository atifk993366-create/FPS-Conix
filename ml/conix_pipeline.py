"""
Conix FPS AI - dataset builder + behaviour-cloning trainer (v0.5)

How labels are made (no root, no PC needed):
  1. In Android Developer options the user turns ON "Show taps".
  2. The Conix app records the screen, so the translucent round tap-dot is visible in the video.
  3. For every calibrated control we look at that control's screen region and compare it with how the
     region normally looks (median over the video). A tap-dot is a ROUND, compact, brighter, low-colour blob of a
     typical size. Scene noise (explosions, moving objects) is rejected by size / roundness / fill checks.
  4. Detection settings (brightness gain, dot size) are chosen AUTOMATICALLY by trying a small grid and keeping the
     one that gives plausible press rates. If nothing looks plausible, labels are flagged unreliable and training refuses.
  5. Joystick finger offset gives a move direction (stick_x, stick_y).
The model input hides every control region (grey box), so the model cannot "read" the tap-dots.

Limits: no real-footage tuning was possible. Always look at the printed pressed-% table and the label timeline.
Camera/aim (look) labels are not included yet.
"""
import argparse, glob, json, os, sys
import numpy as np
import cv2

AW, AH = 480, 270      # analysis resolution (label detection)
MW, MH = 256, 144      # model input resolution
STICK_SCALE = 2.5      # stick search region = r * this
BTN_SCALE = 1.5
MASK_SCALE = 1.7       # grey-out region in model input = r * this (stick: *1.4 more)
KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
GAIN_GRID = (20, 30, 45)
DOT_GRID = (0.018, 0.025, 0.035)   # tap-dot radius as fraction of frame width


def is_stick(name):
    n = name.upper()
    return "JOYSTICK" in n or n in ("MOVE", "STICK", "MOVEMENT")


def load_profile(path):
    with open(path, "r", encoding="utf-8") as f:
        p = json.load(f)
    controls = [c for c in p.get("controls", []) if all(k in c for k in ("name", "x", "y", "r"))]
    if not controls:
        raise ValueError("Is profile mein koi calibrated control nahi hai (" + os.path.basename(path) + "). App mein: game select karo > Open control calibration > har control SAVE karo (ya screenshot par tap karo) > Show taps ON karke NAYI recording karo.")
    return p, controls


def box(c, W, H, scale):
    r = c["r"] * W * scale
    cx, cy = c["x"] * W, c["y"] * H
    x0, x1 = int(max(0, cx - r)), int(min(W, cx + r))
    y0, y1 = int(max(0, cy - r)), int(min(H, cy + r))
    if x1 - x0 < 4: x1 = min(W, x0 + 4)
    if y1 - y0 < 4: y1 = min(H, y0 + 4)
    return x0, y0, x1, y1


def iter_frames(video, target_fps, size):
    """Yields (time_seconds, resized_BGR_frame) at about target_fps. Uses the real frame timestamps
    (screen recordings are variable-frame-rate, so index/fps would drift)."""
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise IOError("Cannot open video: " + video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    period = 1.0 / target_fps
    next_t = 0.0
    i = 0
    while True:
        if not cap.grab():
            break
        ts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        if ts <= 0 and i > 0:
            ts = i / fps               # codec gave no timestamps
        if ts >= next_t - 1e-6:
            ok, f = cap.retrieve()
            if not ok:
                break
            yield ts, cv2.resize(f, size, interpolation=cv2.INTER_AREA)
            next_t += period
            if next_t <= ts:
                next_t = ts + period
        i += 1
    cap.release()


def preview_video(video, profile_path, n=4):
    """Returns n RGB frames (evenly spaced) with every calibrated control box drawn. Use it to check that
    (a) the boxes sit on the real buttons and (b) tap-dots are visible in the recording."""
    _, controls = load_profile(profile_path)
    cap = cv2.VideoCapture(video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out = []
    for k in range(n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((k + 0.5) * total / n))
        ok, fr = cap.read()
        if not ok:
            continue
        fr = cv2.resize(fr, (960, 540))
        for c in controls:
            x0, y0, x1, y1 = box(c, 960, 540, STICK_SCALE if is_stick(c["name"]) else BTN_SCALE)
            cv2.rectangle(fr, (x0, y0), (x1, y1), (0, 0, 255), 2)
            cv2.putText(fr, c["name"], (x0, max(12, y0 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        out.append(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
    cap.release()
    return out


# ------------------------------------------------------------------ tap-dot detection
def _blob(m, min_a, max_a):
    """Find a round, compact blob of plausible size. Returns centroid (x, y) or None."""
    n, lab, st, cen = cv2.connectedComponentsWithStats(m, connectivity=8)
    best, best_a = None, 0
    for k in range(1, n):
        a = int(st[k, cv2.CC_STAT_AREA])
        if a < min_a or a > max_a:
            continue
        w = int(st[k, cv2.CC_STAT_WIDTH]); h = int(st[k, cv2.CC_STAT_HEIGHT])
        if not (0.55 <= w / max(h, 1) <= 1.8):
            continue
        if a / float(w * h) < 0.55:      # a disk fills ~78% of its bounding box
            continue
        if a > best_a:
            best, best_a = k, a
    return None if best is None else (float(cen[best][0]), float(cen[best][1]))


def _press(g, s, base, gain_thr, sat_thr, min_a, max_a):
    gain = g.astype(np.float32) - base
    gain -= float(np.median(gain))                 # ignore whole-region flashes / brightness changes
    gain = cv2.GaussianBlur(gain, (0, 0), 1.5)
    m = ((gain > gain_thr) & (s < sat_thr)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, KERNEL)
    return _blob(m, min_a, max_a)


def _detect(G, S, base, C, cfg, sat_thr, idxs):
    gain_thr, dot_r = cfg
    exp_a = np.pi * (dot_r * AW) ** 2
    min_a, max_a = 0.35 * exp_a, 3.5 * exp_a
    n = len(idxs)
    pr = np.zeros((n, C), bool); cx = np.zeros((n, C), np.float32); cy = np.zeros((n, C), np.float32)
    for j in range(C):
        for k, i in enumerate(idxs):
            r = _press(G[j][i], S[j][i], base[j], gain_thr, sat_thr, min_a, max_a)
            if r is not None:
                pr[k, j] = True; cx[k, j], cy[k, j] = r
    return pr, cx, cy


def _plausible(rates, names):
    ok = 0
    for r, n in zip(rates, names):
        lo, hi = (0.02, 0.90) if is_stick(n) else (0.002, 0.45)
        if lo <= r <= hi:
            ok += 1
    return ok


def build_session(video, profile_path, out_npz, fps=10, gain_thr=None, dot_r=None, sat_thr=80, smooth=True):
    """Video + profile json -> npz with frames, targets. Returns a report dict."""
    prof, controls = load_profile(profile_path)
    names = [c["name"] for c in controls]
    C = len(names)
    boxes_a = [box(c, AW, AH, STICK_SCALE if is_stick(c["name"]) else BTN_SCALE) for c in controls]
    mask_boxes = [box(c, MW, MH, MASK_SCALE * (1.4 if is_stick(c["name"]) else 1.0)) for c in controls]
    G = [[] for _ in controls]; S = [[] for _ in controls]; frames = []; times = []
    for t, fr in iter_frames(video, fps, (AW, AH)):
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        s = cv2.cvtColor(fr, cv2.COLOR_BGR2HSV)[:, :, 1]
        for j, (x0, y0, x1, y1) in enumerate(boxes_a):
            G[j].append(g[y0:y1, x0:x1].copy()); S[j].append(s[y0:y1, x0:x1].copy())
        small = cv2.cvtColor(cv2.resize(fr, (MW, MH), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        for (x0, y0, x1, y1) in mask_boxes:
            small[y0:y1, x0:x1] = 128
        frames.append(small); times.append(t)
    N = len(frames)
    if N < 10:
        raise ValueError("Video mein bahut kam frames: " + video)
    G = [np.stack(x) for x in G]; S = [np.stack(x) for x in S]
    base = [np.median(G[j][::3].astype(np.float32), axis=0) for j in range(C)]

    if gain_thr is not None and dot_r is not None:
        configs = [(float(gain_thr), float(dot_r))]
    else:
        configs = [(g_, d_) for g_ in GAIN_GRID for d_ in DOT_GRID]
    sub = np.arange(0, N, 3)
    best = None
    for cfg in configs:
        pr_s, _, _ = _detect(G, S, base, C, cfg, sat_thr, sub)
        rates = pr_s.mean(0)
        score = 10 * _plausible(rates, names) - float(rates.sum())
        if best is None or score > best[0]:
            best = (score, cfg)
    cfg = best[1]
    pr, cx, cy = _detect(G, S, base, C, cfg, sat_thr, np.arange(N))

    targets = np.zeros((N, C + 2), np.float32)
    targets[:, :C] = pr.astype(np.float32)
    stick_j = next((j for j, n in enumerate(names) if is_stick(n)), None)
    if stick_j is not None:
        x0, y0, x1, y1 = boxes_a[stick_j]
        hw, hh = (x1 - x0) / 2.0, (y1 - y0) / 2.0
        on = pr[:, stick_j]
        targets[on, C] = np.clip((cx[on, stick_j] - hw) / hw, -1, 1)
        targets[on, C + 1] = np.clip((cy[on, stick_j] - hh) / hh, -1, 1)
    if smooth and N >= 3:  # 3-sample majority filter on the pressed flags
        p = np.pad(targets[:, :C], ((1, 1), (0, 0)), mode="edge")
        targets[:, :C] = ((p[:-2] + p[1:-1] + p[2:]) >= 2).astype(np.float32)
        if stick_j is not None:
            targets[targets[:, stick_j] < 0.5, C:] = 0.0
    rates = {n: float(targets[:, j].mean()) for j, n in enumerate(names)}
    warn = [n for n in names if not (0.002 <= rates[n] <= 0.45) and not is_stick(n)] + \
           [n for n in names if is_stick(n) and rates[n] > 0.90]
    np.savez_compressed(
        out_npz, frames=np.stack(frames), targets=targets, t=np.array(times, np.float32),
        names=np.array(names), profile=np.array(json.dumps(prof)),
        params=np.array(json.dumps(dict(fps=fps, gain_thr=cfg[0], dot_r=cfg[1], sat_thr=sat_thr))))
    return dict(video=os.path.basename(video), frames=int(N), pressed_rate=rates, params=dict(gain_thr=cfg[0], dot_r=cfg[1]), suspicious=warn)


def _fingerprint(path):
    import hashlib
    size = os.path.getsize(path)
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read(2_000_000))
        f.seek(max(0, size - 2_000_000))
        h.update(f.read(2_000_000))
    return (size, h.hexdigest())


def build_dataset(data_dir, out_dir, **kw):
    os.makedirs(out_dir, exist_ok=True)
    if not os.path.isdir(data_dir):
        raise FileNotFoundError("Folder nahi mila: " + data_dir + "  (Drive mein ConixData/<GAME>/ banao aur GAME naam theek karo)")
    videos = sorted(glob.glob(os.path.join(data_dir, "*.mp4")))
    print("Folder:", data_dir)
    print("Files:", sorted(os.listdir(data_dir)))
    if not videos:
        raise FileNotFoundError("Is folder mein koi .mp4 nahi hai. Phone se recording (.mp4) yahan copy karo.")
    fallback = sorted(glob.glob(os.path.join(data_dir, "profile_*.json")), key=os.path.getmtime)
    seen, uniq = {}, []
    for v in videos:
        fp = _fingerprint(v)
        if fp in seen:
            print("SKIP DUPLICATE: %s ek hi video hai jaisa %s (same file dobara copy hui). Drive se hata do." % (os.path.basename(v), os.path.basename(seen[fp])))
            continue
        seen[fp] = v; uniq.append(v)
    videos = uniq
    for old_npz in glob.glob(os.path.join(out_dir, "*.npz")):   # purane run ki bachi files hatao
        os.remove(old_npz)
    print("Alag-alag recordings:", len(videos))
    reports = []
    for v in videos:
        stem = v[:-4]
        pj = stem + ".profile.json"
        if not os.path.exists(pj):
            if fallback:
                pj = fallback[-1]
                print("NOTE: %s ki apni .profile.json nahi mili, %s use kar raha hoon" % (os.path.basename(v), os.path.basename(pj)))
            else:
                print("SKIP %s: iske saath wali .profile.json nahi mili" % os.path.basename(v)); continue
        out = os.path.join(out_dir, os.path.basename(stem) + ".npz")
        print("Building", os.path.basename(v), "(auto-settings dhoondh raha hoon, 1-3 min)...")
        rep = build_session(v, pj, out, **kw)
        print("  frames:", rep["frames"], "| chosen settings:", rep["params"])
        for n, r in rep["pressed_rate"].items():
            flag = "   <-- SUSPICIOUS" if n in rep["suspicious"] else ""
            print("  %-16s pressed %5.1f%% of frames%s" % (n, 100 * r, flag))
        if rep["suspicious"]:
            print("  WARNING: kuch controls ke labels bharosemand nahi lagte (hamesha ya kabhi nahi pressed).")
            print("  Check: Show taps ON tha? Calibration boxes sahi button par hain? (cell 2b ka preview dekho)")
        reports.append(rep)
    if not reports:
        raise FileNotFoundError(
            "Koi recording use nahi hui. Har .mp4 ke saath same naam ki .profile.json chahiye "
            "(jaise Cover_Fire_s123.mp4 + Cover_Fire_s123.profile.json).")
    return reports


# ------------------------------------------------------------------ EXACT labels from real touch events (adb getevent)
import re, csv as _csv
_EV = re.compile(r"^\[\s*(\d+\.\d+)\]\s+(\S+):\s+(\S+)\s+(\S+)\s+([0-9a-fA-F]+)\s*$")
ROT_NAMES = ["landscape-A", "landscape-B", "portrait", "portrait-flipped"]


def parse_getevent_lp(text):
    """`getevent -lp` -> {device_path: {ABS_MT_POSITION_X: max, ABS_MT_POSITION_Y: max}} for touch panels."""
    devs, cur = {}, None
    for line in text.splitlines():
        line = line.rstrip("\r")
        m = re.match(r"\s*add device \d+:\s*(\S+)", line)
        if m:
            cur = m.group(1); devs[cur] = {}; continue
        if cur is None:
            continue
        m = re.search(r"(ABS_MT_POSITION_[XY])\s*:.*?max\s+(\d+)", line)
        if m:
            devs[cur][m.group(1)] = int(m.group(2))
    return {d: v for d, v in devs.items() if "ABS_MT_POSITION_X" in v and "ABS_MT_POSITION_Y" in v}


def _pick_device(log_text, devs):
    counts = {d: 0 for d in devs}
    for line in log_text.splitlines():
        if "ABS_MT_POSITION_X" in line:
            m = _EV.match(line.rstrip("\r"))
            if m and m.group(2) in counts:
                counts[m.group(2)] += 1
    best = max(counts, key=counts.get) if counts else None
    if best is None or counts[best] == 0:
        raise ValueError("touch_log.txt mein koi touch event nahi mila. Capture chalu tha? Phone par screen touch hui?")
    return best


def parse_touches(log_text, dev):
    """Multitouch protocol B -> list of touches: dict(down, up, s=np.array[(t, x_raw, y_raw), ...])."""
    touches, slots, cur = [], {}, 0
    def sl(k):
        return slots.setdefault(k, dict(x=None, y=None, touch=None, dirty=False, rel=False))
    for line in log_text.splitlines():
        m = _EV.match(line.rstrip("\r"))
        if not m or m.group(2) != dev:
            continue
        ts = float(m.group(1)); typ, code, val = m.group(3), m.group(4), m.group(5)
        if typ == "EV_ABS":
            if code == "ABS_MT_SLOT":
                cur = int(val, 16)
            elif code == "ABS_MT_TRACKING_ID":
                s_ = sl(cur)
                if val.lower() == "ffffffff":
                    s_["rel"] = True; s_["dirty"] = True
                else:
                    if s_["touch"] is not None:
                        s_["touch"]["up"] = ts
                    t_ = dict(down=ts, up=None, rows=[]); touches.append(t_)
                    s_["touch"] = t_; s_["x"] = s_["y"] = None; s_["dirty"] = True
            elif code == "ABS_MT_POSITION_X":
                s_ = sl(cur); s_["x"] = int(val, 16); s_["dirty"] = True
            elif code == "ABS_MT_POSITION_Y":
                s_ = sl(cur); s_["y"] = int(val, 16); s_["dirty"] = True
        elif typ == "EV_SYN" and code == "SYN_REPORT":
            for s_ in slots.values():
                if not s_["dirty"]:
                    continue
                s_["dirty"] = False
                t_ = s_["touch"]
                if t_ is None:
                    s_["rel"] = False; continue
                if s_["rel"]:
                    t_["up"] = ts; s_["touch"] = None; s_["rel"] = False
                elif s_["x"] is not None and s_["y"] is not None:
                    t_["rows"].append((ts, s_["x"], s_["y"]))
    out = []
    for t_ in touches:
        if t_["rows"]:
            out.append(dict(down=t_["down"], up=t_["up"] if t_["up"] is not None else 1e18, s=np.array(t_["rows"], np.float64)))
    return out


def _to_land(u, v, rot):
    return [(v, 1 - u), (1 - v, u), (u, v), (1 - u, 1 - v)][rot]


def _control_hits(x, y, controls, W, H):
    """Index of the control whose region contains normalized point (x, y), else -1 (nearest wins)."""
    best, bd = -1, 1e18
    for j, c in enumerate(controls):
        rad = c["r"] * W * (STICK_SCALE if is_stick(c["name"]) else BTN_SCALE)
        d = np.hypot((x - c["x"]) * W, (y - c["y"]) * H)
        if d <= rad and d < bd:
            best, bd = j, d
    return best


def _pick_rotation(touches, controls, W, H, maxx, maxy):
    best_rot, best_score = 0, -1.0
    n = max(1, len(touches))
    for rot in range(4):
        hit = 0
        for t_ in touches:
            u, v = t_["s"][0, 1] / maxx, t_["s"][0, 2] / maxy
            x, y = _to_land(u, v, rot)
            if _control_hits(x, y, controls, W, H) >= 0:
                hit += 1
        sc = hit / n
        if sc > best_score:
            best_rot, best_score = rot, sc
    return best_rot, best_score


def read_events_csv(path):
    """events.csv -> {session_id: {'start': uptime_s, 'stop': uptime_s or None}}"""
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in _csv.DictReader(f):
            if "uptime_ms" not in r:
                raise ValueError("events.csv mein uptime_ms nahi hai - app ka naya EventLogger.kt (v0.6) build karke nayi recording karo.")
            if r["action_name"] in ("RECORD_START", "RECORD_STOP"):
                d = out.setdefault(r["session_id"], dict(start=None, stop=None))
                d["start" if r["action_name"] == "RECORD_START" else "stop"] = float(r["uptime_ms"]) / 1000.0
    return out


def build_session_touch(video, profile_path, out_npz, touches, devmax, start_s, stop_s=None, fps=10, sync_offset=0.0):
    prof, controls = load_profile(profile_path)
    names = [c["name"] for c in controls]; C = len(names)
    cap = cv2.VideoCapture(video); W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)); cap.release()
    mask_boxes = [box(c, MW, MH, MASK_SCALE * (1.4 if is_stick(c["name"]) else 1.0)) for c in controls]
    frames, times = [], []
    for t, fr in iter_frames(video, fps, (MW, MH)):
        small = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
        for (x0, y0, x1, y1) in mask_boxes:
            small[y0:y1, x0:x1] = 128
        frames.append(small); times.append(t)
    N = len(frames)
    if N < 10:
        raise ValueError("Video mein bahut kam frames: " + video)
    times = np.array(times, np.float64)
    T = start_s + times + sync_offset
    t_end = stop_s if stop_s is not None else T[-1]
    mine = [t_ for t_ in touches if t_["up"] >= T[0] - 1 and t_["down"] <= t_end + 1]
    if not mine:
        raise ValueError("Is recording ke samay mein koi touch nahi mila (time match nahi hua). touch_log.txt isi session ke dauran chalu tha? "
                         "Recording start %.1f s, log %.1f-%.1f s" % (start_s, touches[0]["down"], touches[-1]["down"]))
    maxx, maxy = devmax
    rot, score = _pick_rotation(mine, controls, W, H, maxx, maxy)
    targets = np.zeros((N, C + 2), np.float32)
    stick_j = next((j for j, n in enumerate(names) if is_stick(n)), None)
    for t_ in mine:
        ts_, xs, ys = t_["s"][:, 0], t_["s"][:, 1] / maxx, t_["s"][:, 2] / maxy
        lx, ly = _to_land(xs, ys, rot)
        j = _control_hits(lx[0], ly[0], controls, W, H)
        if j < 0:
            continue                      # aim/look drag or unrelated touch (not labelled yet)
        f0 = int(np.searchsorted(T, t_["down"], side="left")); f1 = int(np.searchsorted(T, t_["up"], side="right"))
        if f1 <= f0:
            continue
        targets[f0:f1, j] = 1.0
        if j == stick_j:
            rad = controls[j]["r"] * W * STICK_SCALE
            k = np.clip(np.searchsorted(ts_, T[f0:f1], side="right") - 1, 0, len(ts_) - 1)
            targets[f0:f1, C] = np.clip((lx[k] - lx[0]) * W / rad, -1, 1)
            targets[f0:f1, C + 1] = np.clip((ly[k] - ly[0]) * H / rad, -1, 1)
    rates = {n: float(targets[:, j].mean()) for j, n in enumerate(names)}
    np.savez_compressed(
        out_npz, frames=np.stack(frames), targets=targets, t=times.astype(np.float32),
        names=np.array(names), profile=np.array(json.dumps(prof)),
        params=np.array(json.dumps(dict(method="touchlog", fps=fps, rotation=ROT_NAMES[rot], sync_offset=sync_offset))))
    return dict(video=os.path.basename(video), frames=int(N), pressed_rate=rates, rotation=ROT_NAMES[rot], rotation_score=float(score), touches=len(mine))


def build_dataset_touch(data_dir, out_dir, touch_log="touch_log.txt", devices="touch_devices.txt", events="events.csv", fps=10, sync_offset=0.0):
    """EXACT labels: needs in data_dir -> Game_session.mp4 + .profile.json (per recording) and ONE touch_log.txt +
    touch_devices.txt (from the PC capture script) + events.csv (from the phone)."""
    os.makedirs(out_dir, exist_ok=True)
    need = [touch_log, devices, events]
    miss = [n for n in need if not os.path.exists(os.path.join(data_dir, n))]
    if miss:
        raise FileNotFoundError("Folder mein ye files chahiye: " + ", ".join(miss))
    log_text = open(os.path.join(data_dir, touch_log), encoding="utf-8", errors="ignore").read()
    devs = parse_getevent_lp(open(os.path.join(data_dir, devices), encoding="utf-8", errors="ignore").read())
    if not devs:
        raise ValueError("touch_devices.txt mein touchscreen device nahi mila.")
    dev = _pick_device(log_text, devs)
    touches = parse_touches(log_text, dev)
    print("Touch device:", dev, "| touches in log:", len(touches))
    sessions = read_events_csv(os.path.join(data_dir, events))
    videos = sorted(glob.glob(os.path.join(data_dir, "*.mp4")))
    seen, uniq = {}, []
    for v in videos:
        fp = _fingerprint(v)
        if fp in seen:
            print("SKIP DUPLICATE:", os.path.basename(v)); continue
        seen[fp] = v; uniq.append(v)
    for old in glob.glob(os.path.join(out_dir, "*.npz")):
        os.remove(old)
    reports = []
    for v in uniq:
        m = re.search(r"_(s\d+)\.mp4$", v)
        pj = v[:-4] + ".profile.json"
        if not m or m.group(1) not in sessions or sessions[m.group(1)]["start"] is None:
            print("SKIP %s: events.csv mein is session ka RECORD_START nahi mila" % os.path.basename(v)); continue
        if not os.path.exists(pj):
            print("SKIP %s: .profile.json nahi mili" % os.path.basename(v)); continue
        ss = sessions[m.group(1)]
        print("Building", os.path.basename(v), "...")
        try:
            rep = build_session_touch(v, pj, os.path.join(out_dir, os.path.basename(v)[:-4] + ".npz"), touches, (devs[dev]["ABS_MT_POSITION_X"], devs[dev]["ABS_MT_POSITION_Y"]),
                                      ss["start"], ss["stop"], fps=fps, sync_offset=sync_offset)
        except ValueError as e:
            print("  SKIP:", e); continue
        print("  frames: %d | touches in window: %d | screen rotation: %s (match %.0f%%)" % (rep["frames"], rep["touches"], rep["rotation"], 100 * rep["rotation_score"]))
        if rep["rotation_score"] < 0.3:
            print("  WARNING: bahut kam touches calibrated buttons par aaye. Calibration sahi hai? (rotation/sync check)")
        for n, r in rep["pressed_rate"].items():
            print("  %-16s pressed %5.1f%% of frames" % (n, 100 * r))
        reports.append(rep)
    if not reports:
        raise FileNotFoundError("Koi recording use nahi hui (upar ke SKIP messages dekho).")
    return reports


# ------------------------------------------------------------------ training
def make_model(n_out):
    import torch.nn as nn

    def blk(i, o, k, s):
        return nn.Sequential(nn.Conv2d(i, o, k, s, k // 2, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True))

    class Policy(nn.Module):
        def __init__(self):
            super().__init__()
            self.features = nn.Sequential(blk(6, 24, 5, 2), blk(24, 48, 3, 2), blk(48, 96, 3, 2), blk(96, 128, 3, 2),
                                          nn.AdaptiveAvgPool2d((3, 4)), nn.Flatten())
            self.head = nn.Sequential(nn.Linear(128 * 12, 256), nn.ReLU(inplace=True), nn.Dropout(0.3), nn.Linear(256, n_out))

        def forward(self, x):
            return self.head(self.features(x))

    return Policy()


def _load_sessions(dataset_dir):
    """Loads every recording (.npz). Recordings may have different control lists (e.g. one has LEFT/RIGHT,
    another does not): we train on the controls COMMON to all recordings, aligned by name."""
    files = sorted(glob.glob(os.path.join(dataset_dir, "*.npz")))
    if not files:
        raise FileNotFoundError("No .npz files in " + dataset_dir + " - run the dataset step first")
    raw, seen_sig = [], {}
    for f in files:
        d = np.load(f, allow_pickle=False)
        fr = d["frames"]
        sig = hash(fr[::25].tobytes()) if len(fr) else 0
        if sig in seen_sig:
            print("SKIP DUPLICATE dataset:", os.path.basename(f), "(same frames as", seen_sig[sig] + ")"); continue
        seen_sig[sig] = os.path.basename(f)
        raw.append(dict(file=os.path.basename(f), names=[str(n) for n in d["names"]], frames=fr,
                        targets=d["targets"], profile=json.loads(str(d["profile"]))))
    common = [n for n in raw[0]["names"] if all(n in r["names"] for r in raw)]
    print("Recordings:", len(raw))
    for r in raw:
        extra = [n for n in r["names"] if n not in common]
        print("  %-36s controls=%d%s" % (r["file"], len(r["names"]), ("  (chhode gaye: " + ", ".join(extra) + ")") if extra else ""))
    if len(common) < 2:
        raise ValueError("Recordings ke beech 2 se kam common control hain. Har recording ke controls: " +
                         "; ".join("%s=%s" % (r["file"][:24], r["names"]) for r in raw) +
                         " -> App mein har game ke liye same controls calibrate karo.")
    print("Training controls (sab recordings mein common):", common)
    Cn = len(common)
    stick_name = next((n for n in common if is_stick(n)), None)
    sess = []
    for r in raw:
        t = r["targets"]; Ci = len(r["names"]); idx = [r["names"].index(n) for n in common]
        nt = np.zeros((len(t), Cn + 2), np.float32)
        nt[:, :Cn] = t[:, idx]
        if stick_name is not None:
            nt[:, Cn:Cn + 2] = t[:, Ci:Ci + 2] if r["names"].index(stick_name) == next(i for i, n in enumerate(r["names"]) if is_stick(n)) else 0.0
        prof_pos = {c["name"]: (c["x"], c["y"]) for c in r["profile"].get("controls", [])}
        ref_pos = {c["name"]: (c["x"], c["y"]) for c in raw[0]["profile"].get("controls", [])}
        moved = [n for n in common if n in prof_pos and n in ref_pos and
                 (abs(prof_pos[n][0] - ref_pos[n][0]) > 0.03 or abs(prof_pos[n][1] - ref_pos[n][1]) > 0.03)]
        if moved:
            print("  WARNING: %s mein ye buttons pehli recording se alag jagah calibrate hain: %s" % (r["file"], ", ".join(moved)))
        sess.append(dict(file=r["file"], frames=r["frames"], targets=nt, profile=r["profile"]))
    return common, sess


def _prf(pred, true):
    tp = float(((pred == 1) & (true == 1)).sum()); fp = float(((pred == 1) & (true == 0)).sum()); fn = float(((pred == 0) & (true == 1)).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def train(dataset_dir, out_dir, epochs=15, batch=64, lr=1e-3, val_frac=0.2, seed=0, force=False):
    import torch, torch.nn as nn
    rng = np.random.RandomState(seed); torch.manual_seed(seed)
    names, sess = _load_sessions(dataset_dir)
    C = len(names)
    Yall = np.concatenate([s["targets"] for s in sess])
    bad = [n for j, n in enumerate(names) if Yall[:, j].mean() > (0.90 if is_stick(n) else 0.45)]
    if bad and not force:
        raise ValueError("Labels bharosemand nahi hain: %s lagbhag hamesha 'pressed' dikh rahe hain. "
                         "Training roki gayi (galat labels = bekaar model). Show taps ON tha? Cell 2b ka preview dekho; "
                         "phir bhi chalana ho to train(..., force=True)." % ", ".join(bad))
    X = np.concatenate([s["frames"] for s in sess]); Y = np.concatenate([s["targets"] for s in sess])
    sid = np.concatenate([np.full(len(s["frames"]), i) for i, s in enumerate(sess)])
    N = len(X)
    prev = np.arange(N) - 1
    starts = np.nonzero(np.r_[True, sid[1:] != sid[:-1]])[0]
    prev[starts] = starts  # first frame of a session has no previous frame
    # ---- split: held-out sessions when possible, else last chunk of the single session (with a gap)
    if len(sess) >= 2:
        n_val = max(1, int(round(len(sess) * val_frac)))
        val_s = set(range(len(sess) - n_val, len(sess)))
        tr = np.array([i for i in range(N) if sid[i] not in val_s]); va = np.array([i for i in range(N) if sid[i] in val_s])
        split_note = "held-out sessions: " + ", ".join(sess[i]["file"] for i in sorted(val_s))
    else:
        cut = int(N * (1 - val_frac)); gap = 10
        tr = np.arange(0, max(1, cut - gap)); va = np.arange(cut, N)
        split_note = "single session: last %d%% of the video held out (gap of %d samples)" % (int(val_frac * 100), gap)
    print("Samples train/val:", len(tr), len(va), "|", split_note)
    if len(tr) < 2 or len(va) < 1:
        raise ValueError("Not enough frames to train. Record a longer session (at least a few minutes).")
    if len(tr) < 50 or len(va) < 10:
        print("WARNING: very little data. Results will not be meaningful. Record more gameplay.")
    pos = Y[tr, :C].mean(0).clip(1e-3, 1 - 1e-3)
    pos_w = torch.tensor(np.clip((1 - pos) / pos, 1.0, 20.0), dtype=torch.float32)
    stick_cols = [j for j, n in enumerate(names) if is_stick(n)]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = make_model(C + 2).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(1, epochs))
    bce = nn.BCEWithLogitsLoss(pos_weight=pos_w.to(device))

    def batch_x(idx, aug):
        x = np.concatenate([X[idx], X[prev[idx]]], axis=3)
        x = torch.from_numpy(x).permute(0, 3, 1, 2).float().div_(255.0)
        if aug:
            x = x * torch.empty(len(idx), 1, 1, 1).uniform_(0.8, 1.2)
            x = x.clamp_(0, 1)
        return x.to(device)

    def evaluate():
        model.eval(); out = []
        with torch.no_grad():
            for i in range(0, len(va), 128):
                out.append(model(batch_x(va[i:i + 128], False)).cpu())
        o = torch.cat(out).numpy(); prob = 1 / (1 + np.exp(-o[:, :C]))
        rows = []
        for j, n in enumerate(names):
            p, r, f = _prf((prob[:, j] > 0.5).astype(int), Y[va, j].astype(int))
            rows.append(dict(control=n, precision=p, recall=r, f1=f, support=int(Y[va, j].sum()), base_rate=float(Y[va, j].mean())))
        sup = [r["f1"] for r in rows if r["support"] > 0]
        macro = float(np.mean(sup)) if sup else 0.0
        stick_mae = None
        if stick_cols:
            m = Y[va, stick_cols[0]] > 0.5
            if m.any():
                stick_mae = float(np.abs(o[m, C:C + 2] - Y[va][m][:, C:C + 2]).mean())
        return rows, macro, stick_mae, prob

    best, best_state, best_rows, best_prob, history = -1.0, None, None, None, []
    for ep in range(epochs):
        model.train(); rng.shuffle(tr); tot = 0.0; nb = 0
        for i in range(0, len(tr), batch):
            idx = tr[i:i + batch]
            if len(idx) < 2:
                continue
            x = batch_x(idx, True); y = torch.from_numpy(Y[idx]).to(device)
            o = model(x)
            loss = bce(o[:, :C], y[:, :C])
            if stick_cols:
                w = y[:, stick_cols[0]].unsqueeze(1)
                loss = loss + (nn.functional.smooth_l1_loss(o[:, C:], y[:, C:], reduction="none") * w).mean()
            opt.zero_grad(); loss.backward(); opt.step(); tot += loss.item(); nb += 1
        sched.step()
        rows, macro, smae, prob = evaluate()
        history.append(dict(epoch=ep + 1, train_loss=tot / max(1, nb), val_macro_f1=macro))
        print("epoch %2d  train_loss %.4f  val macro-F1 %.3f" % (ep + 1, tot / max(1, nb), macro))
        if macro > best:
            best = macro; best_rows = rows; best_prob = prob
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            best_smae = smae
    model.load_state_dict(best_state)
    # suggested per-control thresholds (tuned on validation: optimistic, use as a starting point only)
    thr = {}
    for j, n in enumerate(names):
        bt, bf = 0.5, -1
        for t in np.arange(0.3, 0.91, 0.05):
            f = _prf((best_prob[:, j] > t).astype(int), Y[va, j].astype(int))[2]
            if f > bf: bf, bt = f, float(t)
        thr[n] = round(bt, 2)
    os.makedirs(out_dir, exist_ok=True)
    prof = sess[0]["profile"]
    meta = dict(
        game=prof.get("game"), controls=names, stick_control=(names[stick_cols[0]] if stick_cols else None),
        input=dict(width=MW, height=MH, channels="current RGB frame + previous RGB frame (6 channels), /255", control_regions_greyed=True),
        output="first %d = pressed logits (sigmoid), last 2 = stick_x, stick_y" % C,
        mask_boxes_norm=[[b[0] / MW, b[1] / MH, b[2] / MW, b[3] / MH] for b in
                         [box(c, MW, MH, MASK_SCALE * (1.4 if is_stick(c["name"]) else 1.0)) for c in prof["controls"]]],
        split=split_note, val_metrics=best_rows, val_macro_f1=best, stick_mae_val=best_smae, suggested_thresholds=thr,
        history=history, train_samples=int(len(tr)), val_samples=int(len(va)), sessions=[s["file"] for s in sess])
    torch.save(dict(state_dict=best_state, meta=meta), os.path.join(out_dir, "policy.pt"))
    model.eval().cpu()
    try:
        ts = torch.jit.trace(model, torch.zeros(1, 6, MH, MW))
        ts.save(os.path.join(out_dir, "policy_ts.pt"))
    except Exception as e:
        print("TorchScript export skipped:", e)
    with open(os.path.join(out_dir, "model_report.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print("\nHeld-out results (threshold 0.5)")
    print("%-16s %9s %9s %9s %8s %9s" % ("control", "precision", "recall", "F1", "support", "base rate"))
    for r in best_rows:
        print("%-16s %9.2f %9.2f %9.2f %8d %8.1f%%" % (r["control"], r["precision"], r["recall"], r["f1"], r["support"], 100 * r["base_rate"]))
    print("Macro F1 (controls that occur in val): %.3f" % best)
    print("Saved to", out_dir, ": policy.pt, policy_ts.pt, model_report.json")
    return meta


# ------------------------------------------------------------------ leave-one-session-out cross-validation
def _best_thr(P, Yc):
    """Threshold (0.10..0.90) with the best F1; 0.5 if there are no positives."""
    if Yc.sum() == 0:
        return 0.5
    best_t, best_f = 0.5, -1.0
    for t in np.arange(0.10, 0.91, 0.05):
        f = _prf((P > t).astype(int), Yc.astype(int))[2]
        if f > best_f:
            best_f, best_t = f, float(t)
    return round(best_t, 2)


def _cv_report(names, probs, Ys):
    """probs/Ys: dict fold -> (n,C) probabilities / (n,C) 0-1 labels from models that did NOT see that fold.
    Thresholds for a fold are tuned only on the OTHER folds (so the numbers are honest)."""
    folds = sorted(probs)
    rows, final_thr = [], {}
    macro_by_fold = {k: [] for k in folds}
    for j, n in enumerate(names):
        f05, fcal, pre, rec, base = [], [], [], [], []
        for k in folds:
            yk = Ys[k][:, j].astype(int)
            if yk.sum() == 0:
                continue
            oP = np.concatenate([probs[m][:, j] for m in folds if m != k]) if len(folds) > 1 else probs[k][:, j]
            oY = np.concatenate([Ys[m][:, j] for m in folds if m != k]) if len(folds) > 1 else Ys[k][:, j]
            thr = _best_thr(oP, oY)
            p, r, f = _prf((probs[k][:, j] > thr).astype(int), yk)
            f05.append(_prf((probs[k][:, j] > 0.5).astype(int), yk)[2])
            fcal.append(f); pre.append(p); rec.append(r); base.append(float(yk.mean()))
            macro_by_fold[k].append(f)
        allP = np.concatenate([probs[k][:, j] for k in folds]); allY = np.concatenate([Ys[k][:, j] for k in folds])
        final_thr[n] = _best_thr(allP, allY)
        m = lambda a: float(np.mean(a)) if a else 0.0
        rows.append(dict(control=n, f1_at_0_5=m(f05), f1_calibrated=m(fcal), f1_min=float(min(fcal)) if fcal else 0.0,
                         f1_max=float(max(fcal)) if fcal else 0.0, precision=m(pre), recall=m(rec), base_rate=m(base),
                         lift=(m(pre) / m(base)) if m(base) > 0 else 0.0, folds_with_data=len(fcal)))
    per_fold = {k: (float(np.mean(v)) if v else 0.0) for k, v in macro_by_fold.items()}
    return rows, final_thr, per_fold


def _batch_x(torch, X, prev, idx, aug, device):
    x = np.concatenate([X[idx], X[prev[idx]]], axis=3)
    x = torch.from_numpy(x).permute(0, 3, 1, 2).float().div_(255.0)
    if aug:
        x = x * torch.empty(len(idx), 1, 1, 1).uniform_(0.8, 1.2)
        x = x.clamp_(0, 1)
    return x.to(device)


def _fit(torch, nn, X, Y, prev, tr, C, stick_col, epochs, batch, lr, seed, device):
    """Train for a FIXED number of epochs (no peeking at held-out data) and return the model."""
    torch.manual_seed(seed); rng = np.random.RandomState(seed)
    pos = Y[tr, :C].mean(0).clip(1e-3, 1 - 1e-3)
    pos_w = torch.tensor(np.clip((1 - pos) / pos, 1.0, 8.0), dtype=torch.float32).to(device)
    model = make_model(C + 2).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(1, epochs))
    bce = nn.BCEWithLogitsLoss(pos_weight=pos_w)
    tr = tr.copy()
    for ep in range(epochs):
        model.train(); rng.shuffle(tr); tot = 0.0; nb = 0
        for i in range(0, len(tr), batch):
            idx = tr[i:i + batch]
            if len(idx) < 2:
                continue
            x = _batch_x(torch, X, prev, idx, True, device); y = torch.from_numpy(Y[idx]).to(device)
            o = model(x)
            loss = bce(o[:, :C], y[:, :C])
            if stick_col is not None:
                w = y[:, stick_col].unsqueeze(1)
                loss = loss + (nn.functional.smooth_l1_loss(o[:, C:], y[:, C:], reduction="none") * w).mean()
            opt.zero_grad(); loss.backward(); opt.step(); tot += loss.item(); nb += 1
        sched.step()
        print("    epoch %2d/%d  train_loss %.4f" % (ep + 1, epochs, tot / max(1, nb)))
    return model


def _predict(torch, model, X, prev, idx, device):
    model.eval(); out = []
    with torch.no_grad():
        for i in range(0, len(idx), 128):
            out.append(model(_batch_x(torch, X, prev, idx[i:i + 128], False, device)).cpu())
    return torch.cat(out).numpy()


def cross_validate(dataset_dir, out_dir, epochs=12, batch=64, lr=1e-3, seed=0, force=False):
    """Every recording (map) is held out once; the model never sees it while being tested on it.
    Then one final model is trained on ALL recordings and saved with honest thresholds."""
    import torch, torch.nn as nn
    names, sess = _load_sessions(dataset_dir)
    C = len(names)
    if len(sess) < 2:
        raise ValueError("Cross-validation ke liye kam se kam 2 alag recordings (.npz) chahiye. Abhi sirf %d hai." % len(sess))
    X = np.concatenate([s_["frames"] for s_ in sess]); Y = np.concatenate([s_["targets"] for s_ in sess])
    sid = np.concatenate([np.full(len(s_["frames"]), i) for i, s_ in enumerate(sess)])
    bad = [n for j, n in enumerate(names) if Y[:, j].mean() > (0.90 if is_stick(n) else 0.45)]
    if bad and not force:
        raise ValueError("Labels bharosemand nahi hain: %s. Training roki gayi. (force=True se chal sakta hai)" % ", ".join(bad))
    N = len(X)
    prev = np.arange(N) - 1
    starts = np.nonzero(np.r_[True, sid[1:] != sid[:-1]])[0]
    prev[starts] = starts
    stick_cols = [j for j, n in enumerate(names) if is_stick(n)]
    stick_col = stick_cols[0] if stick_cols else None
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("Device:", device, "| recordings:", len(sess), "| frames:", N)

    probs, Ys, Yk_full, pred_stick = {}, {}, {}, {}
    for k in range(len(sess)):
        va = np.nonzero(sid == k)[0]; tr = np.nonzero(sid != k)[0]
        print("\nFold %d/%d: TEST = %s (%d frames) | train = %d frames" % (k + 1, len(sess), sess[k]["file"], len(va), len(tr)))
        model = _fit(torch, nn, X, Y, prev, tr, C, stick_col, epochs, batch, lr, seed + k, device)
        o = _predict(torch, model, X, prev, va, device)
        probs[k] = 1 / (1 + np.exp(-o[:, :C])); Ys[k] = Y[va, :C]; Yk_full[k] = Y[va]; pred_stick[k] = o[:, C:C + 2]
        del model
        if device == "cuda":
            torch.cuda.empty_cache()

    rows, final_thr, per_fold = _cv_report(names, probs, Ys)
    stick_mae = None
    if stick_col is not None:
        errs = []
        for k in probs:
            m = Yk_full[k][:, stick_col] > 0.5
            if m.any():
                errs.append(float(np.abs(pred_stick[k][m] - Yk_full[k][m][:, C:C + 2]).mean()))
        stick_mae = float(np.mean(errs)) if errs else None

    print("\n=== Cross-validated results (har map naye map ki tarah test hua) ===")
    print("%-16s %7s %9s %11s %9s %7s %9s %6s" % ("control", "F1@0.5", "F1(calib)", "F1 min-max", "precision", "recall", "base rate", "lift"))
    for r in rows:
        print("%-16s %7.2f %9.2f %5.2f-%-5.2f %9.2f %7.2f %8.1f%% %5.1fx" % (
            r["control"], r["f1_at_0_5"], r["f1_calibrated"], r["f1_min"], r["f1_max"], r["precision"], r["recall"], 100 * r["base_rate"], r["lift"]))
    cv_macro = float(np.mean([r["f1_calibrated"] for r in rows if r["folds_with_data"] > 0] or [0.0]))
    print("Macro F1 (calibrated, average over held-out maps): %.3f" % cv_macro)
    print("Per held-out recording macro-F1:", ", ".join("%s=%.2f" % (sess[k]["file"][:28], v) for k, v in per_fold.items()))
    if stick_mae is not None:
        print("Stick direction MAE on held-out maps: %.3f (0 = perfect; 'always 0' would be about the label spread)" % stick_mae)
    print("Lift = precision / base rate. 1.0x = andaza lagane jaisa; jitna zyada, utna behtar.")

    print("\nFinal model ko saare recordings par train kar raha hoon...")
    model = _fit(torch, nn, X, Y, prev, np.arange(N), C, stick_col, epochs, batch, lr, seed + 99, device)
    model.eval().cpu()
    state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    os.makedirs(out_dir, exist_ok=True)
    prof = sess[0]["profile"]
    meta = dict(
        game=prof.get("game"), controls=names, stick_control=(names[stick_col] if stick_col is not None else None),
        input=dict(width=MW, height=MH, channels="current RGB frame + previous RGB frame (6 channels), /255", control_regions_greyed=True),
        output="first %d = pressed logits (sigmoid), last 2 = stick_x, stick_y" % C,
        mask_boxes_norm=[[b[0] / MW, b[1] / MH, b[2] / MW, b[3] / MH] for b in
                        [box(c, MW, MH, MASK_SCALE * (1.4 if is_stick(c["name"]) else 1.0)) for c in prof["controls"]]],
        thresholds=final_thr, cv_metrics=rows, cv_macro_f1=cv_macro, cv_per_recording=[dict(file=sess[k]["file"], macro_f1=v) for k, v in per_fold.items()],
        stick_mae_cv=stick_mae, epochs=epochs, sessions=[s_["file"] for s_ in sess], samples=int(N),
        note="Final model trained on all recordings. cv_metrics come from leave-one-recording-out models. Thresholds are tuned on pooled out-of-fold predictions.")
    torch.save(dict(state_dict=state, meta=meta), os.path.join(out_dir, "policy.pt"))
    try:
        ts = torch.jit.trace(model, torch.zeros(1, 6, MH, MW))
        ts.save(os.path.join(out_dir, "policy_ts.pt"))
    except Exception as e:
        print("TorchScript export skipped:", e)
    with open(os.path.join(out_dir, "model_report.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print("Saved to", out_dir, ": policy.pt, policy_ts.pt, model_report.json  (thresholds model_report.json mein)")
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--data", required=True); b.add_argument("--out", required=True)
    b.add_argument("--fps", type=int, default=10); b.add_argument("--gain_thr", type=float, default=None)
    b.add_argument("--sat_thr", type=float, default=80); b.add_argument("--dot_r", type=float, default=None)
    t = sub.add_parser("train"); t.add_argument("--dataset", required=True); t.add_argument("--out", required=True)
    t.add_argument("--epochs", type=int, default=15); t.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.cmd == "build":
        build_dataset(a.data, a.out, fps=a.fps, gain_thr=a.gain_thr, sat_thr=a.sat_thr, dot_r=a.dot_r)
    else:
        train(a.dataset, a.out, epochs=a.epochs, force=a.force)
