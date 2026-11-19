"""Processor and Admin areas (Stages 4 and 6).

Two blueprints live here because they share a lot of code:

    processor  /processor/...   works the queue: start review, approve,
                                request an amendment, mark completed
    admin      /admin/...       read-only oversight: all orders, history,
                                users and reports

Both show an order with the same partial templates the dealer uses, so an
order looks the same to everyone. Only the buttons differ.
"""
import csv
import io
import os
from datetime import datetime, timedelta

from flask import (Blueprint, Response, abort, flash, g, redirect,
                   render_template, request, send_file, url_for)

from . import constants as C
from .auth import login_required
from .db import get_db
from .helpers import load_order_bundle, upload_root

processor = Blueprint("processor", __name__, url_prefix="/processor")
admin = Blueprint("admin", __name__, url_prefix="/admin")

TABS = ["overview", "customer", "subscription", "documents", "activity"]
MIME = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}

LIST_SQL = ("SELECT o.*, u.name AS dealer_name FROM orders o "
            "JOIN users u ON u.id = o.dealer_id")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ----------------------------------------------------------- shared tools ----
def _order_or_404(order_number, include_drafts=False):
    """Staff can open any submitted order. Drafts belong to the dealer."""
    row = get_db().execute(LIST_SQL + " WHERE o.order_number = ?", (order_number,)).fetchone()
    if row is None or (row["status"] == "Draft" and not include_drafts):
        abort(404)
    return row


def _toast(kind, title, body=""):
    flash([title, body], kind)


def _event(db, order, title, status, note=None, category=None):
    db.execute(
        """INSERT INTO order_events (order_id, title, status, actor, actor_role, note, category, ts)
           VALUES (?, ?, ?, ?, 'Processor', ?, ?, ?)""",
        (order["id"], title, status, g.user["name"], note, category, now_str()))


def _filtered_orders(statuses=None, include_dealer_filter=False):
    """Orders list with the usual filters (q, status, type, dealer)."""
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    order_type = request.args.get("type", "")
    dealer = request.args.get("dealer", "")
    sql = LIST_SQL + " WHERE o.status != 'Draft'"
    params = []
    if statuses:
        sql += " AND o.status IN (%s)" % ",".join("?" * len(statuses))
        params += statuses
    if q:
        sql += " AND (o.order_number LIKE ? OR o.company_name LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if status in C.STATUSES:
        sql += " AND o.status = ?"
        params.append(status)
    if order_type in C.ORDER_TYPES:
        sql += " AND o.order_type = ?"
        params.append(order_type)
    if include_dealer_filter and dealer.isdigit():
        sql += " AND o.dealer_id = ?"
        params.append(int(dealer))
    return sql, params, dict(q=q, status=status, order_type=order_type, dealer=dealer)


def _detail_context(order, endpoint, can_act):
    tab = request.args.get("tab", "overview")
    if tab not in TABS:
        tab = "overview"
    return dict(order=order, b=load_order_bundle(get_db(), order), tab=tab,
                detail_endpoint=endpoint, can_act=can_act)


def _send_document(order_number, doc_id):
    order = _order_or_404(order_number)
    doc = get_db().execute("SELECT * FROM documents WHERE id = ? AND order_id = ?",
                           (doc_id, order["id"])).fetchone()
    if doc is None or not doc["stored_name"]:
        abort(404)
    path = os.path.join(upload_root(), order_number, doc["stored_name"])
    if not os.path.isfile(path):
        abort(404)
    ext = doc["stored_name"].rsplit(".", 1)[-1].lower()
    resp = send_file(path, mimetype=MIME.get(ext, "application/octet-stream"),
                     as_attachment=(ext == "xlsx"), download_name=doc["filename"])
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


def next_reference_id(db):
    """REF-MVP-78421 is the highest -> REF-MVP-78422."""
    top = 77000
    for r in db.execute("SELECT reference_id FROM orders WHERE reference_id IS NOT NULL"):
        try:
            top = max(top, int(r[0].rsplit("-", 1)[1]))
        except (ValueError, IndexError):
            pass
    return f"REF-MVP-{top + 1}"


