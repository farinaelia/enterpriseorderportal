"""Form handling for the Create Order wizard.

Every wizard step has the same four jobs, so this file has four kinds of
function:

    parse_step(step, form)        read the submitted form into a plain dict
    validate_step(step, values)   return a dict of  {field_name: error message}
    load_values(db, order, step)  read the saved values of a step from the DB
    save_step(db, order, step, values)  write the values to the DB

Two ideas are worth knowing:

* "Save Draft" is LENIENT: it saves whatever was typed, even if incomplete,
  so a dealer can leave and come back. "Continue" is STRICT: it validates
  first and only moves on when there are no errors.
* Column names are never taken from the browser. Each step lists the columns
  it may write (the *_FIELDS lists below), which keeps the SQL safe.
"""
import re
from datetime import datetime

from . import constants as C

# --------------------------------------------------------- field lists ----
STEP1_FIELDS = ["order_type", "registration_type"]

STEP2_FIELDS = [
    "customer_type", "company_name", "brn", "old_brn", "tin", "sst_no",
    "existing_account_no", "address", "city", "postcode",
    "contact_name", "contact_id_no", "contact_designation",
    "contact_phone", "contact_email",
]

STEP5_FIELDS = [
    "partner_name", "channel", "region", "account_manager",
    "customer_category", "site_contact_name", "site_contact_number",
    "device_model", "device_quantity", "service_address",
    "installation_address", "internal_notes",
]

# Longest text allowed per field (anything longer is a validation error).
MAX_LEN = {
    "company_name": 120, "tin": 30, "existing_account_no": 20,
    "address": 200, "city": 60, "contact_name": 100,
    "contact_designation": 80, "contact_email": 120,
    "partner_name": 100, "site_contact_name": 100,
    "service_address": 200, "installation_address": 200,
    "internal_notes": 500, "other_requirements": 500,
}

LINE_TEXT_FIELDS = ["registration_type", "rate_plan", "billing_type",
                    "device_model", "notes"]
LINE_NUM_FIELDS = ["monthly", "num_lines", "contract_months", "device_qty",
                   "device_price", "upfront", "deposit"]

# ------------------------------------------------------------ patterns ----
RE_BRN = re.compile(r"^\d{12}$")                 # 202601234567
RE_OLD_BRN = re.compile(r"^[0-9]{5,7}-?[A-Za-z]$")  # 123456-X
RE_SST = re.compile(r"^[A-Za-z]\d{2}-\d{4}-\d{8}$")  # W10-1234-32000001
RE_POSTCODE = re.compile(r"^\d{5}$")
RE_ID = re.compile(r"^\d{6}-\d{2}-\d{4}$")       # 900101-14-1234
RE_PHONE = re.compile(r"^(?:\+?60|0)\d{8,10}$")
RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean(value):
    """Trim spaces; None becomes an empty string."""
    return (value or "").strip()


def to_int(value, default=0):
    try:
        return int(float(clean(str(value)).replace(",", "")))
    except (TypeError, ValueError):
        return default


def to_float(value, default=0.0):
    try:
        return float(clean(str(value)).replace(",", ""))
    except (TypeError, ValueError):
        return default


def is_number(value):
    try:
        float(clean(str(value)).replace(",", ""))
        return True
    except ValueError:
        return False


def strip_phone(value):
    return re.sub(r"[\s\-()]", "", value)


# ----------------------------------------------------------- order lines ----
def blank_line(order_type=None, registration_type=None):
    """A new empty subscription line with sensible defaults."""
    plans = C.plans_for(order_type)
    plan = plans[0] if len(plans) == 1 else ""
    return dict(
        registration_type=registration_type or "New Connection",
        rate_plan=plan,
        addons=[], services=[],
        monthly=str(C.RATE_PLANS[plan]) if plan else "",
        num_lines="1", contract_months="12",
        device_model="", device_qty="0", device_price="0",
        upfront="0", deposit="0",
        billing_type=C.BILLING_TYPES[0], fixed_ip=False, notes="",
    )


