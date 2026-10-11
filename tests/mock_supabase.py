"""Mock Supabase PostgREST (in-memory) để test mà không cần project thật.

Chạy: python3 tests/mock_supabase.py [port]   (mặc định 54321)
  GET    /rest/v1/{table}?select=*&<filters>&order=&limit=
  POST   /rest/v1/{table}            (Prefer: return=representation)
  PATCH  /rest/v1/{table}?<filters>
  DELETE /rest/v1/{table}?<filters>

Hỗ trợ các toán tử mà supabase_store.py dùng: eq, neq, in, is.null.
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote, urlparse

TABLES = {}
LOCK = threading.Lock()
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 54321

RESERVED = {"select", "order", "limit", "offset", "on_conflict", "columns"}


def _coerce(text):
    if text == "null":
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    return text


def _strip(value):
    value = unquote(value)
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _parse_filters(params):
    filters = []
    for key, raw in params:
        if key in RESERVED:
            continue
        if raw.startswith("in.(") and raw.endswith(")"):
            inner = raw[4:-1]
            values = [_strip(v) for v in inner.split(",") if v != ""]
            filters.append((key, "in", values))
        elif raw.startswith("is."):
            filters.append((key, "is", _coerce(raw[3:])))
        elif "." in raw:
            op, _, value = raw.partition(".")
            filters.append((key, op, _coerce(_strip(value))))
        else:
            filters.append((key, "eq", _coerce(_strip(raw))))
    return filters


def _match(row, filters):
    for col, op, value in filters:
        actual = row.get(col)
        if op == "eq":
            if isinstance(actual, bool) or isinstance(value, bool):
                if bool(actual) != (value is True or str(value).lower() == "true"):
                    return False
            elif value is None:
                if actual is not None:
                    return False
            elif str(actual) != str(value):
                return False
        elif op == "neq":
            if str(actual) == str(value):
                return False
        elif op == "in":
            if str(actual) not in [str(v) for v in value]:
                return False
        elif op == "is":
            if value is None and actual is not None:
                return False
        else:
            return False
    return True


def _apply_order(rows, order):
    if not order:
        return rows
    result = list(rows)
    for clause in order.split(","):
        clause = clause.strip()
        if not clause:
            continue
        col, _, direction = clause.partition(".")
        result.sort(key=lambda r: (r.get(col) is None, str(r.get(col))),
                    reverse=(direction == "desc"))
    return result


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _table_and_params(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if not path.startswith("/rest/v1/"):
            return None, None, None
        table = path[len("/rest/v1/"):].strip("/")
        params = parse_qsl(parsed.query, keep_blank_values=True)
        return table, params, parsed.query

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except ValueError:
            return None

    def _wants_representation(self):
        return "return=representation" in self.headers.get("Prefer", "")

    def do_GET(self):
        table, params, _ = self._table_and_params()
        if table is None:
            return self._send({"tables": {name: len(rows) for name, rows in TABLES.items()}})
        if not table:
            return self._send({"tables": {name: len(rows) for name, rows in TABLES.items()}})
        filters = _parse_filters(params)
        order = next((v for k, v in params if k == "order"), None)
        limit = next((v for k, v in params if k == "limit"), None)
        with LOCK:
            rows = [dict(r) for r in TABLES.get(table, []) if _match(r, filters)]
        rows = _apply_order(rows, order)
        if limit:
            rows = rows[: int(limit)]
        self._send(rows)

    def do_POST(self):
        table, params, _ = self._table_and_params()
        if table is None:
            return self._send({"error": "bad table"}, 404)
        payload = self._body()
        rows = payload if isinstance(payload, list) else [payload]
        rows = [r for r in rows if isinstance(r, dict)]
        stored = []
        with LOCK:
            table_rows = TABLES.setdefault(table, [])
            for row in rows:
                table_rows.append(dict(row))
                stored.append(dict(row))
        if self._wants_representation():
            return self._send(stored, 201)
        self._send(None, 201)

    def do_PATCH(self):
        table, params, _ = self._table_and_params()
        if table is None:
            return self._send({"error": "bad table"}, 404)
        payload = self._body() or {}
        filters = _parse_filters(params)
        updated = []
        with LOCK:
            for row in TABLES.get(table, []):
                if _match(row, filters):
                    row.update(payload)
                    updated.append(dict(row))
        if self._wants_representation():
            return self._send(updated)
        self._send(None, 204)

    def do_DELETE(self):
        table, params, _ = self._table_and_params()
        if table is None:
            return self._send({"error": "bad table"}, 404)
        filters = _parse_filters(params)
        removed = []
        with LOCK:
            rows = TABLES.setdefault(table, [])
            kept = []
            for row in rows:
                if _match(row, filters):
                    removed.append(dict(row))
                else:
                    kept.append(row)
            TABLES[table] = kept
        if self._wants_representation():
            return self._send(removed)
        self._send(None, 204)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"mock Supabase on 127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
