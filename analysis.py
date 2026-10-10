"""物理图像数字化。无全图正弦拟合；标准波的参数只取首个完整周期。"""
import base64
import io
import warnings as pywarnings

import cv2
import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy.signal import find_peaks, savgol_filter


class AnalysisError(ValueError):
    pass


class Point(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    x: float
    y: float


class Settings(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    origin: Point
    x_point: Point
    y_point: Point
    fourth_point: Point | None = None
    t0: float = 0
    y0: float = 0
    x_value: float = 5
    y_value: float = 1
    unit: str = Field(default="cm", max_length=20)
    roi: list[float] | None = None
    h_low: int = Field(default=140, ge=0, le=179)
    h_high: int = Field(default=179, ge=0, le=179)
    s_min: int = Field(default=55, ge=0, le=255)
    v_min: int = Field(default=50, ge=0, le=255)
    min_component: int = Field(default=10, ge=1, le=200)
    max_gap: int = Field(default=8, ge=0, le=50)
    smooth_window: int = Field(default=9, ge=1, le=101)
    min_extrema_spacing: float = Field(default=0.25, gt=0, le=10000)
    prominence: float = Field(default=0.08, gt=0, le=1e9)
    include_offset: bool = False

    @model_validator(mode="after")
    def check_coordinates(self):
        if self.x_value <= self.t0 or self.y_value == self.y0:
            raise ValueError("时间刻度须大于交点时间；位移刻度须不同于交点位移。")
        if self.roi is not None and (len(self.roi) != 4 or not np.isfinite(self.roi).all()):
            raise ValueError("ROI 须为四个有限像素坐标。")
        if self.smooth_window != 1 and (self.smooth_window < 5 or self.smooth_window % 2 == 0):
            raise ValueError("平滑窗口须为 1（关闭）或大于等于 5 的奇数。")
        return self


def decode_image(data: bytes) -> np.ndarray:
    """检查尺寸后解码，拒绝动画及不支持的格式，不默默旋转标定坐标。"""
    try:
        with pywarnings.catch_warnings():
            pywarnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {"PNG", "JPEG", "WEBP"}:
                    raise AnalysisError("请上传 PNG、JPEG 或 WebP 静态图片。")
                if getattr(image, "n_frames", 1) != 1:
                    raise AnalysisError("请使用静态图片。")
                w, h = image.size
                if w * h > 16_000_000 or min(w, h) < 40 or max(w, h) > 12000:
                    raise AnalysisError("图片须至少 40×40，最多 1600 万像素，单边不超过 12000。")
                # 前端重新编码上传图片；直接 API 调用者须自行处理 EXIF 方向并重新标定。
                if image.getexif().get(274, 1) != 1:
                    raise AnalysisError("图片含 EXIF 旋转信息，请用网页上传以统一方向后标定。")
                rgba = image.convert("RGBA")
                background = Image.new("RGBA", rgba.size, "white")
                background.alpha_composite(rgba)
                rgb = np.asarray(background.convert("RGB"))
                return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except AnalysisError:
        raise
    except Exception as exc:
        raise AnalysisError("图片无法解码，或图片尺寸超过安全限制。") from exc


def transform(points, matrix):
    pts = np.atleast_2d(points).astype(float)
    homogeneous = np.column_stack((pts, np.ones(len(pts)))) @ matrix.T
    if np.any(np.abs(homogeneous[:, 2]) < 1e-9):
        raise AnalysisError("透视变换在分析区域内不稳定，请重新标定。")
    return homogeneous[:, :2] / homogeneous[:, 2, None]


def mapping(cfg: Settings, width: int, height: int):
    src = np.array([[p.x, p.y] for p in [cfg.origin, cfg.x_point, cfg.y_point]], np.float32)
    if cfg.fourth_point:
        src = np.vstack((src, [cfg.fourth_point.x, cfg.fourth_point.y])).astype(np.float32)
    if np.any(src < 0) or np.any(src[:, 0] > width - 1) or np.any(src[:, 1] > height - 1):
        raise AnalysisError("标定点超出图片范围。")
    dx, dy = src[1] - src[0], src[2] - src[0]
    if min(np.linalg.norm(dx), np.linalg.norm(dy)) < 15:
        raise AnalysisError("标定点过近：请选择相隔至少 15 像素的刻度。")
    sine_angle = abs(float(np.linalg.det(np.stack([dx, dy])))) / (np.linalg.norm(dx) * np.linalg.norm(dy))
    if sine_angle < 0.15:
        raise AnalysisError("三点近乎共线，不能建立可靠的物理坐标系。")
    dst = np.array([[cfg.t0, cfg.y0], [cfg.x_value, cfg.y0], [cfg.t0, cfg.y_value]], np.float32)
    if cfg.fourth_point:
        polygon = src[[0, 1, 3, 2]].reshape(-1, 1, 2)
        if not cv2.isContourConvex(polygon) or abs(cv2.contourArea(polygon)) < 400:
            raise AnalysisError("四点应按交点、X刻度、Y刻度、(X刻度,Y刻度)选取，围成凸四边形。")
        dst = np.vstack((dst, [cfg.x_value, cfg.y_value])).astype(np.float32)
        matrix = cv2.getPerspectiveTransform(src, dst)
    else:
        matrix = np.vstack((cv2.getAffineTransform(src, dst), [0, 0, 1]))
    if not np.isfinite(matrix).all() or abs(np.linalg.det(matrix)) < 1e-15:
        raise AnalysisError("坐标变换退化，请重新标定。")
    return matrix


def png_url(mask):
    ok, data = cv2.imencode(".png", mask)
    if not ok:
        raise AnalysisError("提取预览生成失败。")
    return "data:image/png;base64," + base64.b64encode(data).decode()


def metrics(t, y, a, period, phase, offset):
    predicted = offset + a * np.sin(2 * np.pi * t / period + phase)
    residual = y - predicted
    sst = float(np.sum((y - np.mean(y)) ** 2))
    return {"n": len(t), "rmse": float(np.sqrt(np.mean(residual ** 2))),
            "r2": float(1 - np.sum(residual ** 2) / sst) if sst > 1e-15 else None,
            "nrmse_by_a1": float(np.sqrt(np.mean(residual ** 2)) / a)}


def analyze(image: np.ndarray, cfg: Settings):
    height, width = image.shape[:2]
    matrix = mapping(cfg, width, height)
    inverse = np.linalg.inv(matrix)
    x0, y0, x1, y1 = cfg.roi or [0, 0, width - 1, height - 1]
    if not (0 <= x0 < x1 <= width - 1 and 0 <= y0 < y1 <= height - 1):
        raise AnalysisError("分析区域须在图片内，且左上坐标小于右下坐标。")
    if min(x1 - x0, y1 - y0) < 20:
        raise AnalysisError("分析区域过小。")
    notes = []
    # 如何处理因图片透视或裁剪导致的误差：三点仿射只校正旋转、缩放和剪切。
    # 透视照片使用第四个已知坐标点；先重采样到物理坐标网格再逐列提取，
    # 不能直接把倾斜图片的一列当作同一时刻。弯曲纸张/镜头畸变不由单应性校正。
    corners = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    denominators = np.column_stack((corners, np.ones(4))) @ matrix[2]
    if np.min(denominators) * np.max(denominators) <= 0:
        raise AnalysisError("分析区域跨越透视变换奇点，请缩小区域或重新标定。")
    physical = transform(corners, matrix)
    t_min, y_min = physical.min(axis=0)
    t_max, y_max = physical.max(axis=0)
    center = np.array([[(x0 + x1) / 2, (y0 + y1) / 2]])
    q = transform(center, matrix)[0]
    jac = np.column_stack((transform(center + [1, 0], matrix)[0] - q,
                           transform(center + [0, 1], matrix)[0] - q))
    scale_t, scale_y = np.linalg.norm(jac, axis=1)
    cols = int(np.clip(np.ceil((t_max - t_min) / scale_t) + 1, 40, 2400))
    rows = int(np.clip(np.ceil((y_max - y_min) / scale_y) + 1, 40, 1400))
    ts = np.linspace(t_min, t_max, cols)
    ys = np.linspace(y_max, y_min, rows)  # 屏幕向下，物理位移向上
    tt, yy = np.meshgrid(ts, ys)
    source = transform(np.column_stack((tt.ravel(), yy.ravel())), inverse).reshape(rows, cols, 2)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lo, hi = cfg.h_low, cfg.h_high
    if lo <= hi:
        mask = cv2.inRange(hsv, (lo, cfg.s_min, cfg.v_min), (hi, 255, 255))
    else:  # 红/粉色可能跨 Hue=179/0 边界
        mask = cv2.bitwise_or(cv2.inRange(hsv, (lo, cfg.s_min, cfg.v_min), (179, 255, 255)),
                             cv2.inRange(hsv, (0, cfg.s_min, cfg.v_min), (hi, 255, 255)))
    roi_mask = np.zeros_like(mask)
    roi_mask[int(np.ceil(y0)):int(np.floor(y1)) + 1, int(np.ceil(x0)):int(np.floor(x1)) + 1] = 255
    mask = cv2.bitwise_and(mask, roi_mask)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    keep = np.zeros(count, dtype=np.uint8)
    keep[1:] = (stats[1:, cv2.CC_STAT_AREA] >= cfg.min_component) * 255
    mask = keep[labels]
    rectified = cv2.remap(mask, source[:, :, 0].astype(np.float32), source[:, :, 1].astype(np.float32),
                          cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT)
    # 连续中轴跟踪：同一列有多个色块时优先沿前一列位置延续。
    # 同色图例或第二条曲线仍可能干扰，须通过 ROI 和叠加预览人工验证。
    raw = np.full(cols, np.nan)
    ambiguous, clipped = 0, 0
    prev_row, prev_col = None, -10000
    for col in range(cols):
        hits = np.flatnonzero(rectified[:, col])
        if not len(hits):
            continue
        groups = np.split(hits, np.flatnonzero(np.diff(hits) > 1) + 1)
        if len(groups) > 1:
            ambiguous += 1
        centers = np.array([np.median(group) for group in groups])
        if prev_row is not None and col - prev_col <= cfg.max_gap + 1:
            chosen = int(np.argmin(np.abs(centers - prev_row)))
        else:
            chosen = int(np.argmax([len(group) for group in groups]))
        row = centers[chosen]
        srcp = transform([[ts[col], np.interp(row, np.arange(rows), ys)]], inverse)[0]
        # 裁剪振幅极值不可恢复。接触 ROI 上/下边或重采样边缘的点设为缺失，
        # 后续凡包含这些点的周期一律不统计，不以插值假装恢复被剪掉的峰谷。
        if row < 2 or row > rows - 3 or srcp[1] <= y0 + 2 or srcp[1] >= y1 - 2:
            raw[col] = np.inf  # 临时标志：禁止对边缘截断插值
            clipped += 1
            prev_row = None
            continue
        raw[col] = np.interp(row, np.arange(rows), ys)
        prev_row, prev_col = row, col
    blocked = np.isinf(raw)
    raw[blocked] = np.nan
    measured = np.isfinite(raw)
    if measured.sum() < 30:
        raise AnalysisError("有效曲线像素不足。请检查曲线颜色、分析区域与标定点。")
    filled = raw.copy()
    indices = np.flatnonzero(measured)
    filled_count = 0
    for a, b in zip(indices[:-1], indices[1:]):
        gap = b - a - 1
        if 0 < gap <= cfg.max_gap and not blocked[a:b + 1].any():
            filled[a:b + 1] = np.interp(ts[a:b + 1], ts[[a, b]], raw[[a, b]])
            filled_count += gap
    runs = np.split(np.flatnonzero(np.isfinite(filled)),
                    np.flatnonzero(np.diff(np.flatnonzero(np.isfinite(filled))) > 1) + 1)
    smooth = np.full(cols, np.nan)
    peak_indices, trough_indices = [], []
    extrema = {}
    candidates = {"peak": [], "trough": []}
    dt = float(ts[1] - ts[0])
    distance = max(1, int(np.ceil(cfg.min_extrema_spacing / dt)))
    for run in runs:
        if len(run) < 5:
            continue
        window = min(cfg.smooth_window, len(run) if len(run) % 2 else len(run) - 1)
        values = savgol_filter(filled[run], window, 2) if window >= 5 else filled[run]
        smooth[run] = values
        peaks = run[find_peaks(values, distance=distance, prominence=cfg.prominence)[0]]
        troughs = run[find_peaks(-values, distance=distance, prominence=cfg.prominence)[0]]
        # 粗线条的平顶会把波峰时间推移数个像素。用邻域二次曲线定位亚采样极值，
        # 邻域约为相邻反向极值间隔的24%，仍是局部测量，绝不使用后续周期拟合首周期。
        ordered = np.sort(np.concatenate((peaks, troughs)))
        for index in ordered:
            gaps = np.abs(ordered - index)
            nearest = int(gaps[gaps > 0].min()) if np.any(gaps > 0) else distance
            radius = min(max(4, int(round(nearest * .12))), int(index - run[0]), int(run[-1] - index))
            refined_t, refined_y = float(ts[index]), float(smooth[index])
            if radius >= 3:
                around = np.arange(index - radius, index + radius + 1)
                qa, qb, qc = np.polyfit((around - index).astype(float), smooth[around], 2)
                shift = -qb / (2 * qa) if abs(qa) > 1e-12 else np.inf
                correct_curvature = (qa < 0) if index in peaks else (qa > 0)
                if correct_curvature and abs(shift) <= radius:
                    refined_t = float(ts[index] + shift * dt)
                    refined_y = float(qa * shift ** 2 + qb * shift + qc)
            extrema[int(index)] = {"t": refined_t, "y": refined_y}
        peak_indices.extend(peaks.tolist())
        trough_indices.extend(troughs.tolist())
        for kind, anchors, others in [("peak", peaks, troughs), ("trough", troughs, peaks)]:
            for a, b in zip(anchors[:-1], anchors[1:]):
                inside = others[(others > a) & (others < b)]
                if len(inside) != 1:
                    continue  # 漏峰/多峰不默默当成一个周期
                mid = int(inside[0])
                boundary_level = float((extrema[int(a)]["y"] + extrema[int(b)]["y"]) / 2)
                opposite_level = extrema[mid]["y"]
                upper, lower = (boundary_level, opposite_level) if kind == "peak" else (opposite_level, boundary_level)
                amp = float((upper - lower) / 2)
                if amp <= 0:
                    continue
                candidates[kind].append({"start_index": int(a), "end_index": int(b),
                    "opposite_index": mid, "start": extrema[int(a)]["t"], "end": extrema[int(b)]["t"],
                    "period": float(extrema[int(b)]["t"] - extrema[int(a)]["t"]), "amplitude": amp,
                    "offset": float((upper + lower) / 2), "upper": float(upper), "lower": float(lower)})
    if not candidates["peak"] and not candidates["trough"]:
        raise AnalysisError("未找到完整周期（需两个同类极值及中间一个反向极值）。请检查裁剪、缺口、峰值间距和突出度。")
    # 采用最早可验证的完整极值到极值周期；全程保持同一种边界，避免周期重叠。
    kind = min((k for k in candidates if candidates[k]), key=lambda k: candidates[k][0]["start"])
    cycles = candidates[kind]
    first = cycles[0]
    a1, t1 = first["amplitude"], first["period"]
    offset = first["offset"] if cfg.include_offset else 0.0
    phase = float(((np.pi / 2 if kind == "peak" else -np.pi / 2) - 2 * np.pi * first["start"] / t1 + np.pi) % (2 * np.pi) - np.pi)
    for i, cycle in enumerate(cycles, 1):
        cycle.update(number=i,
            amplitude_change_pct=100 * (cycle["amplitude"] / a1 - 1),
            amplitude_decay_pct=100 * (1 - cycle["amplitude"] / a1),
            period_change_pct=100 * (cycle["period"] / t1 - 1),
            interpolated_points=int(np.sum(~measured[cycle["start_index"]:cycle["end_index"] + 1])))
    valid = measured & np.isfinite(smooth)
    first_valid = valid & (ts >= first["start"]) & (ts <= first["end"])
    all_metrics = metrics(ts[valid], raw[valid], a1, t1, phase, offset)
    first_metrics = metrics(ts[first_valid], raw[first_valid], a1, t1, phase, offset)
    ideal = offset + a1 * np.sin(2 * np.pi * ts / t1 + phase)
    if clipped:
        notes.append(f"{clipped} 列曲线接触分析区域的上/下边界，相关周期已排除；请扩大区域检查峰谷是否被裁剪。")
    if ambiguous:
        notes.append(f"{ambiguous} 列存在多个同色色块，请检查原图叠加，必要时缩小 ROI 排除图例或第二条曲线。")
    if filled_count:
        notes.append(f"对 {filled_count} 个短缺口采样点作了线性插值；误差指标仅使用实际提取点。")
    if len(runs) > 1:
        notes.append("曲线含长缺口，已分段；跨缺口周期不统计，周期编号仅表示可验证周期的顺序。")
    if t1 / dt < 30:
        notes.append("首周期不足 30 个采样点，时间和振幅分辨率较低，建议使用更清晰的原图。")
    if cfg.smooth_window * dt > t1 / 10:
        notes.append("平滑窗口超过首周期的 10%，可能压低振幅；建议减小窗口并比较结果。")
    if abs(first["offset"]) > 0.05 * a1 and not cfg.include_offset:
        notes.append("首周期中线明显偏离 y=0；请核对零点，或启用首周期中线偏置，偏置会在公式中明确显示。")
    notes.append("极值点处于图像两端时不作为已验证极值；首尾不完整周期不计入统计。")
    notes.append("三点标定不能识别透视误差；透视照片需四点校正。四点也不能消除镜头畸变或纸张弯曲。")
    amplitudes = np.array([c["amplitude"] for c in cycles])
    periods = np.array([c["period"] for c in cycles])
    def nullable(array):
        return [float(v) if np.isfinite(v) else None for v in array]
    pixel_points = transform(np.column_stack((ts[valid], raw[valid])), inverse)
    return {"cycles": cycles, "boundary_kind": kind,
        "standard": {"amplitude": a1, "period": t1, "phase": phase, "offset": offset},
        "metrics": {"all_observed": all_metrics, "first_cycle": first_metrics},
        "summary": {"cycle_count": len(cycles), "mean_amplitude": float(amplitudes.mean()),
            "mean_period": float(periods.mean()), "period_cv_pct": float(periods.std() / periods.mean() * 100),
            "last_amplitude_decay_pct": cycles[-1]["amplitude_decay_pct"],
            "amplitude_nonincreasing": bool(len(cycles) >= 2 and np.all(np.diff(amplitudes) <= 0)),
            "amplitude_monotonicity_tolerance": 0},
        "data": {"t": ts.tolist(), "raw": nullable(raw), "smooth": nullable(smooth),
            "standard": ideal.tolist(), "observed": measured.tolist(),
            "residual": nullable(np.where(valid, raw - ideal, np.nan)),
            "peaks": [extrema[i] for i in peak_indices],
            "troughs": [extrema[i] for i in trough_indices]},
        "calibration": {"matrix": matrix.tolist(), "inverse": inverse.tolist(),
            "mode": "perspective" if cfg.fourth_point else "affine", "dt": dt,
            "dy": float(abs(ys[1] - ys[0])), "center_one_pixel_t": float(scale_t),
            "center_one_pixel_y": float(scale_y), "roi": [x0, y0, x1, y1]},
        "preview": {"mask": png_url(rectified), "pixel_points": pixel_points.tolist()},
        "unit": cfg.unit, "warnings": notes,
        "settings": cfg.model_dump(), "image": {"width": width, "height": height}}