def _parse_lines(form):
    """Read l0_rate_plan, l1_rate_plan ... from the form."""
    count = to_int(form.get("line_count"), 0)
    lines = []
    for i in range(min(count, 20)):
        p = f"l{i}_"
        if form.get(p + "num_lines") is None and form.get(p + "rate_plan") is None:
            continue
        line = {f: clean(form.get(p + f)) for f in LINE_TEXT_FIELDS + LINE_NUM_FIELDS}
        line["addons"] = [a for a in form.getlist(p + "addons") if a in C.ADDONS]
        line["services"] = [s for s in form.getlist(p + "services") if s in C.SERVICES]
        line["fixed_ip"] = form.get(p + "fixed_ip") == "on"
        lines.append(line)
    return lines


# --------------------------------------------------------------- parsing ----
def parse_step(step, form):
    """Turn a submitted form into a dict of cleaned strings."""
    if step == 1:
        return {f: clean(form.get(f)) for f in STEP1_FIELDS}
    if step == 2:
        v = {f: clean(form.get(f)) for f in STEP2_FIELDS}
        # Store IDs without spaces, so "9001011 41234" cannot slip through.
        v["contact_id_no"] = v["contact_id_no"].replace(" ", "")
        v["brn"] = v["brn"].replace(" ", "").replace("-", "")
        return v
    if step == 3:
        return {"lines": _parse_lines(form),
                "other_requirements": clean(form.get("other_requirements"))}
    if step == 5:
        return {f: clean(form.get(f)) for f in STEP5_FIELDS}
    return {}


# ------------------------------------------------------------ validation ----
def validate_step(step, v, order=None):
    """Return {field_name: message}. An empty dict means the step is valid."""
    e = {}
    if step == 1:
        if v.get("order_type") not in C.ORDER_TYPES:
            e["order_type"] = "Choose an order type."
        if v.get("registration_type") not in C.REGISTRATION_TYPES:
            e["registration_type"] = "Choose a registration type."

    elif step == 2:
        _validate_customer(v, e)

    elif step == 3:
        _validate_lines(v, e, order["order_type"] if order is not None else None)

    elif step == 5:
        _validate_internal(v, e)
    return e


def _too_long(v, e, field, label):
    if len(v.get(field, "")) > MAX_LEN[field]:
        e[field] = f"{label} must be {MAX_LEN[field]} characters or fewer."


def _validate_customer(v, e):
    if v.get("customer_type") not in C.CUSTOMER_TYPES:
        e["customer_type"] = "Choose a customer type."
    corporate = v.get("customer_type") == "Corporate Account"

    def need(field, message):
        if not v.get(field):
            e[field] = message

    need("company_name", "Enter the company name.")
    need("address", "Enter the address.")
    need("city", "Enter the city.")
    need("postcode", "Enter the postcode.")
    need("contact_name", "Enter the contact's full name.")
    need("contact_id_no", "Enter the contact's identification number.")
    need("contact_phone", "Enter a contact phone number.")
    need("contact_email", "Enter a contact email address.")
    if corporate:
        need("brn", "Enter the business registration number.")
        need("contact_designation", "Enter the contact's designation.")

    if v.get("brn") and not RE_BRN.match(v["brn"]):
        e["brn"] = "The business registration number must be 12 digits."
    if v.get("old_brn") and not RE_OLD_BRN.match(v["old_brn"]):
        e["old_brn"] = "Use the old format, for example 123456-X."
    if v.get("sst_no") and not RE_SST.match(v["sst_no"]):
        e["sst_no"] = "Use the format W10-1234-32000001."
    if v.get("postcode") and not RE_POSTCODE.match(v["postcode"]):
        e["postcode"] = "The postcode must be 5 digits."
    if v.get("contact_id_no") and not RE_ID.match(v["contact_id_no"]):
        e["contact_id_no"] = "Use the format 900101-14-1234."
    if v.get("contact_phone") and not RE_PHONE.match(strip_phone(v["contact_phone"])):
        e["contact_phone"] = "Enter a valid Malaysian phone number, e.g. 012-345 6789."
    if v.get("contact_email") and not RE_EMAIL.match(v["contact_email"]):
        e["contact_email"] = "Enter a valid email address."

    for field, label in [("company_name", "Company name"), ("address", "Address"),
                         ("city", "City"), ("contact_name", "Contact name"),
                         ("contact_designation", "Designation"),
                         ("contact_email", "Email"), ("tin", "TIN"),
                         ("existing_account_no", "Account number")]:
        if field not in e:
            _too_long(v, e, field, label)


