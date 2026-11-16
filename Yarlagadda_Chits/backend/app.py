import os
from datetime import datetime, timedelta, timezone, date
from functools import wraps

from bson import ObjectId
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, get_jwt_identity, jwt_required
)
from pymongo import MongoClient, DESCENDING
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()
app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev-only-change-this-secret")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=2)
CORS(app, resources={r"/api/*": {"origins": "*"}})
jwt = JWTManager(app)

@jwt.invalid_token_loader
def invalid_token(reason):
    return jsonify({"message": "Your login session is invalid. Please sign in again."}), 401

@jwt.expired_token_loader
def expired_token(jwt_header, jwt_payload):
    return jsonify({"message": "Your login session has expired. Please sign in again."}), 401

@jwt.unauthorized_loader
def missing_token(reason):
    return jsonify({"message": "Please sign in to continue."}), 401

client = MongoClient(os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/"), serverSelectionTimeoutMS=10000, connectTimeoutMS=10000)
db = client[os.getenv("MONGO_DB_NAME", "yarlagadda_chits_test")]
users = db["users"]
chits = db["chits"]
payments = db["payments"]

SCHEDULE_DATA = {
    "100000-10": {
        "premiums": [7710, 7990, 8270, 8550, 8810, 9070, 9315, 9560, 9780, 10000],
        "payable": [72100, 74900, 77700, 80500, 83100, 85700, 88150, 90600, 92800, 95000],
        "dividend": [2290, 2010, 1730, 1450, 1190, 930, 685, 440, 220, 0],
    },
    "200000-16": {
        "premiums": [8700, 8900, 9100, 9300, 9500, 9700, 9900, 10100, 10400, 10700, 11000, 11300, 11600, 11900, 12200, 12500],
        "payable": [129200, 132400, 135600, 138800, 142000, 145200, 148400, 151600, 156400, 161200, 166000, 170800, 175600, 180400, 185200, 190000],
        "dividend": [3800, 3600, 3400, 3200, 3000, 2800, 2600, 2400, 2100, 1800, 1500, 1200, 900, 600, 300, 0],
    },
    "100000-16": {
        "premiums": [4350, 4450, 4550, 4650, 4750, 4850, 4950, 5050, 5200, 5350, 5500, 5650, 5800, 5950, 6100, 6250],
        "payable": [64600, 66200, 67800, 69400, 71000, 72600, 74200, 75800, 78200, 80600, 83000, 85400, 87800, 90200, 92600, 95000],
        "dividend": [1900, 1800, 1700, 1600, 1500, 1400, 1300, 1200, 1050, 900, 750, 600, 450, 300, 150, 0],
    },
    "500000-20": {
        "premiums": [17350, 17700, 18050, 18400, 18750, 19100, 19450, 19800, 20150, 20500, 20950, 21400, 21850, 22300, 22750, 23200, 23650, 24100, 24550, 25000],
        "payable": [327000, 334000, 341000, 348000, 355000, 362000, 369000, 376000, 383000, 390000, 399000, 408000, 417000, 426000, 435000, 444000, 453000, 462000, 471000, 480000],
        "dividend": [7650, 7300, 6950, 6600, 6250, 5900, 5550, 5200, 4850, 4500, 4050, 3600, 3150, 2700, 2250, 1800, 1350, 900, 450, 0],
    },
}

PRESETS = [
    {"name": "₹1 Lakh · 10 Months", "chit_value": 100000, "duration": 10, "member_limit": 10, "month1_premium": 7710},
    {"name": "₹2 Lakhs · 16 Months", "chit_value": 200000, "duration": 16, "member_limit": 16, "month1_premium": 8700},
    {"name": "₹1 Lakh · 16 Months", "chit_value": 100000, "duration": 16, "member_limit": 16, "month1_premium": 4350},
    {"name": "₹5 Lakhs · 20 Months", "chit_value": 500000, "duration": 20, "member_limit": 20, "month1_premium": 17350},
]

def make_schedule(value, duration, start_date, custom_monthly=None):
    """Use the uploaded scheme schedule; dates follow the selected start date."""
    import calendar
    source = SCHEDULE_DATA.get(f"{value}-{duration}")
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        start = datetime.now()
    rows = []
    for index in range(duration):
        year = start.year + (start.month - 1 + index) // 12
        month = (start.month - 1 + index) % 12 + 1
        day = min(start.day, calendar.monthrange(year, month)[1])
        due_date = datetime(year, month, day).strftime("%Y-%m-%d")
        if source:
            premium = source["premiums"][index]
            payable = source["payable"][index]
            dividend = source["dividend"][index]
        else:
            premium = float(custom_monthly if custom_monthly is not None else round(value / duration, 2))
            payable = None
            dividend = None
        rows.append({"month": index + 1, "premium_amount": premium,
                     "payable_amount": payable, "dividend": dividend, "due_date": due_date})
    return rows

def oid(value):
    try:
        return ObjectId(value)
    except Exception:
        return None

def serialize_chit(chit):
    # Never mutate the MongoDB document: ledger/payment lookups still need its ObjectId.
    result = dict(chit)
    result["_id"] = str(chit["_id"])
    result["owner_id"] = str(chit["owner_id"])
    created = chit.get("created_at")
    result["created_at"] = created.isoformat() if hasattr(created, "isoformat") else str(created or "")
    schedule = chit.get("schedule") or []
    result["end_date"] = schedule[-1]["due_date"] if schedule else chit.get("start_date")
    result["members"] = normalise_members(chit)
    result["member_count"] = len(result["members"])
    result["lottery_finalised"] = bool(chit.get("lottery", {}).get("finalised_at"))
    return result


def normalise_members(chit):
    """Return a stable, frontend-safe list from the chit document's embedded members."""
    result = []
    for member in (chit.get("members") or []):
        item = dict(member)
        raw_id = item.get("id", item.get("_id"))
        if raw_id is not None:
            item["id"] = str(raw_id)
        item.pop("_id", None)
        item["name"] = str(item.get("name") or "Unnamed member")
        item["phone"] = str(item.get("phone") or "")
        item["reference"] = str(item.get("reference") or "")
        joined = item.get("joined_at")
        item["joined_at"] = joined.isoformat() if hasattr(joined, "isoformat") else str(joined or "")
        result.append(item)
    return result


def outstanding_as_of_today(ledger):
    """Return unpaid balance for the active instalment, including its first instalment before start date.

    Before the first due date, month 1 is treated as the active instalment so
    advance/partial collections immediately show the remaining amount. Once
    instalments have started, use the latest instalment due today or earlier.
    The ledger balance already includes all carried-forward arrears.
    """
    if not ledger:
        return 0.0
    today = date.today().isoformat()
    due_indexes = [i for i, row in enumerate(ledger)
                   if (row.get("due_date") or "9999-12-31") <= today]
    active_index = due_indexes[-1] if due_indexes else 0
    return round(float(ledger[active_index].get("balance", 0) or 0), 2)

def owned_chit(chit_id, owner_id):
    ident = oid(chit_id)
    if not ident:
        return None
    return chits.find_one({"_id": ident, "owner_id": oid(owner_id)})

def member_ledger(chit, member):
    rows = []
    balance = 0
    member_id = str(member.get("id", member.get("_id", "")))
    schedule = chit.get("schedule") or make_schedule(
        chit["chit_value"], chit["duration"], chit.get("start_date"), chit.get("monthly_base")
    )
    for month in range(1, chit["duration"] + 1):
        schedule_row = schedule[month - 1]
        base_amount = float(schedule_row["premium_amount"])
        previous_due = balance
        due = round(base_amount + previous_due, 2)
        # Read both ObjectId/int and legacy string formats from earlier versions.
        month_payments = list(payments.find({
            "chit_id": {"$in": [chit["_id"], str(chit["_id"])]},
            "member_id": {"$in": [member_id, oid(member_id)] if oid(member_id) else [member_id]},
            "month": {"$in": [month, str(month)]}
        }).sort("created_at", 1))
        paid = sum(float(p["amount"]) for p in month_payments)
        balance = max(0, round(due - paid, 2))
        rows.append({
            "month": month, "base_amount": base_amount, "premium_amount": base_amount,
            "payable_amount": schedule_row.get("payable_amount"),
            "dividend": schedule_row.get("dividend"), "due_date": schedule_row.get("due_date"),
            "previous_due": round(previous_due, 2), "amount_due": due,
            "paid": round(paid, 2), "balance": balance,
            "status": "Paid" if balance == 0 else ("Partial" if paid > 0 else "Pending"),
            "payments": [{"id": str(p["_id"]), "amount": p["amount"],
                          "date": p["created_at"].isoformat() if hasattr(p.get("created_at"), "isoformat") else str(p.get("created_at", "")), "note": p.get("note", "")}
                         for p in month_payments]
        })
    return rows

def chit_totals(chit):
    total_paid = 0
    total_outstanding = 0
    for member in chit.get("members", []):
        ledger = member_ledger(chit, member)
        total_paid += sum(row["paid"] for row in ledger)
        if ledger:
            total_outstanding += outstanding_as_of_today(ledger)
    return round(total_paid, 2), round(total_outstanding, 2)

@app.get("/api/health")
def health():
    try:
        client.admin.command("ping")
        return jsonify({"status": "ok", "database": "connected"})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 503

@app.post("/api/auth/register")
def register():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not name or not email or len(password) < 6:
        return jsonify({"message": "Enter your name, a valid email and a password of at least 6 characters."}), 400
    if users.find_one({"email": email}):
        return jsonify({"message": "An account with this email already exists."}), 409
    user_id = users.insert_one({
        "name": name, "email": email,
        "password": generate_password_hash(password),
        "created_at": datetime.now(timezone.utc)
    }).inserted_id
    token = create_access_token(identity=str(user_id))
    return jsonify({"token": token, "user": {"id": str(user_id), "name": name, "email": email}}), 201

@app.post("/api/auth/login")
def login():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    user = users.find_one({"email": email})
    if not user or not check_password_hash(user["password"], data.get("password") or ""):
        return jsonify({"message": "Email or password is incorrect."}), 401
    token = create_access_token(identity=str(user["_id"]))
    return jsonify({"token": token, "user": {"id": str(user["_id"]), "name": user["name"], "email": user["email"]}})

@app.get("/api/auth/me")
@jwt_required()
def me():
    user = users.find_one({"_id": oid(get_jwt_identity())}, {"password": 0})
    if not user:
        return jsonify({"message": "Account not found."}), 404
    return jsonify({"id": str(user["_id"]), "name": user["name"], "email": user["email"]})

@app.get("/api/presets")
def presets():
    return jsonify(PRESETS)

@app.get("/api/chits")
@jwt_required()
def get_chits():
    owner = oid(get_jwt_identity())
    result = []
    for chit in chits.find({"owner_id": owner}).sort("created_at", DESCENDING):
        if not chit.get("schedule"):
            chit["schedule"] = make_schedule(chit["chit_value"], chit["duration"], chit.get("start_date"), chit.get("monthly_base"))
        paid, outstanding = chit_totals(chit)
        item = serialize_chit(chit)
        item["member_count"] = len(item["members"])
        item["paid"] = paid
        item["outstanding"] = outstanding
        result.append(item)
    return jsonify(result)

@app.post("/api/chits")
@jwt_required()
def create_chit():
    data = request.get_json() or {}
    try:
        value = int(data.get("chit_value", 0))
        duration = int(data.get("duration", 0))
        limit = int(data.get("member_limit", duration))
        start_date = data.get("start_date") or date.today().isoformat()
        parsed_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        monthly_base = round(value / duration, 2)
        if value <= 0 or duration < 2 or duration > 60 or limit < 1 or limit > 100:
            raise ValueError()
        if parsed_start < date.today():
            return jsonify({"message": "Start date cannot be in the past. Completed months are kept in History."}), 400
    except (ValueError, TypeError, ZeroDivisionError):
        return jsonify({"message": "Enter valid chit value, duration and member limit."}), 400
    doc = {
        "owner_id": oid(get_jwt_identity()),
        "name": (data.get("name") or f"₹{value:,} Chit").strip(),
        "chit_value": value, "duration": duration, "member_limit": limit,
        "monthly_base": monthly_base, "start_date": start_date,
        "schedule": make_schedule(value, duration, start_date, monthly_base),
        "notes": (data.get("notes") or "").strip(),
        "members": [], "created_at": datetime.now(timezone.utc)
    }
    result = chits.insert_one(doc)
    doc["_id"] = result.inserted_id
    return jsonify(serialize_chit(doc)), 201

@app.get("/api/chits/<chit_id>")
@jwt_required()
def get_chit(chit_id):
    chit = owned_chit(chit_id, get_jwt_identity())
    if not chit:
        return jsonify({"message": "Chit not found."}), 404
    if not chit.get("schedule"):
        chit["schedule"] = make_schedule(chit["chit_value"], chit["duration"], chit.get("start_date"), chit.get("monthly_base"))
    item = serialize_chit(chit)
    item["members"] = [{
        **m, "ledger": member_ledger(chit, m)
    } for m in normalise_members(chit)]
    item["member_count"] = len(item["members"])
    paid, outstanding = chit_totals(chit)
    item["paid"] = paid
    item["outstanding"] = outstanding
    item["month1_expected_full_capacity"] = round(float((chit.get("schedule") or make_schedule(chit["chit_value"], chit["duration"], chit.get("start_date")))[0]["premium_amount"]) * int(chit["member_limit"]), 2)
    schedule = chit.get("schedule") or make_schedule(chit["chit_value"], chit["duration"], chit.get("start_date"))
    item["later_scheduled_per_member"] = round(sum(float(row["premium_amount"]) for row in schedule[1:]), 2)
    item["later_scheduled_all_members"] = round(item["later_scheduled_per_member"] * len(item["members"]), 2)
    return jsonify(item)

@app.delete("/api/chits/<chit_id>")
@jwt_required()
def delete_chit(chit_id):
    chit = owned_chit(chit_id, get_jwt_identity())
    if not chit:
        return jsonify({"message": "Chit not found."}), 404
    payments.delete_many({"chit_id": chit["_id"]})
    chits.delete_one({"_id": chit["_id"]})
    return jsonify({"message": "Chit deleted."})

@app.post("/api/chits/<chit_id>/members")
@jwt_required()
def add_member(chit_id):
    chit = owned_chit(chit_id, get_jwt_identity())
    if not chit:
        return jsonify({"message": "Chit not found."}), 404
    if chit.get("lottery", {}).get("finalised_at"):
        return jsonify({"message": "The member list is locked because the monthly allotment has been finalised."}), 409
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"message": "Member name is required."}), 400
    if len(chit.get("members", [])) >= chit["member_limit"]:
        return jsonify({"message": "This chit has reached its member limit."}), 400
    member = {
        "id": str(ObjectId()), "name": name,
        "phone": (data.get("phone") or "").strip(),
        "reference": (data.get("reference") or "").strip(),
        "joined_at": datetime.now(timezone.utc).isoformat()
    }
    chits.update_one({"_id": chit["_id"]}, {"$push": {"members": member}})
    return jsonify(member), 201

