"""
Conix FPS AI - dataset builder + behaviour-cloning trainer (v0.4)

How labels are made (no root, no PC needed):
  1. In Android Developer options the user turns ON "Show taps".
  2. The Conix app records the screen. The white tap-dots are therefore visible in the video.
  3. For every calibrated control we look at that control's screen region and compare it with how the
     region normally looks (median over the whole video). A bright, low-saturation blob = finger on it.
  4. Joystick finger offset gives a move direction (stick_x, stick_y).
The model input hides every control region (grey box), so the model cannot "read" the tap-dots and must
learn from the game scene itself.

Honest limits: this heuristic is tuned on synthetic data. Check the preview images on your real video and
adjust GAIN_THR / SAT_THR / MIN_DOT if the label rates look wrong. Camera/aim (look) labels are not included yet.
"""
import argparse, glob, json, os, sys
import numpy as np
import cv2

AW, AH = 480, 270      # analysis resolution (label detection)
MW, MH = 256, 144      # model input resolution
STICK_SCALE = 2.5      # stick search region = r * this
BTN_SCALE = 1.3
MASK_SCALE = 1.7       # grey-out region in model input = r * this (stick: *1.4 more)


KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))


def _largest_blob(m):
    """Keep only the largest connected blob of a 0/1 mask. Returns (pixel_count, mask)."""
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n <= 1:
        return 0.0, m.astype(bool)
    k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    return float(st[k, cv2.CC_STAT_AREA]), lab == k


def is_stick(name):
    n = name.upper()
    return "JOYSTICK" in n or n in ("MOVE", "STICK", "MOVEMENT")