def _validate_lines(v, e, order_type):
    lines = v.get("lines", [])
    if not lines:
        e["lines"] = "Add at least one subscription line."
    allowed = C.plans_for(order_type)
    for i, ln in enumerate(lines):
        p = f"l{i}_"
        if ln["registration_type"] not in C.REGISTRATION_TYPES:
            e[p + "registration_type"] = "Choose a registration type."
        if ln["rate_plan"] not in allowed:
            e[p + "rate_plan"] = ("Choose a rate plan." if not ln["rate_plan"]
                                  else "This plan is not available for this order type.")
        if not is_number(ln["monthly"]) or to_float(ln["monthly"]) <= 0:
            e[p + "monthly"] = "Enter a monthly commitment above RM 0."
        if to_int(ln["num_lines"]) < 1 or to_int(ln["num_lines"]) > 999:
            e[p + "num_lines"] = "Enter between 1 and 999 lines."
        if to_int(ln["contract_months"]) not in C.CONTRACT_MONTHS:
            e[p + "contract_months"] = "Choose a contract length."
        if ln["billing_type"] not in C.BILLING_TYPES:
            e[p + "billing_type"] = "Choose a billing type."
        if ln["device_model"]:
            if ln["device_model"] not in C.DEVICE_MODELS:
                e[p + "device_model"] = "Choose a device from the list."
            if to_int(ln["device_qty"]) < 1:
                e[p + "device_qty"] = "Enter a device quantity of 1 or more."
        for f, label in [("device_price", "Device price"), ("upfront", "Upfront charge"),
                         ("deposit", "Deposit")]:
            if ln[f] and (not is_number(ln[f]) or to_float(ln[f]) < 0):
                e[p + f] = f"{label} cannot be negative."
        if len(ln["notes"]) > 200:
            e[p + "notes"] = "Notes must be 200 characters or fewer."
    _too_long(v, e, "other_requirements", "Other requirements")


def _validate_internal(v, e):
    for field, options, message in [
        ("channel", C.CHANNELS, "Choose a channel."),
        ("region", C.REGIONS, "Choose a region."),
        ("customer_category", C.CUSTOMER_CATEGORIES, "Choose a customer category."),
        ("account_manager", C.ACCOUNT_MANAGERS, "Choose an account manager."),
    ]:
        if v.get(field) not in options:
            e[field] = message
    if v.get("device_model") and v["device_model"] not in C.DEVICE_MODELS:
        e["device_model"] = "Choose a device from the list."
    if v.get("device_quantity") and (not v["device_quantity"].isdigit()):
        e["device_quantity"] = "Enter a whole number."
    if v.get("site_contact_number") and not RE_PHONE.match(strip_phone(v["site_contact_number"])):
        e["site_contact_number"] = "Enter a valid Malaysian phone number."
    for field, label in [("partner_name", "Partner name"),
                         ("site_contact_name", "Site contact name"),
                         ("service_address", "Service address"),
                         ("installation_address", "Installation address"),
                         ("internal_notes", "Internal notes")]:
        _too_long(v, e, field, label)


# --------------------------------------------------------------- loading ----
def load_values(db, order, step):
    """Read a step's saved values from the database (as strings)."""
    if step == 1:
        return {f: order[f] or "" for f in STEP1_FIELDS}
    if step == 2:
        v = {f: order[f] or "" for f in STEP2_FIELDS}
        v["customer_type"] = order["customer_type"] or "Corporate Account"
        return v
    if step == 3:
        rows = db.execute("SELECT * FROM order_lines WHERE order_id = ? ORDER BY position",
                          (order["id"],)).fetchall()
        lines = []
        for r in rows:
            lines.append(dict(
                registration_type=r["registration_type"] or "",
                rate_plan=r["rate_plan"] or "",
                addons=[a.strip() for a in (r["addons"] or "").split(",") if a.strip()],
                services=[s.strip() for s in (r["services"] or "").split(",") if s.strip()],
                monthly=_num_str(r["monthly"]), num_lines=str(r["num_lines"]),
                contract_months=str(r["contract_months"]),
                device_model=r["device_model"] or "",
                device_qty=str(r["device_qty"] or 0),
                device_price=_num_str(r["device_price"]),
                upfront=_num_str(r["upfront"]), deposit=_num_str(r["deposit"]),
                billing_type=r["billing_type"] or C.BILLING_TYPES[0],
                fixed_ip=bool(r["fixed_ip"]), notes=r["notes"] or "",
            ))
        if not lines:
            lines = [blank_line(order["order_type"], order["registration_type"])]
        return {"lines": lines, "other_requirements": order["other_requirements"] or ""}
    if step == 5:
        v = {f: order[f] or "" for f in STEP5_FIELDS}
        v["device_quantity"] = "" if order["device_quantity"] is None else str(order["device_quantity"])
        return v
    return {}