@app.delete("/api/chits/<chit_id>/members/<member_id>")
@jwt_required()
def delete_member(chit_id, member_id):
    chit = owned_chit(chit_id, get_jwt_identity())
    if not chit:
        return jsonify({"message": "Chit not found."}), 404
    if not any(m["id"] == member_id for m in chit.get("members", [])):
        return jsonify({"message": "Member not found."}), 404
    if chit.get("lottery", {}).get("finalised_at"):
        return jsonify({"message": "The member list is locked because the monthly allotment has been finalised."}), 409
    chits.update_one({"_id": chit["_id"]}, {"$pull": {"members": {"id": member_id}}})
    payments.delete_many({"chit_id": chit["_id"], "member_id": member_id})
    return jsonify({"message": "Member removed."})

@app.post("/api/chits/<chit_id>/members/<member_id>/payments")
@jwt_required()
def add_payment(chit_id, member_id):
    chit = owned_chit(chit_id, get_jwt_identity())
    if not chit:
        return jsonify({"message": "Chit not found."}), 404
    if not any(m["id"] == member_id for m in chit.get("members", [])):
        return jsonify({"message": "Member not found."}), 404
    data = request.get_json() or {}
    try:
        month = int(data.get("month"))
        amount = round(float(data.get("amount")), 2)
        if month < 1 or month > chit["duration"] or amount <= 0:
            raise ValueError()
        schedule = chit.get("schedule") or make_schedule(chit["chit_value"], chit["duration"], chit.get("start_date"), chit.get("monthly_base"))
        month_due_date = datetime.strptime(schedule[month - 1]["due_date"], "%Y-%m-%d").date()
        if month_due_date < date.today():
            return jsonify({"message": "This month is completed and is available only in History. Record payments against the current or an upcoming month."}), 400
    except (ValueError, TypeError):
        return jsonify({"message": "Enter a valid month and payment amount."}), 400
    result = payments.insert_one({
        "chit_id": chit["_id"], "member_id": member_id,
        "month": month, "amount": amount,
        "note": (data.get("note") or "").strip(),
        "created_at": datetime.now(timezone.utc)
    })
    member = next(m for m in chit.get("members", []) if m["id"] == member_id)
    ledger = member_ledger(chit, member)
    total_collected = round(sum(row["paid"] for row in ledger), 2)
    outstanding = round(ledger[-1]["balance"], 2) if ledger else 0
    return jsonify({
        "message": "Payment recorded.",
        "payment_id": str(result.inserted_id),
        "member_collected": total_collected,
        "member_outstanding": outstanding,
        "month_paid": ledger[month - 1]["paid"],
        "month_balance": ledger[month - 1]["balance"]
    }), 201

