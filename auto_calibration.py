"""自动标定适用于横平竖直、线性刻度清楚的截图；不通过一致性检查时拒绝猜刻度。"""
import itertools
import re
import threading

import cv2
import numpy as np

from analysis import AnalysisError, Settings, analyze

_engine = None
_ocr_lock = threading.Lock()


def groups(indices):
    if not len(indices):
        return []
    return np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)


def detect_axes(image):
    h, w = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    dark = ((gray < 175) & (hsv[:, :, 1] < 45)).astype(np.uint8) * 255
    # 彩色波形会覆盖坐标轴几个像素，先补轴线短缺口，再寻找长直线。
    horizontal = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((1, 11), np.uint8))
    horizontal = cv2.morphologyEx(horizontal, cv2.MORPH_OPEN, np.ones((1, max(30, w // 4)), np.uint8))
    vertical = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((11, 1), np.uint8))
    vertical = cv2.morphologyEx(vertical, cv2.MORPH_OPEN, np.ones((max(25, h // 5), 1), np.uint8))
    row_groups = groups(np.flatnonzero(np.count_nonzero(horizontal, axis=1) > w * .4))
    col_groups = groups(np.flatnonzero(np.count_nonzero(vertical, axis=0) > h * .35))
    candidates = []
    for rows, cols in itertools.product(row_groups, col_groups):
        y, x = int(np.median(rows)), int(np.median(cols))
        xs, ys = np.flatnonzero(horizontal[y]), np.flatnonzero(vertical[:, x])
        if len(xs) and len(ys) and xs.min() - 3 <= x <= xs.max() + 3 and ys.min() <= y <= ys.max():
            if x < w * .4:
                candidates.append((len(xs) + len(ys), x, y, int(xs.max()), int(ys.min()), int(ys.max())))
    if not candidates:
        raise AnalysisError("自动标定未找到清晰的水平、竖直坐标轴。请使用原始截图；斜拍图或无坐标轴图需手动标定。")
    _, x, y, right, top, bottom = max(candidates)
    if right - x < 60 or bottom - top < 45 or x < 12 or h - bottom < 15:
        raise AnalysisError("刻度文字可能被裁剪，无法自动建立物理坐标系，请保留完整坐标轴与刻度或使用手动标定。")
    return x, y, right, top, bottom


def read_text(crop, offset):
    global _engine
    padded = cv2.copyMakeBorder(crop, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    enlarged = cv2.resize(padded, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    with _ocr_lock:
        if _engine is None:
            from rapidocr_onnxruntime import RapidOCR
            # 本地推理模型随 EXE 打包，分析图片不需要网络。
            _engine = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
        result, _ = _engine(enlarged, use_cls=False)
    records = []
    for box, text, confidence in result or []:
        pos = np.mean(box, axis=0) / 4 - 12 + np.array(offset)
        normalized = text.strip().replace("−", "-").replace("–", "-").replace("，", ".").replace(" ", "")
        value = None
        if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", normalized):
            value = float(normalized)
            if not np.isfinite(value):
                value = None
        records.append({"x": float(pos[0]), "y": float(pos[1]), "text": text,
                        "value": value, "confidence": float(confidence)})
    return records


def grid_positions(image, bounds):
    left, _, right, top, bottom = bounds
    crop = image[top:bottom + 1, left:right + 1]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    mask = ((gray < 245) & (hsv[:, :, 1] < 30)).astype(np.uint8) * 255
    v = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 1), np.uint8))
    v = cv2.morphologyEx(v, cv2.MORPH_OPEN, np.ones((max(15, crop.shape[0] // 2), 1), np.uint8))
    h = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((1, 11), np.uint8))
    h = cv2.morphologyEx(h, cv2.MORPH_OPEN, np.ones((1, max(25, crop.shape[1] // 2)), np.uint8))
    x_groups = groups(np.flatnonzero(np.count_nonzero(v, axis=0) > crop.shape[0] * .55))
    y_groups = groups(np.flatnonzero(np.count_nonzero(h, axis=1) > crop.shape[1] * .55))
    return np.array([float(np.median(g) + left) for g in x_groups]), np.array([float(np.median(g) + top) for g in y_groups])


def fit_ticks(records, axis, positions, span):
    ticks = [dict(r) for r in records if r["value"] is not None and r["confidence"] >= .7]
    if axis == "x" and ticks:
        # 只取数字最多的一排，避免将下方按钮或其他文字中的数字当时间刻度。
        baseline = max((r["y"] for r in ticks), key=lambda y: sum(abs(t["y"] - y) < 12 for t in ticks))
        ticks = [r for r in ticks if abs(r["y"] - baseline) < 12]
    for tick in ticks:
        tick["pixel"] = tick[axis]
        if len(positions):
            nearest = float(positions[np.argmin(np.abs(positions - tick[axis]))])
            if abs(nearest - tick[axis]) <= max(4, span * .012):
                tick["pixel"] = nearest  # OCR 文字中心对齐到真实网格，避免字体宽度偏差。
    if len(ticks) < 3 or len({t["value"] for t in ticks}) < 3:
        raise AnalysisError(f"{'时间' if axis == 'x' else '位移'}轴可可靠识别的数字刻度不足3个，请使用完整清晰截图或手动标定。")
    pixel = np.array([t["pixel"] for t in ticks])
    value = np.array([t["value"] for t in ticks])
    tolerance = max(float(np.ptp(value)) * .015, 1e-8)
    best = None
    for i, j in itertools.combinations(range(len(ticks)), 2):
        if abs(pixel[j] - pixel[i]) < span * .15:
            continue
        slope = (value[j] - value[i]) / (pixel[j] - pixel[i])
        if (axis == "x" and slope <= 0) or (axis == "y" and slope >= 0):
            continue
        intercept = value[i] - slope * pixel[i]
        error = np.abs(value - (slope * pixel + intercept))
        inliers = error <= tolerance
        score = (int(inliers.sum()), -float(error[inliers].mean()) if inliers.any() else -np.inf)
        if best is None or score > best[0]:
            best = (score, inliers)
    if best is None or best[1].sum() < max(3, int(np.ceil(len(ticks) * .75))):
        raise AnalysisError("识别出的刻度不符合线性坐标，可能有 OCR 错误、透视或非线性刻度。请手动标定。")
    inliers = best[1]
    if np.ptp(pixel[inliers]) < span * .4:
        raise AnalysisError("可靠刻度覆盖范围过小，自动标定误差可能过大，请手动标定。")
    slope, intercept = np.polyfit(pixel[inliers], value[inliers], 1)
    residual = np.abs(value[inliers] - (slope * pixel[inliers] + intercept))
    if residual.max() > tolerance:
        raise AnalysisError("刻度拟合误差过大，请手动标定。")
    return float(slope), float(intercept), [ticks[i] for i in np.flatnonzero(inliers)], float(residual.max())


def auto_analyze(image, unit="纵轴单位", include_offset=False):
    bounds = detect_axes(image)
    x, y, right, top, bottom = bounds
    height, width = image.shape[:2]
    x_end = min(height, bottom + max(55, int(height * .23)))
    x_text = read_text(image[bottom + 2:x_end, max(0, x - 25):], (max(0, x - 25), bottom + 2))
    y_text = read_text(image[max(0, top - 10):min(height, bottom + 10), :max(1, x - 2)], (0, max(0, top - 10)))
    x_grid, y_grid = grid_positions(image, bounds)
    sx, bx, xticks, x_error = fit_ticks(x_text, "x", x_grid, right - x)
    sy, by, yticks, y_error = fit_ticks(y_text, "y", y_grid, bottom - top)
    notes = []
    # 未识别到明确时间单位时，沿用本工具的“秒”约定，必须在结果中提示。
    time_labels = " ".join(r["text"] for r in x_text).lower().replace(" ", "")
    time_factor = .001 if re.search(r"(?:\bms\b|毫秒)", time_labels) else 60 if re.search(r"(?:\bmin\b|分钟)", time_labels) else 1
    if not re.search(r"(?:\bs\b|秒|\bms\b|毫秒|\bmin\b|分钟)", time_labels):
        notes.append("未识别到横轴时间单位，按本工具默认的秒计算；请核对仪器单位。")
    sx, bx = sx * time_factor, bx * time_factor
    if unit == "纵轴单位":
        notes.append("图片位移单位未自动确定，振幅保留纵轴刻度单位；可在页面填写真实单位后重新分析。")
    hsv = cv2.cvtColor(image[top:bottom + 1, x:right + 1], cv2.COLOR_BGR2HSV)
    colored = (hsv[:, :, 1] >= 40) & (hsv[:, :, 2] >= 60)
    if colored.sum() < 40:
        raise AnalysisError("没有找到足够的彩色曲线像素，请手动取色。")
    hist = np.bincount(hsv[:, :, 0][colored], minlength=180).astype(float)
    histogram = np.array([sum(hist[(i + j) % 180] for j in range(-4, 5)) for i in range(180)])
    hue = int(np.argmax(histogram))
    hue_distance = np.minimum(np.abs(np.arange(180) - hue), 180 - np.abs(np.arange(180) - hue))
    if hist[hue_distance > 24].sum() > hist.sum() * .25:
        raise AnalysisError("分析区域内有多种显著曲线颜色，请手动选择曲线颜色及分析区域。")
    t0, y0 = sx * x + bx, sy * y + by
    x_anchor = max(xticks, key=lambda r: r["pixel"])
    y_anchor = min(yticks, key=lambda r: r["pixel"])
    cfg = Settings(origin={"x": x, "y": y}, x_point={"x": x_anchor["pixel"], "y": y},
        y_point={"x": x, "y": y_anchor["pixel"]}, t0=t0, y0=y0,
        x_value=sx * x_anchor["pixel"] + bx, y_value=sy * y_anchor["pixel"] + by,
        unit=unit, roi=[x, top, right, bottom], h_low=(hue - 12) % 180, h_high=(hue + 12) % 180,
        s_min=35, v_min=50, prominence=max(.02 * np.ptp([r["value"] for r in yticks]), 1e-8),
        min_extrema_spacing=max((sx * (right - x)) / 150, .000001), include_offset=include_offset)
    result = analyze(image, cfg)
    result["warnings"] = ["自动坐标标定：已用多个 OCR 数字刻度及线性一致性检验建立物理坐标系。请检查图上自动标记是否落在正确刻度。"] + notes + result["warnings"]
    result["automatic"] = {"x_ticks": xticks, "y_ticks": yticks, "x_max_fit_error": x_error * time_factor,
        "y_max_fit_error": y_error, "curve_hue": hue, "mode": "ocr_linear_axes", "time_unit_factor": time_factor}
    return result
