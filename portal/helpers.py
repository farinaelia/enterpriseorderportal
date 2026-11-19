"""Small helper functions used by many pages.

Two kinds of helper live here:

1. Jinja *filters* - used inside templates, e.g. {{ order.updated_at|dt }}
2. Python functions used by views, e.g. load_order_bundle()
"""
import os
import re
from datetime import datetime

from flask import current_app, g, url_for

from . import constants as C

DT_FORMAT = "%Y-%m-%d %H:%M"


# ------------------------------------------------------------ filters ----
def _parse(value):
    if isinstance(value, datetime):
        return value
    return datetime.strptime(value, DT_FORMAT)


def fmt_date(value):
    """'2026-03-18 08:20' -> '18 Mar 2026'  (works on Windows, Mac, Linux)."""
    if not value:
        return "—"
    d = _parse(value if len(value) > 10 else value + " 00:00")
    return f"{d.day:02d} {d:%b %Y}"


def fmt_time(value):
    """'2026-03-18 08:20' -> '8:20 AM'."""
    d = _parse(value)
    return d.strftime("%I:%M %p").lstrip("0")


def fmt_datetime(value):
    """'2026-03-17 15:24' -> '17 Mar 2026, 3:24 PM'."""
    if not value:
        return "—"
    return f"{fmt_date(value)}, {fmt_time(value)}"


def fmt_money(value):
    """1914 -> 'RM 1,914.00'."""
    return f"RM {value or 0:,.2f}"


def fmt_money_short(value):
    """68 -> 'RM 68.00' (same as money, kept separate for clarity)."""
    return fmt_money(value)


def mask_id(value):
    """'900101-14-1234' -> '******-**-1234' (hide all but the last 4 digits)."""
    if not value:
        return "—"
    digits_total = len(re.findall(r"\d", value))
    seen = 0
    out = []
    for ch in value:
        if ch.isdigit():
            seen += 1
            out.append(ch if seen > digits_total - 4 else "*")
        else:
            out.append(ch)
    return "".join(out)


def mask_brn(value):
    """'202601234567' -> '2026******67' (show first 4 and last 2)."""
    if not value:
        return "—"
    return value[:4] + "*" * (len(value) - 6) + value[-2:]


def mask_account(value):
    """'123454589' -> '*****4589' (show only the last 4)."""
    if not value:
        return "—"
    return "*" * (len(value) - 4) + value[-4:]


def slug(value):
    """'Under Review' -> 'under-review' (used for CSS class names)."""
    return value.lower().replace(" ", "-")


def initials(name):
    """'Muhammad Syufaiq' -> 'MS'."""
    parts = name.split()
    return (parts[0][0] + parts[-1][0]).upper() if parts else "?"


def split_csv(value):
    """'a,b,c' -> ['a', 'b', 'c'];  None -> []"""
    return [x.strip() for x in value.split(",")] if value else []


