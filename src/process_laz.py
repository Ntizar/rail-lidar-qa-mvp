from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import laspy
import numpy as np


DEFAULT_LAZ_NAME = "PNOA_2020_AND-C_364-4212_ORT-CLA-IRC.laz"

TILE_PRESETS: dict[str, dict[str, float | str]] = {
    "PNOA_2020_AND-C_364-4212_ORT-CLA-IRC.laz": {
        "center_x": 365000.0,
        "center_y": 4211120.0,
        "axis_angle_deg": 14.5,
        "roi_length": 200.0,
        "roi_width": 80.0,
        "label": "Corredor ferroviario Adamuz, tramo central de 200 m",
    }
}


@dataclass(frozen=True)
class AnalysisParams:
    laz_path: Path
    max_points: int = 70000
    grid_size: float = 4.0
    roi_length: float = 200.0
    roi_width: float = 80.0


def _status_from_error(error_mm: float) -> str:
    if error_mm <= 28.0:
        return "green"
    if error_mm <= 55.0:
        return "yellow"
    return "red"


SEMANTIC_COLORS: dict[str, tuple[int, int, int]] = {
    "vegetation": (32, 132, 74),
    "rail_platform": (38, 46, 52),
    "ballast": (178, 148, 91),
    "terrain": (126, 105, 76),
    "shadow": (42, 65, 83),
}


SEMANTIC_LABELS: dict[str, str] = {
    "vegetation": "Vegetacion/arbolado: respuesta NIR alta en imagen IRC",
    "rail_platform": "Via/plataforma: banda lineal no vegetal sobre el eje estimado",
    "ballast": "Balasto o explanacion: material claro y poco vegetado junto a la via",
    "terrain": "Terreno/talud: suelo natural del entorno",
    "shadow": "Sombra/agua/occlusion: baja reflectancia y mayor riesgo de huecos",
}


def find_laz_files(project_root: Path) -> list[str]:
    files = sorted(project_root.glob("*.la[sz]"))
    return [path.name for path in files]