# ================================================================ PROCESSOR ====
@processor.route("")
@login_required("processor")
def dashboard():
    db = get_db()
    counts = {s: 0 for s in C.STATUSES}
    for r in db.execute("SELECT status, COUNT(*) c FROM orders GROUP BY status"):
        counts[r["status"]] = r["c"]
    waiting = db.execute(LIST_SQL + " WHERE o.status IN ('Submitted', 'Under Review') "
                         "ORDER BY CASE o.status WHEN 'Submitted' THEN 0 ELSE 1 END, "
                         "o.submitted_at LIMIT 6").fetchall()
    mine = db.execute(
        "SELECT COUNT(*) FROM order_events WHERE actor = ? AND ts >= ?",
        (g.user["name"], datetime.now().strftime("%Y-%m-%d 00:00"))).fetchone()[0]
    hour = datetime.now().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
    return render_template("staff/processor_dashboard.html", active="dashboard",
                           counts=counts, waiting=waiting, mine=mine,
                           greeting=greeting, first_name=g.user["short_name"])


@processor.route("/queue")
@login_required("processor")
def queue():
    sql, params, f = _filtered_orders(statuses=["Submitted", "Under Review"])
    rows = get_db().execute(
        sql + " ORDER BY CASE o.status WHEN 'Submitted' THEN 0 ELSE 1 END, o.submitted_at",
        params).fetchall()
    return render_template("staff/orders.html", active="queue", orders=rows, f=f,
                           title="Work Queue", subtitle="Orders waiting for review, oldest first.",
                           endpoint="processor.queue", detail_endpoint="processor.order_detail",
                           status_choices=["Submitted", "Under Review"], show_dealer=True)


@processor.route("/orders")
@login_required("processor")
def all_orders():
    sql, params, f = _filtered_orders()
    rows = get_db().execute(sql + " ORDER BY o.updated_at DESC", params).fetchall()
    return render_template("staff/orders.html", active="all", orders=rows, f=f,
                           title="All Orders", subtitle="Every submitted order across all dealers.",
                           endpoint="processor.all_orders", detail_endpoint="processor.order_detail",
                           status_choices=[s for s in C.STATUSES if s != "Draft"], show_dealer=True)


@processor.route("/orders/<order_number>")
@login_required("processor")
def order_detail(order_number):
    order = _order_or_404(order_number)
    ctx = _detail_context(order, "processor.order_detail", can_act=True)
    ctx.update(active="queue", amend_categories=C.AMEND_CATEGORIES,
               amend_sections=list(C.AMEND_SECTIONS),
               default_due=(datetime.now() + timedelta(days=C.AMEND_DAYS)).strftime("%Y-%m-%d"))
    return render_template("staff/order_detail.html", **ctx)


@processor.route("/orders/<order_number>/documents/<int:doc_id>")
@login_required("processor")
def document_preview(order_number, doc_id):
    return _send_document(order_number, doc_id)


def _back(order_number):
    return redirect(url_for("processor.order_detail", order_number=order_number))


@processor.route("/orders/<order_number>/start", methods=["POST"])
@login_required("processor")
def start_review(order_number):
    db, order = get_db(), _order_or_404(order_number)
    if order["status"] != "Submitted":
        _toast("error", "Cannot start review", f"This order is {order['status']}.")
        return _back(order_number)
    title = "Review restarted" if order["submissions"] > 1 else "Review started"
    db.execute("UPDATE orders SET status = 'Under Review', updated_at = ? WHERE id = ?",
               (now_str(), order["id"]))
    _event(db, order, title, "Under Review")
    db.commit()
    _toast("success", title, order_number)
    return _back(order_number)


@processor.route("/orders/<order_number>/approve", methods=["POST"])
@login_required("processor")
def approve(order_number):
    db, order = get_db(), _order_or_404(order_number)
    if order["status"] != "Under Review":
        _toast("error", "Cannot approve", "Only orders Under Review can be approved.")
        return _back(order_number)
    b = load_order_bundle(db, order)
    if b["required_uploaded"] != b["required_total"]:
        _toast("error", "Documents missing",
               "Request an amendment: required documents are not uploaded.")
        return _back(order_number)
    note = request.form.get("note", "").strip()[:300] or "All documents verified."
    ref, ts = next_reference_id(db), now_str()
    db.execute("UPDATE orders SET status = 'Approved', reference_id = ?, approved_by = ?, "
               "approved_at = ?, updated_at = ? WHERE id = ?",
               (ref, g.user["name"], ts, ts, order["id"]))
    _event(db, order, "Order approved", "Approved", note)
    _event(db, order, "Reference ID added", "Approved", f"Reference ID {ref} recorded.")
    db.commit()
    _toast("success", "Order approved", f"Reference ID {ref}")
    return _back(order_number)