# --------------------------------------------------------- view helpers ----
def load_order_bundle(db, order):
    """Gather everything the order detail page needs into one dictionary.

    `order` is a row from the orders table. We fetch its lines, documents and
    events, then calculate totals, the progress bar and the resolved
    amendments. Keeping this here keeps the view function short.
    """
    oid = order["id"]
    lines = db.execute(
        "SELECT * FROM order_lines WHERE order_id = ? ORDER BY position", (oid,)
    ).fetchall()
    docs = db.execute(
        "SELECT * FROM documents WHERE order_id = ?", (oid,)
    ).fetchall()
    events = db.execute(
        "SELECT * FROM order_events WHERE order_id = ? ORDER BY ts, id", (oid,)
    ).fetchall()

    # --- subscription totals ---
    total_lines = sum(l["num_lines"] for l in lines)
    monthly = sum(l["num_lines"] * l["monthly"] for l in lines)
    upfront = sum(
        (l["device_qty"] or 0) * (l["device_price"] or 0)
        + (l["upfront"] or 0) + (l["deposit"] or 0)
        for l in lines
    )

    # --- documents: required ones first (uploaded or missing) ---
    docs_by_key = {d["doc_key"]: d for d in docs}
    required = C.required_doc_keys(order["customer_type"], order["order_type"])
    doc_rows = []
    for key in required:
        doc_rows.append(dict(key=key, label=C.DOC_LABELS[key], required=True,
                             file=docs_by_key.get(key)))
    for d in docs:  # uploaded optional documents
        if d["doc_key"] not in required:
            doc_rows.append(dict(key=d["doc_key"], label=C.DOC_LABELS[d["doc_key"]],
                                 required=False, file=d))
    required_uploaded = sum(1 for k in required if k in docs_by_key)

    # --- progress bar ---
    current = C.STEP_INDEX[order["status"]]
    all_done = order["status"] == "Completed"
    first_event_date = {}
    for e in events:
        first_event_date.setdefault(e["status"], e["ts"])
    steps = []
    for i, name in enumerate(C.PROGRESS_STEPS):
        if all_done or i < current:
            state = "done"
        elif i == current:
            state = "current"
        else:
            state = "pending"
        when = order["created_at"] if name == "Draft" else first_event_date.get(name)
        steps.append(dict(name=name, state=state, date=when))

    # --- resolved amendments (a request followed by a dealer resubmission) ---
    resolved = []
    pending_request = None
    for e in events:
        if e["title"] == "Amendment requested":
            pending_request = e
        elif e["title"] == "Order resubmitted" and pending_request:
            response = (e["note"] or "").replace("Dealer response: ", "")
            resolved.append(dict(category=pending_request["category"],
                                 reason=pending_request["note"],
                                 response=response))
            pending_request = None

    return dict(
        lines=lines, docs=docs, events=events,
        total_lines=total_lines, monthly=monthly, upfront=upfront,
        doc_rows=doc_rows, required_total=len(required),
        required_uploaded=required_uploaded,
        steps=steps, resolved=resolved,
        amend_sections=split_csv(order["amendment_sections"]),
        locked=order["status"] in C.LOCKED_STATUSES,
    )


def upload_root():
    """Folder where uploaded documents live (instance/uploads by default)."""
    return current_app.config.get("UPLOAD_FOLDER") or os.path.join(current_app.instance_path, "uploads")


# ---------------------------------------------------------- navigation ----
WORKSPACE_LABEL = {
    "dealer": "Dealer workspace",
    "processor": "Processor workspace",
    "admin": "Admin workspace",
}


def nav_for(user, db):
    """The sidebar links for this user's role.

    Each item: (key, label, icon name, url, badge number or None).
    `key` is compared with the `active` variable each page passes in, which is
    how the current page gets highlighted.
    """
    role = user["role"]
    if role == "dealer":
        amendments = db.execute(
            "SELECT COUNT(*) FROM orders WHERE dealer_id = ? AND status = 'Amendment Required'",
            (user["id"],)).fetchone()[0]
        return [
            ("dashboard", "Dashboard", "dashboard", url_for("dealer.dashboard"), None),
            ("orders", "My Orders", "folder", url_for("dealer.orders"), amendments or None),
            ("create", "Create Order", "file-plus", url_for("wizard.create"), None),
            ("help", "Help", "help", url_for("dealer.help"), None),
        ]
    if role == "processor":
        waiting = db.execute(
            "SELECT COUNT(*) FROM orders WHERE status = 'Submitted'").fetchone()[0]
        return [
            ("dashboard", "Dashboard", "dashboard", url_for("processor.dashboard"), None),
            ("queue", "Work Queue", "list-check", url_for("processor.queue"), waiting or None),
            ("all", "All Orders", "folder", url_for("processor.all_orders"), None),
            ("help", "Help", "help", url_for("processor.help"), None),
        ]
    return [
        ("overview", "Overview", "dashboard", url_for("admin.overview"), None),
        ("all", "All Orders", "folder", url_for("admin.all_orders"), None),
        ("history", "Status History", "history", url_for("admin.history"), None),
        ("users", "Users", "users", url_for("admin.users"), None),
        ("reports", "Reports", "chart", url_for("admin.reports"), None),
    ]


# ------------------------------------------------------------- wiring ----
def init_app(app):
    app.jinja_env.filters.update(
        date=fmt_date, time=fmt_time, dt=fmt_datetime, money=fmt_money,
        mask_id=mask_id, mask_brn=mask_brn, mask_account=mask_account,
        slug=slug, csv=split_csv, initials=initials,
    )

    @app.context_processor
    def inject_globals():
        """Variables every template can use without being passed in."""
        from .db import get_db

        user = getattr(g, "user", None)
        data = dict(C=C, current_user=user, nav_items=[], workspace_label="")
        if user is not None:
            data["nav_items"] = nav_for(user, get_db())
            data["workspace_label"] = WORKSPACE_LABEL[user["role"]]
        return data