def _num_str(x):
    if x is None:
        return "0"
    return str(int(x)) if float(x) == int(x) else f"{float(x):.2f}"


# ---------------------------------------------------------------- saving ----
def split_sections(value):
    """'Subscription Details,Supporting Documents' -> list of known section names."""
    return [x.strip() for x in (value or "").split(",") if x.strip() in C.AMEND_SECTIONS]


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _lenient(value, field):
    return value[:MAX_LEN[field]] if field in MAX_LEN else value


def save_step(db, order, step, v):
    """Write a step's values to the database (does NOT commit)."""
    ts = now_str()
    if step == 1:
        db.execute(
            "UPDATE orders SET order_type = ?, registration_type = ?, updated_at = ? WHERE id = ?",
            (v["order_type"] if v["order_type"] in C.ORDER_TYPES else None,
             v["registration_type"] if v["registration_type"] in C.REGISTRATION_TYPES else None,
             ts, order["id"]))
    elif step == 2:
        data = {f: _lenient(v.get(f, ""), f) or None for f in STEP2_FIELDS}
        if data["customer_type"] not in C.CUSTOMER_TYPES:
            data["customer_type"] = "Corporate Account"
        sets = ", ".join(f"{f} = ?" for f in STEP2_FIELDS)
        db.execute(f"UPDATE orders SET {sets}, updated_at = ? WHERE id = ?",
                   [data[f] for f in STEP2_FIELDS] + [ts, order["id"]])
    elif step == 3:
        db.execute("DELETE FROM order_lines WHERE order_id = ?", (order["id"],))
        for pos, ln in enumerate(v["lines"], start=1):
            db.execute(
                """INSERT INTO order_lines
                   (order_id, position, registration_type, rate_plan, addons, services,
                    monthly, num_lines, contract_months, device_model, device_qty,
                    device_price, upfront, deposit, billing_type, fixed_ip, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (order["id"], pos, ln["registration_type"], ln["rate_plan"],
                 ",".join(ln["addons"]), ",".join(ln["services"]),
                 max(to_float(ln["monthly"]), 0), max(to_int(ln["num_lines"], 1), 1),
                 to_int(ln["contract_months"], 12) or 12,
                 ln["device_model"] or None, max(to_int(ln["device_qty"]), 0),
                 max(to_float(ln["device_price"]), 0), max(to_float(ln["upfront"]), 0),
                 max(to_float(ln["deposit"]), 0),
                 ln["billing_type"] or C.BILLING_TYPES[0], 1 if ln["fixed_ip"] else 0,
                 ln["notes"][:200] or None))
        db.execute("UPDATE orders SET other_requirements = ?, updated_at = ? WHERE id = ?",
                   (v["other_requirements"][:500] or None, ts, order["id"]))
    elif step == 5:
        data = {f: _lenient(v.get(f, ""), f) or None for f in STEP5_FIELDS}
        data["device_quantity"] = (int(v["device_quantity"])
                                   if v.get("device_quantity", "").isdigit() else None)
        sets = ", ".join(f"{f} = ?" for f in STEP5_FIELDS)
        db.execute(f"UPDATE orders SET {sets}, updated_at = ? WHERE id = ?",
                   [data[f] for f in STEP5_FIELDS] + [ts, order["id"]])


def next_order_number(db, year=None):
    """ORD-2026-00130 is the highest -> ORD-2026-00131."""
    year = year or datetime.now().year
    rows = db.execute("SELECT order_number FROM orders").fetchall()
    top = 0
    for r in rows:
        try:
            top = max(top, int(r["order_number"].rsplit("-", 1)[1]))
        except (ValueError, IndexError):
            pass
    return f"ORD-{year}-{top + 1:05d}"


# -------------------------------------------------------- whole-order check ----
def step_errors(db, order):
    """{step: errors} for every data step. Used by the stepper and Submit."""
    fresh = db.execute("SELECT * FROM orders WHERE id = ?", (order["id"],)).fetchone()
    out = {}
    for step in (1, 2, 3, 5):
        out[step] = validate_step(step, load_values(db, fresh, step), fresh)
    return out