@processor.route("/orders/<order_number>/amend", methods=["POST"])
@login_required("processor")
def amend(order_number):
    db, order = get_db(), _order_or_404(order_number)
    if order["status"] != "Under Review":
        _toast("error", "Cannot request amendment", "Only orders Under Review can be returned.")
        return _back(order_number)
    category = request.form.get("category", "")
    sections = [s for s in request.form.getlist("sections") if s in C.AMEND_SECTIONS]
    reason = request.form.get("reason", "").strip()
    due = request.form.get("due", "").strip()
    problems = []
    if category not in C.AMEND_CATEGORIES:
        problems.append("choose a category")
    if not sections:
        problems.append("select at least one section")
    if len(reason) < 10:
        problems.append("write a reason of at least 10 characters")
    if len(reason) > 500:
        problems.append("keep the reason under 500 characters")
    try:
        datetime.strptime(due, "%Y-%m-%d")
    except ValueError:
        due = (datetime.now() + timedelta(days=C.AMEND_DAYS)).strftime("%Y-%m-%d")
    if problems:
        _toast("error", "Amendment not sent", "Please " + ", ".join(problems) + ".")
        return _back(order_number)
    ts = now_str()
    db.execute(
        "UPDATE orders SET status = 'Amendment Required', amendment_cycles = amendment_cycles + 1, "
        "amendment_category = ?, amendment_reason = ?, amendment_sections = ?, amendment_by = ?, "
        "amendment_at = ?, amendment_due = ?, updated_at = ? WHERE id = ?",
        (category, reason, ",".join(sections), g.user["name"], ts, due, ts, order["id"]))
    _event(db, order, "Amendment requested", "Amendment Required", reason, category=category)
    db.commit()
    _toast("success", "Returned to dealer", f"{order_number} now needs correction.")
    return _back(order_number)


@processor.route("/orders/<order_number>/complete", methods=["POST"])
@login_required("processor")
def complete(order_number):
    db, order = get_db(), _order_or_404(order_number)
    if order["status"] != "Approved":
        _toast("error", "Cannot complete", "Only Approved orders can be completed.")
        return _back(order_number)
    note = request.form.get("note", "").strip()[:300] or "Activation confirmed for all lines."
    ts = now_str()
    db.execute("UPDATE orders SET status = 'Completed', completed_by = ?, completed_at = ?, "
               "updated_at = ? WHERE id = ?", (g.user["name"], ts, ts, order["id"]))
    _event(db, order, "Order marked completed", "Completed", note)
    db.commit()
    _toast("success", "Order completed", order_number)
    return _back(order_number)


@processor.route("/help")
@login_required("processor")
def help():
    return render_template("staff/processor_help.html", active="help")


# ==================================================================== ADMIN ====
@admin.route("")
@login_required("admin")
def overview():
    db = get_db()
    counts = {s: 0 for s in C.STATUSES}
    for r in db.execute("SELECT status, COUNT(*) c FROM orders GROUP BY status"):
        counts[r["status"]] = r["c"]
    recent = db.execute(
        "SELECT e.*, o.order_number, o.company_name FROM order_events e "
        "JOIN orders o ON o.id = e.order_id ORDER BY e.ts DESC, e.id DESC LIMIT 8").fetchall()
    by_dealer = db.execute(
        "SELECT u.name, COUNT(o.id) total, "
        "SUM(o.status = 'Amendment Required') amend, SUM(o.status = 'Draft') drafts "
        "FROM users u LEFT JOIN orders o ON o.dealer_id = u.id "
        "WHERE u.role = 'dealer' GROUP BY u.id ORDER BY total DESC").fetchall()
    stuck = db.execute(LIST_SQL + " WHERE o.status = 'Submitted' ORDER BY o.submitted_at LIMIT 5").fetchall()
    return render_template("staff/admin_overview.html", active="overview", counts=counts,
                           total=sum(counts.values()), recent=recent,
                           by_dealer=by_dealer, stuck=stuck)


@admin.route("/orders")
@login_required("admin")
def all_orders():
    sql, params, f = _filtered_orders(include_dealer_filter=True)
    rows = get_db().execute(sql + " ORDER BY o.updated_at DESC", params).fetchall()
    dealers = get_db().execute("SELECT id, name FROM users WHERE role = 'dealer' ORDER BY name").fetchall()
    return render_template("staff/orders.html", active="all", orders=rows, f=f,
                           title="All Orders", subtitle="Read-only view of every submitted order.",
                           endpoint="admin.all_orders", detail_endpoint="admin.order_detail",
                           status_choices=[s for s in C.STATUSES if s != "Draft"],
                           show_dealer=True, dealers=dealers)


