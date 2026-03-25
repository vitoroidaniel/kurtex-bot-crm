"""
Kurtex CRM — Flask backend
Connects to the same MongoDB used by the Telegram bot.

Required env vars (same as bot):
    MONGODB_URI      — MongoDB connection string
    MONGODB_DB       — Database name (default: kurtex)
    SECRET_KEY       — Flask session secret (generate a random string)
    TELEGRAM_BOT_TOKEN — For login widget verification

Run:
    pip install flask pymongo python-dotenv
    python app.py
"""
import random
import time
from flask import request, jsonify, session, url_for

import os
import hashlib
import hmac
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, session,
    redirect, url_for, jsonify, g, Response
)
import io
from pymongo import MongoClient, DESCENDING
from bson import ObjectId
import bcrypt
import secrets
import time
import pandas as pd
from dateutil import parser as date_parser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "")

# ── MongoDB ───────────────────────────────────────────────────────────────────

_client = None
_db     = None

def get_db():
    global _client, _db
    if _db is not None:
        return _db
    uri     = os.getenv("MONGODB_URI", "")
    db_name = os.getenv("MONGODB_DB", "")
    _client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    _db     = _client[db_name]
    return _db

def cases_col():
    return get_db()["cases"]

def users_col():
    return get_db()["users"]

def strip(doc):
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc

# ── Roles ─────────────────────────────────────────────────────────────────────

CAN_VIEW_REPORTS = {"developer", "super_admin", "manager", "team_leader"}
CAN_MANAGE_USERS = {"developer", "super_admin", "manager", "team_leader"}

ROLE_LABELS = {
    "developer":   "Developer",
    "manager":     "Manager",
    "team_leader": "Team Leader",
    "agent":       "Agent",
    "super_admin": "Developer",
}

ROLE_COLORS = {
    "developer":   "#6366f1",
    "super_admin": "#6366f1",
    "manager":     "#f59e0b",
    "team_leader": "#10b981",
    "agent":       "#64748b",
}

def serialize_user(user: dict) -> dict:
    """Convert bytes/ObjectId fields to JSON-safe format"""
    new_user = {}
    for k, v in user.items():
        if isinstance(v, bytes):
            new_user[k] = v.decode("utf-8")  # or base64.b64encode(v).decode("utf-8")
        elif isinstance(v, ObjectId):
            new_user[k] = str(v)
        else:
            new_user[k] = v
    return new_user