@app.post("/api/chits/<chit_id>/lottery/finalise")
@jwt_required()
def finalise_lottery(chit_id):
    chit = owned_chit(chit_id, get_jwt_identity())
    if not chit:
        return jsonify({"message": "Chit not found."}), 404
    if chit.get("lottery", {}).get("finalised_at"):
        return jsonify({"message": "The monthly allotment has already been finalised. It cannot be submitted again."}), 409
    members = chit.get("members", [])
    if len(members) != chit["duration"]:
        return jsonify({"message": f"Add exactly {chit['duration']} members before finalising the allotment. Currently {len(members)} are added."}), 400
    data = request.get_json() or {}
    assignments = data.get("assignments") or []
    if len(assignments) != chit["duration"]:
        return jsonify({"message": f"Enter one winner for each of the {chit['duration']} months."}), 400
    member_by_id = {m["id"]: m for m in members}
    seen = set()
    clean = []
    for expected_month, row in enumerate(assignments, start=1):
        try:
            month = int(row.get("month"))
        except (TypeError, ValueError):
            month = 0
        member_id = str(row.get("member_id") or "")
        if month != expected_month or member_id not in member_by_id or member_id in seen:
            return jsonify({"message": "Each month must have one valid member, and every member must be selected exactly once."}), 400
        seen.add(member_id)
        clean.append({
            "month": month,
            "due_date": (chit.get("schedule") or make_schedule(chit["chit_value"], chit["duration"], chit.get("start_date"), chit.get("monthly_base")))[month - 1]["due_date"],
            "member_id": member_id,
            "member_name": member_by_id[member_id]["name"],
            "ticket_number": str(row.get("ticket_number") or "").strip()
        })
    if len(seen) != chit["duration"]:
        return jsonify({"message": "Every member must be allotted exactly one month."}), 400
    lottery = {"assignments": clean, "finalised_at": datetime.now(timezone.utc).isoformat()}
    chits.update_one({"_id": chit["_id"]}, {"$set": {"lottery": lottery}})
    return jsonify({"message": "All monthly allotments have been finalised.", "lottery": lottery}), 201


@app.get("/api/dashboard")
@jwt_required()
def dashboard():
    owner = oid(get_jwt_identity())
    all_chits = list(chits.find({"owner_id": owner}))
    total_members = sum(len(normalise_members(c)) for c in all_chits)
    chit_summaries = []
    for chit in all_chits:
        if not chit.get("schedule"):
            chit["schedule"] = make_schedule(chit["chit_value"], chit["duration"], chit.get("start_date"), chit.get("monthly_base"))
        paid, outstanding = chit_totals(chit)
        member_count = len(normalise_members(chit))
        chit_summaries.append({
            "id": str(chit["_id"]), "name": chit["name"],
            "chit_value": chit["chit_value"], "duration": chit["duration"],
            "member_count": member_count, "member_limit": chit["member_limit"],
            "monthly_base": chit["schedule"][0]["premium_amount"],
            "schedule": chit["schedule"],
            "end_date": chit["schedule"][-1]["due_date"] if chit.get("schedule") else chit.get("start_date"),
            "lottery_finalised": bool(chit.get("lottery", {}).get("finalised_at")),
            "paid": paid, "outstanding": outstanding
        })
    return jsonify({"total_chits": len(all_chits), "total_members": total_members,
                    "chits": chit_summaries})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