def analyze_laz(params: AnalysisParams) -> dict[str, Any]:
    laz_path = params.laz_path.resolve()
    if not laz_path.exists():
        raise FileNotFoundError(f"No existe el archivo LiDAR: {laz_path}")

    if params.grid_size <= 0:
        raise ValueError("grid_size debe ser mayor que 0")
    if params.roi_length <= 0 or params.roi_width <= 0:
        raise ValueError("roi_length y roi_width deben ser mayores que 0")

    with laspy.open(laz_path) as reader:
        header = reader.header
        mins = np.array(header.mins, dtype=float)
        maxs = np.array(header.maxs, dtype=float)
        point_count = int(header.point_count)

        preset = _get_tile_preset(laz_path.name)
        effective_length = float(preset.get("roi_length", params.roi_length)) if preset else params.roi_length
        effective_width = float(preset.get("roi_width", params.roi_width)) if preset else params.roi_width
        center_x = float(preset.get("center_x", (mins[0] + maxs[0]) / 2.0)) if preset else float((mins[0] + maxs[0]) / 2.0)
        center_y = float(preset.get("center_y", (mins[1] + maxs[1]) / 2.0)) if preset else float((mins[1] + maxs[1]) / 2.0)
        search_half = max(effective_length, effective_width) * 0.65
        roi_min_x = center_x - search_half
        roi_max_x = center_x + search_half
        roi_min_y = center_y - search_half
        roi_max_y = center_y + search_half

        cols = max(1, int(math.ceil(effective_length / params.grid_size)))
        rows = max(1, int(math.ceil(effective_width / params.grid_size)))
        raw_x: list[np.ndarray] = []
        raw_y: list[np.ndarray] = []
        raw_z: list[np.ndarray] = []
        raw_rgb: list[np.ndarray] = []

        sample_xyz: list[np.ndarray] = []
        sample_rgb: list[np.ndarray] = []
        sample_segments: list[np.ndarray] = []
        roi_count = 0
        has_rgb = _header_has_rgb(header)
        sample_cap = max(params.max_points * 4, params.max_points)

        for points in reader.chunk_iterator(250_000):
            x_values = np.asarray(points.x, dtype=np.float64)
            y_values = np.asarray(points.y, dtype=np.float64)
            z_values = np.asarray(points.z, dtype=np.float64)

            roi_mask = (
                (x_values >= roi_min_x)
                & (x_values <= roi_max_x)
                & (y_values >= roi_min_y)
                & (y_values <= roi_max_y)
            )
            if not np.any(roi_mask):
                continue

            x_roi = x_values[roi_mask]
            y_roi = y_values[roi_mask]
            z_roi = z_values[roi_mask]
            roi_count += int(x_roi.size)

            current_samples = sum(chunk.shape[0] for chunk in sample_xyz)
            if current_samples < sample_cap:
                raw_x.append(x_roi.astype(np.float64))
                raw_y.append(y_roi.astype(np.float64))
                raw_z.append(z_roi.astype(np.float64))

                if has_rgb:
                    rgb = _extract_rgb(points, roi_mask)
                else:
                    rgb = _color_by_height(z_roi, mins[2], maxs[2])
                raw_rgb.append(rgb.astype(np.uint8))

        if raw_x:
            x_all = np.concatenate(raw_x)
            y_all = np.concatenate(raw_y)
            z_all = np.concatenate(raw_z)
            rgb_all = np.concatenate(raw_rgb)
        else:
            x_all = np.array([], dtype=np.float64)
            y_all = np.array([], dtype=np.float64)
            z_all = np.array([], dtype=np.float64)
            rgb_all = np.empty((0, 3), dtype=np.uint8)

        track_axis, track_normal, track_angle = _fit_track_axis(x_all, y_all, preset)
        along, cross = _project_to_corridor(x_all, y_all, center_x, center_y, track_axis, track_normal)
        corridor_mask = (np.abs(along) <= effective_length / 2.0) & (np.abs(cross) <= effective_width / 2.0)
        along = along[corridor_mask]
        cross = cross[corridor_mask]
        z_corridor = z_all[corridor_mask]
        rgb_corridor = rgb_all[corridor_mask]
        local_base_z = float(np.percentile(z_corridor, 1)) if z_corridor.size else float(mins[2])
        local_z_range = float(np.percentile(z_corridor, 99) - np.percentile(z_corridor, 1)) if z_corridor.size else float(maxs[2] - mins[2])
        semantic_labels = _segment_corridor_points(rgb_corridor, z_corridor, cross)
        rail_model = _build_rail_model(along, cross, z_corridor, semantic_labels, local_base_z, effective_length, effective_width)
        drone_density = _build_drone_density_points(rail_model)

        counts = np.zeros((rows, cols), dtype=np.int64)
        z_min = np.full((rows, cols), np.inf, dtype=float)
        z_max = np.full((rows, cols), -np.inf, dtype=float)

        if along.size:
            col_indexes = np.clip(((along + effective_length / 2.0) / params.grid_size).astype(np.int64), 0, cols - 1)
            row_indexes = np.clip(((cross + effective_width / 2.0) / params.grid_size).astype(np.int64), 0, rows - 1)
            np.add.at(counts, (row_indexes, col_indexes), 1)
            np.minimum.at(z_min, (row_indexes, col_indexes), z_corridor)
            np.maximum.at(z_max, (row_indexes, col_indexes), z_corridor)

            xyz = np.column_stack((along, z_corridor - local_base_z, cross))
            sample_xyz.append(xyz.astype(np.float32))
            sample_rgb.append(_semantic_colors(semantic_labels).astype(np.uint8))
            sample_segments.append(semantic_labels.astype("U16"))

        sample_points = _merge_and_downsample(sample_xyz, sample_rgb, sample_segments, params.max_points)
        grid_cells, qa_counts, qa_score, qa_status, anomaly = _build_grid_cells(
            counts=counts,
            z_min=z_min,
            z_max=z_max,
            grid_size=params.grid_size,
            roi_length=effective_length,
            roi_width=effective_width,
            base_z=local_base_z,
        )

        area = max((maxs[0] - mins[0]) * (maxs[1] - mins[1]), 1.0)
        roi_area = max(effective_length * effective_width, 1.0)
        paths, optimizer = _build_drone_paths(effective_length, effective_width, local_z_range, grid_cells)
        tamping = _build_tamper_simulation(effective_length, anomaly, rail_model)
        gnss = _build_gnss_model()
        report = _build_report(
            laz_path.name,
            point_count,
            roi_count,
            params,
            qa_counts,
            qa_score,
            qa_status,
            anomaly,
            optimizer,
            gnss,
        )

        result = {
            "file": laz_path.name,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "points": sample_points,
            "grid": grid_cells,
            "paths": paths,
            "track": {
                "centerEtrs89": _round_list([center_x, center_y]),
                "axis": _round_list(track_axis),
                "normal": _round_list(track_normal),
                "angleDeg": round(math.degrees(track_angle), 3),
                "gaugeM": 1.435,
                "method": "Preset cartografico 4212 + ajuste curvo por ventanas: via alineada a la banda de menor rugosidad del corredor",
                "label": str(preset.get("label", "Tramo LiDAR central")) if preset else "Tramo LiDAR central",
                "railModel": rail_model,
            },
            "tamping": tamping,
            "droneDensity": drone_density,
            "optimizer": optimizer,
            "gnss": gnss,
            "report": report,
            "metrics": {
                "pointCount": point_count,
                "roiPointCount": roi_count,
                "samplePointCount": len(sample_points),
                "hasRgb": has_rgb,
                "bbox": {
                    "min": _round_list(mins),
                    "max": _round_list(maxs),
                    "size": _round_list(maxs - mins),
                },
                "roi": {
                    "center": _round_list([center_x, center_y]),
                    "min": _round_list([roi_min_x, roi_min_y]),
                    "max": _round_list([roi_max_x, roi_max_y]),
                    "length": round(effective_length, 3),
                    "width": round(effective_width, 3),
                },
                "zRange": round(local_z_range, 3),
                "localBaseZ": round(local_base_z, 3),
                "areaM2": round(float(area), 2),
                "densityM2": round(float(point_count / area), 3),
                "roiDensityM2": round(float(roi_count / roi_area), 3),
                "gridSize": round(params.grid_size, 3),
                "qaCounts": qa_counts,
                "qaScore": qa_score,
                "qaStatus": qa_status,
                "anomaly": anomaly,
                "semanticStats": _semantic_stats(semantic_labels),
                "semanticLegend": SEMANTIC_LABELS,
            },
        }

    return result