def load_profile(path):
    with open(path, "r", encoding="utf-8") as f:
        p = json.load(f)
    controls = [c for c in p.get("controls", []) if all(k in c for k in ("name", "x", "y", "r"))]
    if not controls:
        raise ValueError("No calibrated controls in " + path)
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
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise IOError("Cannot open video: " + video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    step = max(1, int(round(fps / target_fps)))
    i = 0
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, f = cap.retrieve()
            if not ok:
                break
            yield i / fps, cv2.resize(f, size, interpolation=cv2.INTER_AREA)
        i += 1
    cap.release()


def _baselines(video, controls, fps, base_every=3, max_crops=300):
    crops = {c["name"]: [] for c in controls}
    k = 0
    for _, fr in iter_frames(video, fps, (AW, AH)):
        k += 1
        if k % base_every:
            continue
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        for c in controls:
            x0, y0, x1, y1 = box(c, AW, AH, STICK_SCALE if is_stick(c["name"]) else BTN_SCALE)
            if len(crops[c["name"]]) < max_crops:
                crops[c["name"]].append(g[y0:y1, x0:x1].astype(np.float32))
    base = {}
    for n, lst in crops.items():
        if not lst:
            raise ValueError("Video has no frames: " + video)
        base[n] = np.median(np.stack(lst), axis=0)
    return base


def build_session(video, profile_path, out_npz, fps=10, gain_thr=35, sat_thr=70, min_dot=0.010, smooth=True):
    """Video + profile json -> npz with frames, targets. Returns a report dict."""
    prof, controls = load_profile(profile_path)
    names = [c["name"] for c in controls]
    C = len(names)
    base = _baselines(video, controls, fps)
    min_px = np.pi * (min_dot * AW) ** 2
    frames, targets, times, scores = [], [], [], []
    mask_boxes = [box(c, MW, MH, MASK_SCALE * (1.4 if is_stick(c["name"]) else 1.0)) for c in controls]
    for t, fr in iter_frames(video, fps, (AW, AH)):
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        sat = cv2.cvtColor(fr, cv2.COLOR_BGR2HSV)[:, :, 1]
        sc = np.zeros(C, np.float32)
        pr = np.zeros(C, np.float32)
        stick = np.zeros(2, np.float32)
        for j, c in enumerate(controls):
            x0, y0, x1, y1 = box(c, AW, AH, STICK_SCALE if is_stick(c["name"]) else BTN_SCALE)
            gain = g[y0:y1, x0:x1] - base[c["name"]]
            gain = gain - float(np.median(gain))  # ignore whole-region flashes / brightness changes
            gain = cv2.GaussianBlur(gain, (0, 0), 1.5)
            m = ((gain > gain_thr) & (sat[y0:y1, x0:x1] < sat_thr)).astype(np.uint8)
            m = cv2.morphologyEx(m, cv2.MORPH_OPEN, KERNEL)  # remove scattered noise, keep compact blobs
            npx, m = _largest_blob(m)
            frac = npx / m.size
            # a finger dot is a compact blob: big enough to be a dot, small enough not to be a full-screen flash
            pressed = (npx >= min_px) and (frac <= 0.45)
            sc[j] = frac if pressed else 0.0
            pr[j] = 1.0 if pressed else 0.0
            if pressed and is_stick(c["name"]) and stick_idx_unset(stick):
                ys, xs = np.nonzero(m)
                hw, hh = (x1 - x0) / 2.0, (y1 - y0) / 2.0
                stick[0] = float(np.clip((xs.mean() - hw) / hw, -1, 1))
                stick[1] = float(np.clip((ys.mean() - hh) / hh, -1, 1))
        small = cv2.cvtColor(cv2.resize(fr, (MW, MH), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        for (x0, y0, x1, y1) in mask_boxes:
            small[y0:y1, x0:x1] = 128
        frames.append(small); scores.append(sc); times.append(t)
        targets.append(np.concatenate([pr, stick]))
    if not frames:
        raise ValueError("No frames read from " + video)
    frames = np.stack(frames); targets = np.stack(targets).astype(np.float32); scores = np.stack(scores)
    if smooth and len(frames) >= 3:  # 3-sample majority filter on the pressed flags
        b = targets[:, :C]
        p = np.pad(b, ((1, 1), (0, 0)), mode="edge")
        targets[:, :C] = ((p[:-2] + p[1:-1] + p[2:]) >= 2).astype(np.float32)
        stick_on = np.zeros(len(targets), bool)
        for j, n in enumerate(names):
            if is_stick(n):
                stick_on |= targets[:, j] > 0.5
        targets[~stick_on, C:] = 0.0
    np.savez_compressed(
        out_npz, frames=frames, targets=targets, t=np.array(times, np.float32), scores=scores,
        names=np.array(names), profile=np.array(json.dumps(prof)),
        params=np.array(json.dumps(dict(fps=fps, gain_thr=gain_thr, sat_thr=sat_thr, min_dot=min_dot))))
    rate = {n: float(targets[:, j].mean()) for j, n in enumerate(names)}
    return dict(video=os.path.basename(video), frames=int(len(frames)), pressed_rate=rate)


def stick_idx_unset(stick):
    return stick[0] == 0.0 and stick[1] == 0.0


def build_dataset(data_dir, out_dir, **kw):
    os.makedirs(out_dir, exist_ok=True)
    reports = []
    for v in sorted(glob.glob(os.path.join(data_dir, "*.mp4"))):
        stem = v[:-4]
        pj = stem + ".profile.json"
        if not os.path.exists(pj):
            print("SKIP (no matching .profile.json):", os.path.basename(v)); continue
        out = os.path.join(out_dir, os.path.basename(stem) + ".npz")
        print("Building", os.path.basename(v), "...")
        rep = build_session(v, pj, out, **kw)
        print("  frames:", rep["frames"])
        for n, r in rep["pressed_rate"].items():
            print("  %-16s pressed %5.1f%% of frames" % (n, 100 * r))
        reports.append(rep)
    if not reports:
        print("No usable recordings found. Need Game_session.mp4 AND Game_session.profile.json in", data_dir)
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
    files = sorted(glob.glob(os.path.join(dataset_dir, "*.npz")))
    if not files:
        raise FileNotFoundError("No .npz files in " + dataset_dir + " - run the dataset step first")
    sess = []
    names0 = None
    for f in files:
        d = np.load(f, allow_pickle=False)
        names = [str(n) for n in d["names"]]
        if names0 is None:
            names0 = names
        if names != names0:
            print("SKIP (different controls than the first session):", os.path.basename(f)); continue
        sess.append(dict(file=os.path.basename(f), frames=d["frames"], targets=d["targets"], profile=json.loads(str(d["profile"]))))
    return names0, sess


def _prf(pred, true):
    tp = float(((pred == 1) & (true == 1)).sum()); fp = float(((pred == 1) & (true == 0)).sum()); fn = float(((pred == 0) & (true == 1)).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def train(dataset_dir, out_dir, epochs=15, batch=64, lr=1e-3, val_frac=0.2, seed=0):
    import torch, torch.nn as nn
    rng = np.random.RandomState(seed); torch.manual_seed(seed)
    names, sess = _load_sessions(dataset_dir)
    C = len(names)
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--data", required=True); b.add_argument("--out", required=True)
    b.add_argument("--fps", type=int, default=10); b.add_argument("--gain_thr", type=float, default=35)
    b.add_argument("--sat_thr", type=float, default=70); b.add_argument("--min_dot", type=float, default=0.010)
    t = sub.add_parser("train"); t.add_argument("--dataset", required=True); t.add_argument("--out", required=True)
    t.add_argument("--epochs", type=int, default=15)
    a = ap.parse_args()
    if a.cmd == "build":
        build_dataset(a.data, a.out, fps=a.fps, gain_thr=a.gain_thr, sat_thr=a.sat_thr, min_dot=a.min_dot)
    else:
        train(a.dataset, a.out, epochs=a.epochs)
