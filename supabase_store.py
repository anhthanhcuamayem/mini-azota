"""Client Supabase (PostgREST) tối giản cho ứng dụng.

Toàn bộ dữ liệu (tài khoản, lớp, bộ đề, đề thi, bài nộp, phiên thi) được lưu
trong Postgres của Supabase và truy cập qua REST API của PostgREST. Ứng dụng
chạy phía server nên dùng service-role key để bỏ qua Row Level Security.

Biến môi trường:
  SUPABASE_URL               - ví dụ https://xxxx.supabase.co
  SUPABASE_SERVICE_ROLE_KEY  - service role key (ưu tiên)
  SUPABASE_KEY               - dự phòng nếu chỉ có 1 key

Bảng tương ứng được tạo bằng supabase_schema.sql.
"""
import os

import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    or os.environ.get("SUPABASE_KEY", "").strip()
)

TIMEOUT = 30
VALID_OPS = {"eq", "neq", "gt", "gte", "lt", "lte", "like", "ilike", "in", "is"}


class SupabaseError(Exception):
    """Lỗi khi làm việc với Supabase."""


def configure(url, key):
    """Cho phép nạp cấu hình động (dùng trong test)."""
    global SUPABASE_URL, SUPABASE_KEY
    SUPABASE_URL = (url or "").strip().rstrip("/")
    SUPABASE_KEY = (key or "").strip()


def configured():
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _require():
    if not configured():
        raise SupabaseError(
            "Chưa cấu hình Supabase: điền SUPABASE_URL và SUPABASE_SERVICE_ROLE_KEY "
            "vào file .env rồi khởi động lại server."
        )


def _rest_url(table):
    return f"{SUPABASE_URL}/rest/v1/{table}"


def _headers(prefer=None):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _normalize_filters(filters):
    """Chuẩn hóa filters về list[(cột, toán_tử, giá_trị)]."""
    out = []
    for item in filters or []:
        if len(item) == 2:
            col, value = item
            op = "eq"
        else:
            col, op, value = item
        if op not in VALID_OPS:
            raise SupabaseError(f"Toán tử lọc không hỗ trợ: {op}")
        out.append((col, op, value))
    return out


def _filter_params(filters):
    params = {}
    for col, op, value in _normalize_filters(filters):
        if op == "in":
            values = value if isinstance(value, (list, tuple, set)) else [value]
            joined = ",".join(f'"{v}"' if _needs_quote(v) else str(v) for v in values)
            params[col] = f"in.({joined})"
        elif op == "is" or (op == "eq" and value is None):
            params[col] = "is.null"
        elif op == "neq":
            params[col] = "neq." + (str(value) if value is not None else "null")
        else:
            params[col] = f"{op}.{_escape(value)}"
    return params


def _needs_quote(value):
    text = str(value)
    return any(ch in text for ch in ',()"')


def _escape(value):
    # requests sẽ tự percent-encode khi gửi params; ở đây chỉ cần thêm dấu "
    # cho các giá trị chứa ký tự đặc biệt của PostgREST và hạ chữ boolean.
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if _needs_quote(text):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def _raise_for_status(resp):
    if resp.status_code >= 400:
        detail = resp.text[:500]
        raise SupabaseError(f"Supabase trả về HTTP {resp.status_code}: {detail}")


def select(table, filters=None, columns="*", order=None, limit=None):
    """Đọc danh sách hàng. Trả về list[dict]."""
    _require()
    params = {"select": columns}
    params.update(_filter_params(filters))
    if order:
        params["order"] = order
    if limit:
        params["limit"] = str(limit)
    resp = requests.get(_rest_url(table), headers=_headers(), params=params, timeout=TIMEOUT)
    _raise_for_status(resp)
    data = resp.json()
    return data if isinstance(data, list) else []


def select_one(table, filters=None, columns="*", order=None):
    rows = select(table, filters=filters, columns=columns, order=order, limit=1)
    return rows[0] if rows else None


def insert(table, rows, upsert=False, on_conflict=None):
    """Chèn (hoặc upsert) và trả về các hàng vừa ghi."""
    _require()
    payload = rows if isinstance(rows, list) else [rows]
    prefer = "return=representation"
    if upsert:
        prefer += ",resolution=merge-duplicates"
    params = {"on_conflict": on_conflict} if (upsert and on_conflict) else None
    resp = requests.post(_rest_url(table), headers=_headers(prefer), params=params,
                         json=payload, timeout=TIMEOUT)
    _raise_for_status(resp)
    return resp.json()


def update(table, values, filters):
    """Cập nhật theo filters, trả về các hàng đã đổi."""
    _require()
    resp = requests.patch(_rest_url(table), headers=_headers("return=representation"),
                          params=_filter_params(filters), json=values, timeout=TIMEOUT)
    _raise_for_status(resp)
    return resp.json()


def delete(table, filters):
    _require()
    resp = requests.delete(_rest_url(table), headers=_headers("return=representation"),
                           params=_filter_params(filters), timeout=TIMEOUT)
    _raise_for_status(resp)
    return resp.json()


def count(table, filters=None):
    _require()
    params = {"select": "*"}
    params.update(_filter_params(filters))
    headers = _headers("count=exact")
    headers["Range"] = "0-0"
    resp = requests.get(_rest_url(table), headers=headers, params=params, timeout=TIMEOUT)
    _raise_for_status(resp)
    content_range = resp.headers.get("Content-Range", "")
    if "/" in content_range:
        try:
            return int(content_range.split("/")[-1])
        except ValueError:
            return len(resp.json())
    return len(resp.json())