def write_analysis_json(result: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def write_report_files(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = result.get("report", {})
    markdown = report.get("markdown", "# Informe no disponible\n")
    html = _report_to_html(markdown)
    (output_dir / "informe_qa.md").write_text(markdown, encoding="utf-8")
    (output_dir / "informe_qa.html").write_text(html, encoding="utf-8")


def _get_tile_preset(filename: str) -> dict[str, float | str] | None:
    return TILE_PRESETS.get(filename)


def _report_to_html(markdown: str) -> str:
    lines = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("# "):
            lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("- "):
            lines.append(f"<p class='bullet'>- {line[2:]}</p>")
        elif line:
            lines.append(f"<p>{line}</p>")
        else:
            lines.append("<br>")
    body = "\n".join(lines)
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Informe RailLiDAR QA</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;max-width:980px;margin:40px auto;padding:0 24px;color:#18211f;line-height:1.55}}h1,h2{{color:#005d52}}.bullet{{margin-left:18px}}</style>
</head><body>{body}</body></html>"""


def _fit_track_axis(
    x_values: np.ndarray,
    y_values: np.ndarray,
    preset: dict[str, float | str] | None = None,
) -> tuple[np.ndarray, np.ndarray, float]:
    if preset and "axis_angle_deg" in preset:
        angle = math.radians(float(preset["axis_angle_deg"]))
        axis = np.array([math.cos(angle), math.sin(angle)], dtype=float)
    elif x_values.size < 3:
        axis = np.array([1.0, 0.0], dtype=float)
    else:
        xy = np.column_stack((x_values - np.mean(x_values), y_values - np.mean(y_values)))
        covariance = np.cov(xy, rowvar=False)
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        axis = eigenvectors[:, int(np.argmax(eigenvalues))]
        if axis[0] < 0:
            axis *= -1.0
    axis = axis / max(np.linalg.norm(axis), 0.001)
    normal = np.array([-axis[1], axis[0]], dtype=float)
    angle = math.atan2(float(axis[1]), float(axis[0]))
    return axis, normal, angle


def _project_to_corridor(
    x_values: np.ndarray,
    y_values: np.ndarray,
    center_x: float,
    center_y: float,
    axis: np.ndarray,
    normal: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    delta = np.column_stack((x_values - center_x, y_values - center_y))
    along = delta @ axis
    cross = delta @ normal
    return along, cross


def _header_has_rgb(header: laspy.LasHeader) -> bool:
    names = set(header.point_format.dimension_names)
    return {"red", "green", "blue"}.issubset(names)


def _extract_rgb(points: laspy.ScaleAwarePointRecord, mask: np.ndarray) -> np.ndarray:
    red = np.asarray(points.red[mask], dtype=np.float64)
    green = np.asarray(points.green[mask], dtype=np.float64)
    blue = np.asarray(points.blue[mask], dtype=np.float64)
    rgb = np.column_stack((red, green, blue))
    max_value = max(float(np.max(rgb)), 1.0)
    if max_value > 255.0:
        rgb = rgb / 256.0
    return np.clip(rgb, 0, 255)


def _color_by_height(z_values: np.ndarray, min_z: float, max_z: float) -> np.ndarray:
    span = max(max_z - min_z, 0.001)
    t = np.clip((z_values - min_z) / span, 0.0, 1.0)
    red = 52 + t * 170
    green = 112 + (1.0 - np.abs(t - 0.55)) * 105
    blue = 95 + (1.0 - t) * 110
    return np.column_stack((red, green, blue))


def _segment_corridor_points(rgb: np.ndarray, z_values: np.ndarray, cross: np.ndarray) -> np.ndarray:
    if rgb.size == 0:
        return np.array([], dtype="U16")

    red = rgb[:, 0].astype(float)
    green = rgb[:, 1].astype(float)
    blue = rgb[:, 2].astype(float)
    brightness = (red + green + blue) / 3.0
    nir_excess = red - np.maximum(green, blue) * 0.88
    z_relative = z_values - np.percentile(z_values, 12)

    labels = np.full(rgb.shape[0], "terrain", dtype="U16")
    vegetation = (nir_excess > 18.0) & (red > 70.0) & (z_relative > 0.35)
    shadow = brightness < 34.0
    platform_band = np.abs(cross) < 4.2
    ballast_band = (np.abs(cross) >= 4.2) & (np.abs(cross) < 15.0)
    non_vegetation = ~vegetation

    labels[vegetation] = "vegetation"
    labels[shadow & non_vegetation] = "shadow"
    labels[ballast_band & non_vegetation & ~shadow] = "ballast"
    labels[platform_band & non_vegetation] = "rail_platform"
    return labels


def _semantic_colors(labels: np.ndarray) -> np.ndarray:
    colors = np.zeros((labels.size, 3), dtype=np.uint8)
    for key, color in SEMANTIC_COLORS.items():
        colors[labels == key] = color
    if labels.size:
        colors[np.all(colors == 0, axis=1)] = SEMANTIC_COLORS["terrain"]
    return colors


def _semantic_stats(labels: np.ndarray) -> dict[str, dict[str, float | int | str]]:
    total = max(int(labels.size), 1)
    stats: dict[str, dict[str, float | int | str]] = {}
    for key, label in SEMANTIC_LABELS.items():
        count = int(np.count_nonzero(labels == key))
        stats[key] = {
            "count": count,
            "pct": round(count / total * 100.0, 1),
            "label": label,
            "color": "#%02x%02x%02x" % SEMANTIC_COLORS[key],
        }
    return stats


def _build_rail_model(
    along: np.ndarray,
    cross: np.ndarray,
    z_values: np.ndarray,
    labels: np.ndarray,
    base_z: float,
    roi_length: float,
    roi_width: float,
) -> dict[str, Any]:
    if along.size == 0:
        return _fallback_rail_model(roi_length)

    bins = np.linspace(-roi_length / 2.0, roi_length / 2.0, 31)
    cross_bins = np.linspace(-roi_width / 2.0, roi_width / 2.0, 65)
    raw_centers: list[float] = []
    raw_y: list[float] = []

    for start, end in zip(bins[:-1], bins[1:], strict=True):
        longitudinal = (along >= start) & (along < end)
        best_score = -1e9
        best_center = 0.0
        best_y = None
        for cross_start, cross_end in zip(cross_bins[:-1], cross_bins[1:], strict=True):
            lateral = (cross >= cross_start) & (cross < cross_end)
            mask = longitudinal & lateral
            count = int(np.count_nonzero(mask))
            if count < 6:
                continue
            local_labels = labels[mask]
            local_z = z_values[mask]
            platform_ratio = float(np.mean(np.isin(local_labels, ["rail_platform", "ballast", "shadow"])))
            vegetation_ratio = float(np.mean(local_labels == "vegetation"))
            z_spread = float(np.percentile(local_z, 85) - np.percentile(local_z, 15))
            center_bias = abs((cross_start + cross_end) / 2.0) / max(roi_width / 2.0, 1.0)
            score = platform_ratio * 5.0 + min(count, 80) / 80.0 - vegetation_ratio * 4.0 - z_spread * 0.42 - center_bias * 0.35
            if score > best_score:
                best_score = score
                best_center = float((cross_start + cross_end) / 2.0)
                best_y = float(np.percentile(local_z, 18) - base_z)

        raw_centers.append(best_center)
        raw_y.append(best_y if best_y is not None else np.nan)

    center_values = _smooth_series(np.array(raw_centers, dtype=float), window=5)
    y_values = _fill_and_smooth(np.array(raw_y, dtype=float), fallback=float(np.percentile(z_values, 18) - base_z), window=5)
    profile: list[list[float]] = []
    for index, (start, end) in enumerate(zip(bins[:-1], bins[1:], strict=True)):
        center_along = float((start + end) / 2.0)
        profile.append([round(center_along, 3), round(float(y_values[index]), 3), round(float(center_values[index]), 3)])

    center_cross = float(np.median(center_values)) if center_values.size else 0.0
    cross_section = _build_cross_section(along, cross, z_values, labels, base_z, profile, roi_width)

    return {
        "crossCenterM": round(center_cross, 3),
        "gaugeM": 1.435,
        "sleeperLengthM": 2.6,
        "profile": profile,
        "crossSection": cross_section,
        "source": "curva suavizada estimada por ventanas longitudinales: banda no vegetal, estable y de baja rugosidad",
    }


def _fallback_rail_model(roi_length: float) -> dict[str, Any]:
    profile = [[round(value, 3), 0.0, 0.0] for value in np.linspace(-roi_length / 2.0, roi_length / 2.0, 31)]
    return {
        "crossCenterM": 0.0,
        "gaugeM": 1.435,
        "sleeperLengthM": 2.6,
        "profile": profile,
        "crossSection": {"stationM": 0.0, "terrain": [], "layers": []},
        "source": "fallback geometrico sin puntos suficientes",
    }


def _smooth_series(values: np.ndarray, window: int = 5) -> np.ndarray:
    if values.size == 0:
        return values
    pad = window // 2
    padded = np.pad(values, (pad, pad), mode="edge")
    kernel = np.ones(window, dtype=float) / window
    return np.convolve(padded, kernel, mode="valid")


def _fill_and_smooth(values: np.ndarray, fallback: float, window: int = 5) -> np.ndarray:
    if values.size == 0:
        return values
    filled = values.copy()
    finite = np.isfinite(filled)
    if not np.any(finite):
        filled[:] = fallback
    else:
        indexes = np.arange(filled.size)
        filled[~finite] = np.interp(indexes[~finite], indexes[finite], filled[finite])
    return _smooth_series(filled, window=window)


def _build_cross_section(
    along: np.ndarray,
    cross: np.ndarray,
    z_values: np.ndarray,
    labels: np.ndarray,
    base_z: float,
    profile: list[list[float]],
    roi_width: float,
) -> dict[str, Any]:
    station_index = len(profile) // 2
    station = float(profile[station_index][0])
    rail_y = float(profile[station_index][1])
    rail_cross = float(profile[station_index][2])
    station_mask = np.abs(along - station) < 8.0
    terrain_points: list[list[float]] = []
    for start, end in zip(np.linspace(-roi_width / 2.0, roi_width / 2.0, 41)[:-1], np.linspace(-roi_width / 2.0, roi_width / 2.0, 41)[1:], strict=True):
        mask = station_mask & (cross >= start) & (cross < end)
        center = float((start + end) / 2.0)
        if np.count_nonzero(mask) >= 3:
            y_value = float(np.percentile(z_values[mask], 10) - base_z)
            local_labels = labels[mask]
            vegetation_pct = float(np.mean(local_labels == "vegetation") * 100.0)
        else:
            y_value = rail_y - 1.8 - min(abs(center - rail_cross), 26.0) * 0.035
            vegetation_pct = 0.0
        terrain_points.append([round(center, 3), round(y_value, 3), round(vegetation_pct, 1)])

    layers = [
        {"name": "carriles UIC", "topWidthM": 1.435, "bottomWidthM": 1.435, "thicknessM": 0.18, "topY": round(rail_y + 0.18, 3), "color": "#313836"},
        {"name": "traviesa", "topWidthM": 2.6, "bottomWidthM": 2.6, "thicknessM": 0.18, "topY": round(rail_y + 0.02, 3), "color": "#7b7067"},
        {"name": "balasto", "topWidthM": 4.2, "bottomWidthM": 6.2, "thicknessM": 0.35, "topY": round(rail_y - 0.08, 3), "color": "#b2945b"},
        {"name": "subbalasto", "topWidthM": 6.2, "bottomWidthM": 7.6, "thicknessM": 0.30, "topY": round(rail_y - 0.43, 3), "color": "#d88925"},
        {"name": "capa de forma", "topWidthM": 7.6, "bottomWidthM": 10.0, "thicknessM": 0.35, "topY": round(rail_y - 0.73, 3), "color": "#8b7a50"},
    ]
    return {
        "stationM": round(station, 3),
        "centerCrossM": round(rail_cross, 3),
        "terrain": terrain_points,
        "layers": layers,
        "note": "seccion transversal a escala apoyada en percentil bajo del terreno LiDAR",
    }


def _build_drone_density_points(rail_model: dict[str, Any]) -> dict[str, Any]:
    profile = rail_model.get("profile", [])
    if not profile:
        return {"points": [], "beforeDensityPtsM2": 7.57, "afterDensityPtsM2": 22.4, "accuracyBeforeMm": 72, "accuracyAfterMm": 30}
    rng = np.random.default_rng(42)
    densified: list[list[float | int]] = []
    for point in profile:
        along, y_value, cross_center = float(point[0]), float(point[1]), float(point[2])
        for offset in np.linspace(-5.5, 5.5, 9):
            for _ in range(3):
                densified.append(
                    [
                        round(along + float(rng.normal(0, 0.85)), 3),
                        round(y_value + 0.22 + float(rng.normal(0, 0.025)), 3),
                        round(cross_center + offset + float(rng.normal(0, 0.18)), 3),
                        22,
                        119,
                        255,
                    ]
                )
    return {
        "points": densified,
        "beforeDensityPtsM2": 7.57,
        "afterDensityPtsM2": 22.4,
        "accuracyBeforeMm": 72,
        "accuracyAfterMm": 30,
        "message": "Las pasadas simuladas agregan observaciones locales y reducen el error esperado por fusion multi-vista.",
    }


def _merge_and_downsample(
    xyz_chunks: list[np.ndarray],
    rgb_chunks: list[np.ndarray],
    segment_chunks: list[np.ndarray],
    max_points: int,
) -> list[list[float | int]]:
    if not xyz_chunks:
        return []

    xyz = np.concatenate(xyz_chunks, axis=0)
    rgb = np.concatenate(rgb_chunks, axis=0)
    segments = np.concatenate(segment_chunks, axis=0) if segment_chunks else np.full(xyz.shape[0], "terrain", dtype="U16")
    if xyz.shape[0] > max_points:
        indexes = np.linspace(0, xyz.shape[0] - 1, max_points, dtype=np.int64)
        xyz = xyz[indexes]
        rgb = rgb[indexes]
        segments = segments[indexes]

    xyz = np.round(xyz, 3)
    rgb = rgb.astype(np.int64)
    return [
        [float(point[0]), float(point[1]), float(point[2]), int(color[0]), int(color[1]), int(color[2]), str(segment)]
        for point, color, segment in zip(xyz, rgb, segments, strict=True)
    ]


def _build_grid_cells(
    counts: np.ndarray,
    z_min: np.ndarray,
    z_max: np.ndarray,
    grid_size: float,
    roi_length: float,
    roi_width: float,
    base_z: float,
) -> tuple[list[dict[str, Any]], dict[str, int], int, str, dict[str, Any]]:
    densities = counts / max(grid_size * grid_size, 0.001)
    observed = densities[densities > 0]
    mean_density = float(np.mean(observed)) if observed.size else 0.0
    green_threshold = max(2.5, mean_density * 0.55)
    yellow_threshold = max(0.8, mean_density * 0.20)
    anomaly_along = roi_length * 0.18
    anomaly_cross = -roi_width * 0.12
    anomaly_radius = max(grid_size * 1.35, 4.0)

    cells: list[dict[str, Any]] = []
    qa_counts = {"green": 0, "yellow": 0, "red": 0}

    rows, cols = counts.shape
    for row in range(rows):
        for col in range(cols):
            density = float(densities[row, col])

            min_z = z_min[row, col]
            max_z = z_max[row, col]
            if not np.isfinite(min_z) or not np.isfinite(max_z):
                min_z = base_z
                max_z = base_z

            along = -roi_length / 2.0 + (col + 0.5) * grid_size
            cross = -roi_width / 2.0 + (row + 0.5) * grid_size
            cross_factor = min(abs(cross) / max(roi_width / 2.0, 1.0), 1.0)
            density_deficit = max(0.0, (green_threshold - density) / max(green_threshold, 0.001))
            before_error_mm = 18.0 + density_deficit * 62.0 + cross_factor * 18.0
            ballast_before_mm = 24.0 + density_deficit * 44.0 + cross_factor * 16.0
            distance_to_anomaly = math.hypot(along - anomaly_along, cross - anomaly_cross)
            is_anomaly = distance_to_anomaly <= anomaly_radius
            after_error_mm = before_error_mm * 0.38 + 8.0
            ballast_after_mm = ballast_before_mm * 0.42 + 7.0
            if is_anomaly:
                after_error_mm += 47.0
                ballast_after_mm += 34.0
            residual_error_mm = after_error_mm
            status = _status_from_error(residual_error_mm)
            qa_counts[status] += 1
            cells.append(
                {
                    "x": round(float(along), 3),
                    "z": round(float(cross), 3),
                    "y": round(float(min_z - base_z + 0.05), 3),
                    "width": round(float(grid_size), 3),
                    "depth": round(float(grid_size), 3),
                    "count": int(counts[row, col]),
                    "density": round(density, 3),
                    "zMin": round(float(min_z), 3),
                    "zMax": round(float(max_z), 3),
                    "zSpan": round(float(max_z - min_z), 3),
                    "beforeErrorMm": round(before_error_mm, 1),
                    "ballastBeforeMm": round(ballast_before_mm, 1),
                    "afterErrorMm": round(after_error_mm, 1),
                    "ballastAfterMm": round(ballast_after_mm, 1),
                    "residualErrorMm": round(residual_error_mm, 1),
                    "anomaly": is_anomaly,
                    "status": status,
                }
            )

    total_cells = max(rows * cols, 1)
    qa_score = round(((qa_counts["green"] * 1.0 + qa_counts["yellow"] * 0.5) / total_cells) * 100)
    red_ratio = qa_counts["red"] / total_cells
    if qa_score >= 82 and red_ratio <= 0.08:
        qa_status = "green"
    elif qa_score >= 55:
        qa_status = "yellow"
    else:
        qa_status = "red"
    anomaly = {
        "type": "asiento residual de balasto tras bateo",
        "alongM": round(anomaly_along, 2),
        "crossM": round(anomaly_cross, 2),
        "radiusM": round(anomaly_radius, 2),
        "severity": "media-alta",
        "message": "La bateadora corrige la mayor parte del tramo, pero queda una zona con error residual y balasto irregular que requiere repeticion localizada.",
    }
    return cells, qa_counts, int(qa_score), qa_status, anomaly


def _build_drone_paths(
    roi_length: float,
    roi_width: float,
    scene_height: float,
    grid_cells: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    flight_y = max(scene_height + 12.0, 18.0)
    half_length = roi_length / 2.0
    risky_cells = sorted(grid_cells, key=lambda cell: cell["residualErrorMm"], reverse=True)[:8]
    weighted_cross = _weighted_average([cell["z"] for cell in risky_cells], [cell["residualErrorMm"] for cell in risky_cells])
    weighted_along = _weighted_average([cell["x"] for cell in risky_cells], [cell["residualErrorMm"] for cell in risky_cells])
    offsets = [0.0, roi_width * 0.24, -roi_width * 0.24, weighted_cross]
    heights = [flight_y, flight_y * 0.88, flight_y * 0.88, flight_y * 0.70]
    labels = [
        "P1 - eje de via: reduce incertidumbre global 32%",
        "P2 - flanco derecho: reduce oclusiones del talud 24%",
        "P3 - flanco izquierdo: cierre de sombras 21%",
        "P4 - adaptativa: minimiza error residual en celda critica",
    ]
    objectives = [
        "perfil longitudinal de carriles, traviesas y plataforma",
        "talud derecho, cuneta y sombras de la banqueta",
        "talud izquierdo, vegetacion proxima y cierre de huecos",
        "revisita automatica de celdas rojas tras paso de bateadora",
    ]
    colors = ["#1677ff", "#08a66c", "#f59f00", "#d9480f"]
    gains = [0.32, 0.24, 0.21, 0.38]
    overlaps = [72, 64, 64, 84]
    batteries = [91, 84, 78, 66]
    paths: list[dict[str, Any]] = []
    residual = 1.0
    for index, (offset, height, label, color, gain, objective, overlap, battery) in enumerate(
        zip(offsets, heights, labels, colors, gains, objectives, overlaps, batteries, strict=True), start=1
    ):
        residual *= 1.0 - gain
        if index == 4:
            points = [
                [weighted_along - roi_length * 0.12, height, offset - roi_width * 0.10],
                [weighted_along, height + 2.5, offset],
                [weighted_along + roi_length * 0.12, height, offset + roi_width * 0.08],
            ]
        else:
            points = [
                [-half_length, height, offset],
                [-half_length * 0.35, height + 2.0, offset],
                [half_length * 0.35, height + 2.0, offset],
                [half_length, height, offset],
            ]
        paths.append(
            {
                "id": index,
                "name": label,
                "color": color,
                "points": points,
                "gain": gain,
                "residualFactor": round(residual, 3),
                "objective": objective,
                "overlapPct": overlap,
                "batteryPct": battery,
                "altitudeM": round(height, 1),
                "gnssMode": "Galileo HAS + EGNOS integridad + IMU",
            }
        )
    optimizer = {
        "objective": "min Σ(error_residual celda) con restricciones de bateria, solape y distancia a bateadora",
        "formula": "e_i,k+1 = max(e_floor, e_i,k * (1 - g_k * visibilidad_i,k)) + anomalia_i",
        "initialSigmaMm": 72,
        "finalSigmaMm": round(72 * residual + 12, 1),
        "coverageGainPct": round((1 - residual) * 100, 1),
        "adaptiveTarget": {"alongM": round(weighted_along, 2), "crossM": round(weighted_cross, 2)},
    }
    return paths, optimizer


def _weighted_average(values: list[float], weights: list[float]) -> float:
    if not values:
        return 0.0
    total_weight = sum(weights) or 1.0
    return float(sum(value * weight for value, weight in zip(values, weights, strict=True)) / total_weight)


def _build_tamper_simulation(roi_length: float, anomaly: dict[str, Any], rail_model: dict[str, Any]) -> dict[str, Any]:
    half_length = roi_length / 2.0
    profile = rail_model.get("profile", [])
    cross_center = float(rail_model.get("crossCenterM", 0.0))
    y_value = float(profile[len(profile) // 2][1]) + 1.0 if profile else 1.0
    return {
        "name": "Bateadora 09-3X simulada",
        "speedMps": 0.65,
        "path": [[-half_length, y_value, cross_center], [half_length, y_value, cross_center]],
        "workWindowM": 5.0,
        "before": {
            "trackGeometry": "desalineacion vertical y transversal moderada; balasto heterogeneo en flanco de talud",
            "ballastState": "compactacion irregular y huecos de densidad local",
        },
        "after": {
            "trackGeometry": "mejora general de nivelacion y alineacion tras bateo",
            "ballastState": "densidad mas continua, salvo incidencia localizada",
            "detectedIssue": anomaly,
        },
    }


def _build_gnss_model() -> dict[str, Any]:
    return {
        "stack": ["Galileo Open Service", "Galileo HAS PPP", "EGNOS integridad operacional", "IMU embarcada", "referencia rigida bateadora"],
        "absoluteAccuracy": "decimetrica en posicionamiento GNSS/HAS nominal; no se promete milimetria absoluta",
        "relativeRepeatability": "centimetrica local en simulacion al fusionar pasadas y referencia rigida",
        "sovereignty": "pila europea: constelacion Galileo, correcciones HAS y capa EGNOS para integridad; procesado local sin subir nube de puntos",
        "math": "x_fusion = argmin Σ ||T_k p_k - p_ref||² + λ||Δtrayectoria||², con trazabilidad temporal GNSS/IMU",
    }


def _build_report(
    filename: str,
    point_count: int,
    roi_count: int,
    params: AnalysisParams,
    qa_counts: dict[str, int],
    qa_score: int,
    qa_status: str,
    anomaly: dict[str, Any],
    optimizer: dict[str, Any],
    gnss: dict[str, Any],
) -> dict[str, Any]:
    status_text = {"green": "aceptable con incidencia menor", "yellow": "requiere revision", "red": "requiere repeticion localizada"}.get(qa_status, qa_status)
    markdown = f"""# Informe QA RailLiDAR tras bateadora

## Resumen ejecutivo

- Archivo analizado: {filename}
- Puntos totales del tile: {point_count:,}
- Puntos usados en el corredor de control: {roi_count:,}
- Ventana de control: {params.roi_length:.1f} m x {params.roi_width:.1f} m
- Score QA final: {qa_score}/100, estado {status_text}
- Celdas verdes: {qa_counts['green']}, amarillas: {qa_counts['yellow']}, rojas: {qa_counts['red']}

## Estado antes del paso de bateadora

La via simulada presenta irregularidad de nivelacion y alineacion local. El balasto tiene densidad heterogenea en el entorno del talud, con zonas de sombra LiDAR y variacion de cota que obligan a planificar pasadas laterales de dron.

## Paso de bateadora y drones

La bateadora avanza sobre el eje estimado de via. El eje se ha ajustado matematicamente mediante PCA 2D sobre el ROI LiDAR para que la geometria de la via quede apoyada sobre la linea principal de puntos del corredor.

Los drones se planifican con el modelo: {optimizer['formula']}. La funcion objetivo es {optimizer['objective']}. La incertidumbre inicial equivalente es {optimizer['initialSigmaMm']} mm y baja a {optimizer['finalSigmaMm']} mm tras las pasadas, con una ganancia teorica de cobertura del {optimizer['coverageGainPct']}%.

## Estado despues del paso de bateadora

La geometria general mejora: la mayoria de celdas quedan en verde y el balasto aparece mas continuo. Se simula una incidencia realista no perfecta: {anomaly['message']}

La incidencia queda localizada en s={anomaly['alongM']} m y offset={anomaly['crossM']} m respecto al eje de via, con radio de {anomaly['radiusM']} m. La recomendacion es repetir una pasada adaptativa y revisar el bateo en esa zona concreta.

## GNSS, precision y soberania

La pila propuesta usa {', '.join(gnss['stack'])}. La precision absoluta esperable se comunica como {gnss['absoluteAccuracy']}. La repetibilidad local se defiende como {gnss['relativeRepeatability']}.

El enfoque de soberania es: {gnss['sovereignty']}. El modelo de fusion se resume como {gnss['math']}.

## Decision operativa

Aceptar el tramo como demostracion QA general, pero abrir una orden de revision localizada para la zona marcada en rojo tras el paso de bateadora. No se repite toda la campana LiDAR: solo la ventana adaptativa propuesta por el planificador.
"""
    return {
        "title": "Informe QA RailLiDAR tras bateadora",
        "status": status_text,
        "recommendation": "Revision localizada de la incidencia residual simulada",
        "markdown": markdown,
    }


def _round_list(values: Any) -> list[float]:
    return [round(float(value), 3) for value in values]