def hash_password(password):
    """Hash a password for storage."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt)

def verify_password(password, hashed):
    """Verify a password against its hash."""
    if not hashed or not isinstance(hashed, bytes):
        return False
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

# ── Telegram Login Widget Verification ───────────────────────────────────────

def verify_telegram_login(data: dict) -> bool:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        # Dev mode: skip verification
        return True
    check_hash = data.pop("hash", "")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed   = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    # Auth date must be within 24h
    auth_date = int(data.get("auth_date", 0))
    age = datetime.now(timezone.utc).timestamp() - auth_date
    if age > 86400:
        return False
    return hmac.compare_digest(computed, check_hash)

# ── Auth helpers ──────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def get_current_user():
    if "user_id" not in session:
        return None
    uid  = session["user_id"]
    user = strip(users_col().find_one({"telegram_id": uid}))
    return user

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated(*args, **kwargs):
            user = get_current_user()
            if not user or user.get("role") not in roles:
                return jsonify({"error": "Access denied"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

# ── Routes: Auth ──────────────────────────────────────────────────────────────

# 1️⃣ Telegram login
@app.route("/auth/telegram", methods=["POST"])
def auth_telegram():
    data = request.json or {}
    tg_data = dict(data)

    if not verify_telegram_login(tg_data):
        return jsonify({"error": "Invalid Telegram login"}), 401

    telegram_id = int(data.get("id", 0))
    user = strip(users_col().find_one({"telegram_id": telegram_id}))
    if not user:
        return jsonify({"error": "You are not registered"}), 403

    # Generate OTP
    otp_code = str(random.randint(100000, 999999))
    telegram_otp_store[telegram_id] = {"code": otp_code, "expires": time.time() + 300}
    send_telegram_otp(telegram_id, otp_code)

    return jsonify({"ok": True, "message": "OTP sent via Telegram"})


# 2️⃣ Verify OTP
@app.route("/verify-code", methods=["POST"])
def verify_code():
    data = request.json or {}
    telegram_id = int(data.get("telegram_id", 0))
    code = str(data.get("code", ""))

    otp_entry = telegram_otp_store.get(telegram_id)
    if not otp_entry:
        return jsonify({"error": "No OTP request found"}), 400

    if time.time() > otp_entry["expires"]:
        telegram_otp_store.pop(telegram_id, None)
        return jsonify({"error": "OTP expired"}), 400

    if otp_entry["code"] != code:
        return jsonify({"error": "Invalid code"}), 400

    user = strip(users_col().find_one({"telegram_id": telegram_id}))
    if not user:
        return jsonify({"error": "User not found"}), 403

    session["user_id"]   = telegram_id
    session["user_name"] = user.get("name", "User")
    session["user_role"] = user.get("role", "agent")

    telegram_otp_store.pop(telegram_id, None)
    return jsonify({"ok": True, "redirect": url_for("dashboard")})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ── Dev login (only when no bot token set) ────────────────────────────────────

@app.route("/register", methods=["GET"])
def register_page():
    return render_template("register.html")

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.json or {}
    username = data.get("telegram_username", "").strip().lstrip("@")
    password = data.get("password", "")
    
    if not username or not password or len(password) < 6:
        return jsonify({"error": "Invalid username or password (min 6 chars)"}), 400
    
    user = users_col().find_one({"username": username})
    if not user:
        return jsonify({"error": "User not found. Add via Telegram bot first."}), 404
    
    if user.get("pw_hash"):
        return jsonify({"error": "Password already set."}), 400
    
    pw_hash = hash_password(password)
    users_col().update_one(
        {"username": username},
        {"$set": {"pw_hash": pw_hash}}
    )
    
    return jsonify({"ok": True, "message": "Password set successfully"})

@app.route("/api/check-user", methods=["POST"])
def api_check_user():
    data = request.json or {}
    username = data.get("telegram_username", "").strip().lstrip("@")
    user = users_col().find_one({"username": username})
    if not user:
        return jsonify({"exists": False})
    return jsonify({"exists": True, "has_pw": bool(user.get("pw_hash"))})

@app.route("/login-password", methods=["POST"])
def login_password():
    data = request.json or {}
    username = data.get("telegram_username", "").strip().lstrip("@")
    password = data.get("password", "")
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    
    user = strip(users_col().find_one({"username": username}))
    if not user or not verify_password(password, user.get("pw_hash")):
        return jsonify({"error": "Invalid credentials"}), 401
    
    session["user_id"]   = user["telegram_id"]
    session["user_name"] = user.get("name", "User")
    session["user_role"] = user.get("role", "agent")
    
    return jsonify({"ok": True, "redirect": url_for("dashboard")})

@app.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.json or {}
    username = data.get("telegram_username", "").strip().lstrip("@")
    if not username:
        return jsonify({"error": "Username required"}), 400
    
    user = users_col().find_one({"username": username})
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # Generate secure token
    plain_token = secrets.token_hex(24)
    token_hash = hash_password(plain_token)  # Reuse bcrypt
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    
    users_col().update_one(
        {"username": username},
        {"$set": {
            "reset_token": token_hash,
            "reset_expires": expires.isoformat()
        }}
    )
    
    return jsonify({"ok": True, "token": plain_token})

@app.route("/verify-reset", methods=["POST"])
def verify_reset():
    data = request.json or {}
    username = data.get("telegram_username", "").strip().lstrip("@")
    token = data.get("token", "")
    password = data.get("password", "")
    
    if not all([username, token, password]):
        return jsonify({"error": "Username, token, and password required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    
    user_doc = users_col().find_one({"username": username})
    if not user_doc:
        return jsonify({"error": "User not found"}), 404
    
    # Check expiry
    expires_str = user_doc.get("reset_expires")
    if expires_str:
        expires = datetime.fromisoformat(expires_str.replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expires:
            return jsonify({"error": "Reset token expired"}), 400
    
    # Verify token hash
    stored_hash = user_doc.get("reset_token")
    if not verify_password(token, stored_hash):
        return jsonify({"error": "Invalid token"}), 401
    
    # Set new password and clear reset fields
    new_hash = hash_password(password)
    users_col().update_one(
        {"username": username},
        {"$set": {"pw_hash": new_hash},
         "$unset": {"reset_token": "", "reset_expires": ""}}
    )
    
    return jsonify({"ok": True, "message": "Password reset successfully"})

# ── Routes: Pages ─────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    user = get_current_user()
    return render_template("dashboard.html", user=user,
                           role_labels=ROLE_LABELS, role_colors=ROLE_COLORS)

@app.route("/api/analytics")
@role_required(*CAN_VIEW_REPORTS)
def api_analytics():
    user = get_current_user()
    role = user.get("role", "agent")
    
    # Time periods
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    week_start = (now - timedelta(days=now.weekday())).date().isoformat()
    month_start = (now - timedelta(days=30)).date().isoformat()
    
    pipeline = [
        {"$match": {"opened_at": {"$gte": month_start}}},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "by_status": {"$push": "$status"},
            "by_agent": {"$push": "$agent_name"},
            "by_group": {"$push": "$group_name"},
            "resolution_times": {"$push": "$resolution_secs"}
        }}
    ]
    agg = list(cases_col().aggregate(pipeline))
    data = agg[0] if agg else {"total": 0, "by_status": [], "by_agent": [], "by_group": [], "resolution_times": []}
    
    # Charts data
    status_counts = defaultdict(int)
    agent_cases = defaultdict(int)
    group_cases = defaultdict(int)
    valid_res_times = [t for t in data["resolution_times"] if t]
    
    for s in data["by_status"]:
        status_counts[s or "open"] += 1
    for a in data["by_agent"]:
        if a: agent_cases[a] += 1
    for g in data["by_group"]:
        if g: group_cases[g] += 1
    
    avg_resolution = sum(valid_res_times) / len(valid_res_times) if valid_res_times else 0
    
    # Pic count (simple URL parse in notes)
    pic_cases = 0
    for case in cases_col().find({"notes": {"$regex": r"(https?://.*\.(jpg|png|gif|webp))", "$options": "i"}}, {"notes": 1}):
        pic_cases += 1
    
    return jsonify({
        "summary": {
            "total_30d": data["total"],
            "avg_resolution_min": round(avg_resolution / 60, 1) if avg_resolution else 0,
            "cases_with_pics": pic_cases
        },
        "charts": {
            "status_pie": dict(sorted(status_counts.items(), key=lambda x: -x[1])[:6]),
            "agent_bar": dict(sorted(agent_cases.items(), key=lambda x: -x[1])[:10]),
            "group_bar": dict(sorted(group_cases.items(), key=lambda x: -x[1])[:6])
        },
        "timeseries": {}  # Line chart data (extend if needed)
    })

@app.route("/api/export")
@login_required
def api_export():
    format = request.args.get("format", "csv").lower()
    if format not in ["csv", "excel"]:
        return jsonify({"error": "Format must be csv or excel"}), 400
    
    # Reuse cases query logic
    user = get_current_user()
    role = user.get("role", "agent")
    query = {}
    if role == "agent":
        query["agent_id"] = user["telegram_id"]
    
    status = request.args.get("status")
    if status and status != "all":
        query["status"] = status
    search = request.args.get("q", "").strip()
    if search:
        query["$or"] = [
            {"driver_name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"group_name": {"$regex": search, "$options": "i"}},
            {"agent_name": {"$regex": search, "$options": "i"}},
            {"id": {"$regex": search, "$options": "i"}},
        ]
    date_from = request.args.get("date_from")
    if date_from:
        query.setdefault("opened_at", {})["$gte"] = date_from
    date_to = request.args.get("date_to")
    if date_to:
        query.setdefault("opened_at", {})["$lte"] = date_to + "T23:59:59"
    
    cases = list(cases_col().find(query, {"_id": 0}).sort("opened_at", DESCENDING))
    if not cases:
        return jsonify({"error": "No cases found for export"}), 404
    
    df = pd.DataFrame(cases)
    
    if format == "csv":
        csv_data = df.to_csv(index=False).encode('utf-8')
        return Response(csv_data, mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=kurtex-cases-{datetime.now().strftime('%Y%m%d')}.csv"})
    else:  # excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Cases')
        output.seek(0)
        return Response(output.read(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=kurtex-cases-{datetime.now().strftime('%Y%m%d')}.xlsx"})

# ── API: Stats ────────────────────────────────────────────────────────────────

from flask import Response
import io

@app.route("/api/stats")
@login_required
def api_stats():
    today = datetime.now(timezone.utc).date().isoformat()
    week_start = (datetime.now(timezone.utc) - timedelta(days=datetime.now(timezone.utc).weekday())).date().isoformat()

    all_cases   = list(cases_col().find({}, {"_id": 0}))
    today_cases = [c for c in all_cases if (c.get("opened_at") or "") >= today]
    week_cases  = [c for c in all_cases if (c.get("opened_at") or "") >= week_start]

    def status_counts(cases):
        counts = defaultdict(int)
        for c in cases:
            counts[c.get("status", "open")] += 1
        return dict(counts)

    # Leaderboard (this week)
    agent_stats = defaultdict(lambda: {"cases": 0, "resolved": 0, "avg_secs": []})
    for c in week_cases:
        if c.get("agent_name"):
            agent_stats[c["agent_name"]]["cases"] += 1
            if c.get("status") == "done":
                agent_stats[c["agent_name"]]["resolved"] += 1
                if c.get("resolution_secs"):
                    agent_stats[c["agent_name"]]["avg_secs"].append(c["resolution_secs"])

    leaderboard = []
    for name, s in sorted(agent_stats.items(), key=lambda x: -x[1]["cases"]):
        avg = int(sum(s["avg_secs"]) / len(s["avg_secs"])) if s["avg_secs"] else None
        leaderboard.append({"name": name, "cases": s["cases"],
                            "resolved": s["resolved"], "avg_secs": avg})

    return jsonify({
        "today": {"total": len(today_cases), **status_counts(today_cases)},
        "week":  {"total": len(week_cases),  **status_counts(week_cases)},
        "all":   {"total": len(all_cases),   **status_counts(all_cases)},
        "leaderboard": leaderboard[:10],
    })

# ── API: Cases ────────────────────────────────────────────────────────────────

@app.route("/api/cases")
@login_required
def api_cases():
    user   = get_current_user()
    role   = user.get("role", "agent")
    query  = {}

    # Agents only see their own cases
    if role == "agent":
        query["agent_id"] = user["telegram_id"]

    # Filters
    status = request.args.get("status")
    if status and status != "all":
        query["status"] = status

    search = request.args.get("q", "").strip()
    if search:
        query["$or"] = [
            {"driver_name":    {"$regex": search, "$options": "i"}},
            {"description":    {"$regex": search, "$options": "i"}},
            {"group_name":     {"$regex": search, "$options": "i"}},
            {"agent_name":     {"$regex": search, "$options": "i"}},
            {"id":             {"$regex": search, "$options": "i"}},
        ]

    date_from = request.args.get("date_from")
    date_to   = request.args.get("date_to")
    if date_from:
        query.setdefault("opened_at", {})["$gte"] = date_from
    if date_to:
        query.setdefault("opened_at", {})["$lte"] = date_to + "T23:59:59"

    agent_filter = request.args.get("agent_id")
    if agent_filter and role != "agent":
        query["agent_id"] = int(agent_filter)

    page     = max(1, int(request.args.get("page", 1)))
    per_page = int(request.args.get("per_page", 25))
    skip     = (page - 1) * per_page

    total  = cases_col().count_documents(query)
    cursor = cases_col().find(query, {"_id": 0}).sort("opened_at", DESCENDING).skip(skip).limit(per_page)
    cases  = list(cursor)

    return jsonify({"cases": cases, "total": total, "page": page, "per_page": per_page})

@app.route("/api/cases/<case_id>")
@login_required
def api_case_detail(case_id):
    case = strip(cases_col().find_one({"id": case_id}))
    if not case:
        return jsonify({"error": "Not found"}), 404
    return jsonify(case)

# ── API: Users ────────────────────────────────────────────────────────────────

@app.route("/api/users")
@login_required
def api_users():
    user = get_current_user()
    role = user.get("role", "agent")

    users = [strip(u) for u in users_col().find({}, {"_id": 0}).sort("name", 1)]

    # Enrich with case stats
    all_cases = list(cases_col().find({}, {"_id": 0, "agent_id": 1, "status": 1}))
    stats = defaultdict(lambda: {"total": 0, "done": 0})
    for c in all_cases:
        if c.get("agent_id"):
            stats[c["agent_id"]]["total"] += 1
            if c.get("status") == "done":
                stats[c["agent_id"]]["done"] += 1

    for u in users:
        s = stats.get(u.get("telegram_id"), {"total": 0, "done": 0})
        u["case_count"] = s["total"]
        u["resolved"]   = s["done"]

    return jsonify({"users": users, "role_labels": ROLE_LABELS, "role_colors": ROLE_COLORS})

@app.route("/api/me", methods=["GET"])
def api_me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    user = users_col().find_one({"telegram_id": user_id}) or {}
    safe_user = serialize_user(user)

    return jsonify({
        "name": session.get("user_name", "User"),
        "role": session.get("user_role", safe_user.get("role", "agent")),
        **safe_user
    })

@app.route("/api/cases/<case_id>", methods=["PATCH"])
@login_required
def api_update_case(case_id):
    return jsonify({"error": "Case updates disabled - view-only mode"}), 403

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = not os.getenv("TELEGRAM_BOT_TOKEN")
    app.run(host="0.0.0.0", port=port, debug=debug)

# railway fix
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