@admin.route("/orders/<order_number>")
@login_required("admin")
def order_detail(order_number):
    order = _order_or_404(order_number)
    ctx = _detail_context(order, "admin.order_detail", can_act=False)
    ctx.update(active="all")
    return render_template("staff/order_detail.html", **ctx)


@admin.route("/orders/<order_number>/documents/<int:doc_id>")
@login_required("admin")
def document_preview(order_number, doc_id):
    return _send_document(order_number, doc_id)


@admin.route("/history")
@login_required("admin")
def history():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    role = request.args.get("role", "")
    sql = ("SELECT e.*, o.order_number, o.company_name FROM order_events e "
           "JOIN orders o ON o.id = e.order_id WHERE 1 = 1")
    params = []
    if q:
        sql += " AND (o.order_number LIKE ? OR e.actor LIKE ? OR e.title LIKE ?)"
        params += [f"%{q}%"] * 3
    if status in C.STATUSES:
        sql += " AND e.status = ?"
        params.append(status)
    if role in ("Dealer", "Processor", "Admin"):
        sql += " AND e.actor_role = ?"
        params.append(role)
    rows = get_db().execute(sql + " ORDER BY e.ts DESC, e.id DESC LIMIT 300", params).fetchall()
    return render_template("staff/history.html", active="history", events=rows,
                           q=q, status=status, role=role)


@admin.route("/users")
@login_required("admin")
def users():
    rows = get_db().execute(
        "SELECT u.*, (SELECT COUNT(*) FROM orders o WHERE o.dealer_id = u.id) AS order_count "
        "FROM users u ORDER BY CASE u.role WHEN 'admin' THEN 0 WHEN 'processor' THEN 1 ELSE 2 END, u.name"
    ).fetchall()
    return render_template("staff/users.html", active="users", users=rows)


def _report_data():
    db = get_db()
    by_status = {s: 0 for s in C.STATUSES}
    for r in db.execute("SELECT status, COUNT(*) c FROM orders GROUP BY status"):
        by_status[r["status"]] = r["c"]
    by_type = db.execute("SELECT COALESCE(order_type, 'Not chosen') t, COUNT(*) c FROM orders "
                         "GROUP BY t ORDER BY c DESC").fetchall()
    submitted = db.execute("SELECT COUNT(*) FROM orders WHERE status != 'Draft'").fetchone()[0]
    amended = db.execute("SELECT COUNT(*) FROM orders WHERE amendment_cycles > 0").fetchone()[0]
    done = db.execute("SELECT COUNT(*) FROM orders WHERE status IN ('Approved','Completed')").fetchone()[0]
    value = db.execute(
        "SELECT COALESCE(SUM(l.num_lines * l.monthly), 0) FROM order_lines l "
        "JOIN orders o ON o.id = l.order_id WHERE o.status IN ('Approved', 'Completed')").fetchone()[0]
    return dict(by_status=by_status, by_type=by_type, submitted=submitted,
                amended=amended, done=done, value=value,
                amend_rate=round(amended / submitted * 100) if submitted else 0,
                approve_rate=round(done / submitted * 100) if submitted else 0)


@admin.route("/reports")
@login_required("admin")
def reports():
    return render_template("staff/reports.html", active="reports", r=_report_data())


@admin.route("/reports/orders.csv")
@login_required("admin")
def export_csv():
    rows = get_db().execute(LIST_SQL + " ORDER BY o.order_number").fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Order number", "Status", "Order type", "Company", "Dealer", "Created",
                "Submitted", "Submissions", "Amendment cycles", "Reference ID"])
    for o in rows:
        # A cell starting with = + - @ can run as a formula in Excel: neutralise it.
        def safe(v):
            v = "" if v is None else str(v)
            return "'" + v if v[:1] in "=+-@" else v
        w.writerow([safe(x) for x in (o["order_number"], o["status"], o["order_type"],
                                      o["company_name"], o["dealer_name"], o["created_at"],
                                      o["submitted_at"], o["submissions"], o["amendment_cycles"],
                                      o["reference_id"])])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=orders.csv"})
