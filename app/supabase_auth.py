"""Các thao tác Supabase Auth qua REST API.

Service key chỉ được dùng phía server cho thao tác quản trị tạo tài khoản.
Đăng nhập và xác thực token dùng publishable/anon key nếu đã cấu hình.
"""
import os
from urllib.parse import urlencode

import requests


SUPABASE_URL = ""
SUPABASE_SERVICE_KEY = ""
SUPABASE_PUBLIC_KEY = ""
TIMEOUT = 20


class AuthError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def configure(url, service_key, public_key=""):
    global SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_PUBLIC_KEY
    SUPABASE_URL = (url or "").strip().rstrip("/")
    SUPABASE_SERVICE_KEY = (service_key or "").strip()
    SUPABASE_PUBLIC_KEY = (
        (public_key or "").strip()
        or os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
        or os.environ.get("SUPABASE_ANON_KEY", "").strip()
        or SUPABASE_SERVICE_KEY
    )


def configured():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def _require():
    if not configured():
        raise AuthError("Chưa cấu hình Supabase Auth.", 503)


def _auth_url(path):
    return f"{SUPABASE_URL}/auth/v1/{path.lstrip('/')}"


def _headers(key, access_token=None):
    headers = {"apikey": key, "Content-Type": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def _request(method, path, *, key, access_token=None, **kwargs):
    _require()
    try:
        response = requests.request(
            method,
            _auth_url(path),
            headers=_headers(key, access_token),
            timeout=TIMEOUT,
            **kwargs,
        )
    except requests.RequestException as exc:
        raise AuthError("Không kết nối được Supabase Auth.", 503) from exc

    if response.status_code >= 400:
        try:
            data = response.json()
        except ValueError:
            data = {}
        message = (
            data.get("msg")
            or data.get("message")
            or data.get("error_description")
            or data.get("error")
            or "Supabase Auth từ chối yêu cầu."
        )
        raise AuthError(str(message), response.status_code)
    try:
        return response.json()
    except ValueError:
        return {}


def admin_create_user(email, password, name, role):
    return _request(
        "POST",
        "/admin/users",
        key=SUPABASE_SERVICE_KEY,
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"name": name, "role": role},
        },
    )


def admin_delete_user(user_id):
    if not user_id:
        return
    try:
        _request("DELETE", f"/admin/users/{user_id}", key=SUPABASE_SERVICE_KEY)
    except AuthError:
        # Không che lỗi tạo tài khoản ban đầu bằng lỗi dọn dẹp tài khoản mồ côi.
        pass


def password_login(email, password):
    return _request(
        "POST",
        "/token",
        key=SUPABASE_PUBLIC_KEY,
        params={"grant_type": "password"},
        json={"email": email, "password": password},
    )


def get_user(access_token):
    if not access_token:
        raise AuthError("Thiếu access token.", 401)
    return _request(
        "GET",
        "/user",
        key=SUPABASE_PUBLIC_KEY,
        access_token=access_token,
    )


def google_url(redirect_to):
    _require()
    params = urlencode({"provider": "google", "redirect_to": redirect_to})
    return f"{_auth_url('/authorize')}?{params}"
