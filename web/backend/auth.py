"""Phone-OTP login + JWT session cookies. OTP delivery via Twilio (urllib); dev bypass for local."""
import base64
import secrets
import time
import urllib.parse
import urllib.request

import jwt

import settings

_otps = {}   # phone -> (code, expiry_ts)


def normalize_phone(p: str) -> str:
    if not p:
        return ""
    p = p.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if p and p[0].isdigit():
        p = "+" + p
    return p


def _allowlist():
    return {normalize_phone(x) for x in ([settings.ADMIN_PHONE] + settings.ALLOWED_PHONES) if x}


def is_allowed(phone: str) -> bool:
    allow = _allowlist()
    return (not allow) or (normalize_phone(phone) in allow)


def request_otp(phone: str):
    phone = normalize_phone(phone)
    if not phone:
        return False, "phone required"
    if not is_allowed(phone):
        return False, "this number is not authorized"
    code = settings.DEV_CODE if settings.DEV_AUTH_BYPASS else f"{secrets.randbelow(1000000):06d}"
    _otps[phone] = (code, time.time() + settings.OTP_TTL)
    if not settings.DEV_AUTH_BYPASS:
        ok, err = _send_sms(phone, f"Your BigRedAlumni verification code is {code}")
        if not ok:
            return False, err
    return True, None


def verify_code(phone: str, code: str):
    phone = normalize_phone(phone)
    rec = _otps.get(phone)
    if not rec or rec[1] < time.time():
        return None
    if (code or "").strip() != rec[0]:
        return None
    _otps.pop(phone, None)
    return issue_token(phone)


def issue_token(phone: str) -> str:
    exp = int(time.time() + settings.JWT_TTL_HOURS * 3600)
    return jwt.encode({"sub": phone, "exp": exp}, settings.JWT_SECRET, algorithm="HS256")


def verify_token(token: str):
    if not token:
        return None
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"]).get("sub")
    except Exception:  # noqa: BLE001
        return None


def _send_sms(to: str, body: str):
    sid, tok, frm = settings.TWILIO_SID, settings.TWILIO_TOKEN, settings.TWILIO_FROM
    if not (sid and tok and frm):
        return False, "Twilio not configured"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urllib.parse.urlencode({"To": to, "From": frm, "Body": body}).encode()
    cred = base64.b64encode(f"{sid}:{tok}".encode()).decode()
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Basic {cred}",
        "Content-Type": "application/x-www-form-urlencoded"})
    try:
        urllib.request.urlopen(req, timeout=20)
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, f"SMS send failed: {e}"
