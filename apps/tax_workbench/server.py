from __future__ import annotations

import argparse
import json
import re
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from .markdown import save_session
from .models import (
    AMOUNT_PERIODS,
    INVOICE_NEEDS,
    REGIONS,
    TAXPAYER_TYPES,
    TRANSACTION_TYPES,
    VAT_STATUSES,
    TaxFacts,
)
from .planner import TaxPlanningService

MAX_BODY = 1_000_000
CASE_RE = re.compile(
    r"^/api/cases/([A-Za-z0-9][A-Za-z0-9_-]{0,63})(?:/(analyze|review|audit))?$"
)
FACT_RE = re.compile(
    r"^/api/cases/([A-Za-z0-9][A-Za-z0-9_-]{0,63})/facts/(.+)$"
)


def schema_payload() -> dict[str, Any]:
    return {
        "regions": sorted(REGIONS),
        "taxpayer_types": sorted(TAXPAYER_TYPES),
        "vat_statuses": sorted(VAT_STATUSES),
        "transaction_types": sorted(TRANSACTION_TYPES),
        "amount_periods": sorted(AMOUNT_PERIODS),
        "invoice_needs": sorted(INVOICE_NEEDS),
        "objectives": [
            "合规降负",
            "现金流优化",
            "发票与报价",
            "主体身份评估",
            "海南政策预审",
        ],
        "decision_core": "V7",
    }


def make_handler(vault: Path):
    service = TaxPlanningService(vault)
    static_file = Path(__file__).resolve().parent / "static" / "index.html"

    class Handler(BaseHTTPRequestHandler):
        server_version = "TaxKBWorkbench/0.2"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _html(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, Any]:
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise ValueError("无效 Content-Length") from exc
            if length <= 0 or length > MAX_BODY:
                raise ValueError("请求体为空或超过1MB限制")
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("请求体必须是有效 UTF-8 JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError("JSON 顶层必须是对象")
            return payload

        @staticmethod
        def _facts(payload: dict[str, Any]) -> TaxFacts:
            data = payload.get("facts") if isinstance(payload.get("facts"), dict) else payload
            return TaxFacts.from_dict(data)

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/health":
                self._json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "service": "tax-planning-workbench",
                        "decision_core": "v7",
                    },
                )
                return
            if path == "/api/schema":
                self._json(HTTPStatus.OK, schema_payload())
                return

            match = CASE_RE.fullmatch(path)
            if match:
                case_id, action = match.groups()
                try:
                    payload = (
                        {"events": service.audit_case(case_id)}
                        if action == "audit"
                        else service.get_case(case_id)
                    )
                except FileNotFoundError:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "case_not_found"})
                    return
                self._json(HTTPStatus.OK, payload)
                return

            if path in {"/", "/index.html"}:
                if not static_file.exists():
                    self._json(
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                        {"error": "前端页面不存在"},
                    )
                    return
                self._html(HTTPStatus.OK, static_file.read_bytes())
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            try:
                payload = self._read_json()
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            try:
                if path in {"/api/analyze", "/api/save"}:
                    facts = self._facts(payload)
                    errors = facts.validate()
                    if errors:
                        self._json(
                            HTTPStatus.UNPROCESSABLE_ENTITY,
                            {"error": "validation_failed", "errors": errors},
                        )
                        return
                    result = (
                        service.create_case(facts)
                        if path == "/api/save"
                        else service.analyze(facts)
                    )
                    response = result.to_dict()
                    response["facts"] = facts.to_dict()
                    if path == "/api/save":
                        saved = save_session(vault, facts, result)
                        response["saved_path"] = saved.relative_to(vault).as_posix()
                    self._json(HTTPStatus.OK, response)
                    return

                if path == "/api/cases":
                    facts = self._facts(payload)
                    errors = facts.validate()
                    if errors:
                        self._json(
                            HTTPStatus.UNPROCESSABLE_ENTITY,
                            {"error": "validation_failed", "errors": errors},
                        )
                        return
                    result = service.create_case(facts)
                    response = result.to_dict()
                    response["facts"] = facts.to_dict()
                    self._json(HTTPStatus.CREATED, response)
                    return

                match = CASE_RE.fullmatch(path)
                if match:
                    case_id, action = match.groups()
                    if action == "analyze":
                        self._json(
                            HTTPStatus.OK,
                            service.analyze_case(case_id).to_dict(),
                        )
                        return
                    if action == "review":
                        self._json(
                            HTTPStatus.OK,
                            service.review_case(
                                case_id,
                                bool(payload.get("approved")),
                                str(payload.get("actor") or "reviewer"),
                                str(payload.get("note") or ""),
                            ),
                        )
                        return
            except FileNotFoundError:
                self._json(HTTPStatus.NOT_FOUND, {"error": "case_not_found"})
                return
            except (ValueError, RuntimeError) as exc:
                self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
                return

            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_PATCH(self) -> None:
            path = self.path.split("?", 1)[0]
            match = FACT_RE.fullmatch(path)
            if not match:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            try:
                payload = self._read_json()
                case_id, fact_id = match.groups()
                result = service.revise_case_fact(
                    case_id,
                    unquote(fact_id),
                    payload.get("value"),
                    str(payload.get("actor") or "user"),
                )
            except FileNotFoundError:
                self._json(HTTPStatus.NOT_FOUND, {"error": "case_not_found"})
                return
            except (ValueError, RuntimeError) as exc:
                self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
                return
            self._json(HTTPStatus.OK, result)

    return Handler


def create_server(
    vault: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(Path(vault).resolve()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local TaxKB planning workbench.")
    parser.add_argument("--vault", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", dest="open_browser")
    args = parser.parse_args()
    server = create_server(Path(args.vault), args.host, args.port)
    url = f"http://{args.host}:{server.server_port}/"
    print(f"TaxKB planning workbench: {url}")
    print("Press Ctrl+C to stop. The server only listens locally by default.")
    if args.open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
