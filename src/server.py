from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from process_laz import AnalysisParams, DEFAULT_LAZ_NAME, analyze_laz, find_laz_files, write_analysis_json, write_report_files


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "web"
OUTPUT_ROOT = PROJECT_ROOT / "output"
ANALYSIS_CACHE: dict[tuple[str, int, float, float, float], dict] = {}


class RailLidarHandler(BaseHTTPRequestHandler):
    server_version = "RailLidarQAMVP/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)

        try:
            if route == "/api/health":
                self._send_json({"ok": True})
            elif route == "/api/files":
                self._send_json({"files": find_laz_files(PROJECT_ROOT), "default": DEFAULT_LAZ_NAME})
            elif route == "/api/analyze":
                self._handle_analyze(query)
            elif route == "/api/report":
                self._handle_report()
            else:
                self._serve_static(route)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format % args))

    def _handle_analyze(self, query: dict[str, list[str]]) -> None:
        filename = _safe_filename(_first(query, "file", DEFAULT_LAZ_NAME))
        max_points = _int_param(query, "sample", 70000, 5000, 200000)
        grid_size = _float_param(query, "grid", 4.0, 1.0, 25.0)
        roi_length = _float_param(query, "length", 80.0, 10.0, 250.0)
        roi_width = _float_param(query, "width", 40.0, 10.0, 160.0)

        laz_path = (PROJECT_ROOT / filename).resolve()
        if laz_path.parent != PROJECT_ROOT.resolve() or laz_path.suffix.lower() not in {".las", ".laz"}:
            self._send_json({"error": "Archivo no permitido"}, status=HTTPStatus.BAD_REQUEST)
            return

        cache_key = (filename, max_points, grid_size, roi_length, roi_width)
        if cache_key not in ANALYSIS_CACHE:
            result = analyze_laz(
                AnalysisParams(
                    laz_path=laz_path,
                    max_points=max_points,
                    grid_size=grid_size,
                    roi_length=roi_length,
                    roi_width=roi_width,
                )
            )
            ANALYSIS_CACHE[cache_key] = result
            write_analysis_json(result, OUTPUT_ROOT / "last_analysis.json")
            write_report_files(result, OUTPUT_ROOT)
        self._send_json(ANALYSIS_CACHE[cache_key])

    def _handle_report(self) -> None:
        report_path = OUTPUT_ROOT / "informe_qa.html"
        if not report_path.exists():
            self._send_json({"error": "Todavia no hay informe. Ejecuta primero Analizar LAZ."}, status=HTTPStatus.NOT_FOUND)
            return
        content = report_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_static(self, route: str) -> None:
        if route in {"", "/"}:
            static_path = WEB_ROOT / "index.html"
        elif route.startswith("/node_modules/three/"):
            static_path = PROJECT_ROOT / unquote(route.lstrip("/"))
        else:
            static_path = WEB_ROOT / unquote(route.lstrip("/"))

        resolved = static_path.resolve()
        allowed_roots = [WEB_ROOT.resolve(), (PROJECT_ROOT / "node_modules" / "three").resolve()]
        if not any(resolved == root or root in resolved.parents for root in allowed_roots):
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not resolved.exists() or not resolved.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        mime_type, _ = mimetypes.guess_type(str(resolved))
        content = resolved.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def _first(query: dict[str, list[str]], key: str, default: str) -> str:
    values = query.get(key)
    if not values:
        return default
    return values[0] or default


def _safe_filename(value: str) -> str:
    return Path(value).name


def _int_param(query: dict[str, list[str]], key: str, default: int, min_value: int, max_value: int) -> int:
    try:
        value = int(_first(query, key, str(default)))
    except ValueError:
        value = default
    return max(min_value, min(max_value, value))


def _float_param(query: dict[str, list[str]], key: str, default: float, min_value: float, max_value: float) -> float:
    try:
        value = float(_first(query, key, str(default)))
    except ValueError:
        value = default
    return max(min_value, min(max_value, value))


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor local del MVP RailLiDAR QA")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), RailLidarHandler)
    print(f"RailLiDAR QA MVP disponible en http://{args.host}:{args.port}")
    print("Pulsa Ctrl+C para detener el servidor.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
