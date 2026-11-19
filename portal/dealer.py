"""Dealer pages: dashboard, My Orders, order detail, help.

A *blueprint* is a group of related routes. Every URL here starts with
/dealer (see url_prefix). Each function below is a "view": it reads from the
database, then hands the data to an HTML template to display.
"""
import os
from datetime import datetime, timedelta

from flask import (Blueprint, abort, g, redirect, render_template,
                   request, send_file, url_for)

from . import constants as C
from .auth import login_required
from .db import get_db
from .helpers import load_order_bundle, upload_root

bp = Blueprint("dealer", __name__, url_prefix="/dealer")

TABS = ["overview", "customer", "subscription", "documents", "activity"]


def _my_order_or_404(order_number):
    """Fetch an order, but ONLY if it belongs to the signed-in dealer.

    This is the key security rule of the dealer area: a dealer must never be
    able to open another dealer's order by typing its number into the URL.
    """
    order = get_db().execute(
        "SELECT * FROM orders WHERE order_number = ? AND dealer_id = ?",
        (order_number, g.user["id"]),
    ).fetchone()
    if order is None:
        abort(404)
    return order


# ----------------------------------------------------------- dashboard ----
@bp.route("")
@login_required("dealer")
def dashboard():
    db = get_db()

    # Orders needing action come first, then everything else, newest first.
    orders = db.execute(
        """SELECT * FROM orders WHERE dealer_id = ?
           ORDER BY CASE status WHEN 'Amendment Required' THEN 0
                                WHEN 'Draft' THEN 1 ELSE 2 END,
                    updated_at DESC""",
        (g.user["id"],),
    ).fetchall()

    drafts = [o for o in orders if o["status"] == "Draft"]
    amendments = [o for o in orders if o["status"] == "Amendment Required"]
    action_orders = amendments + drafts

    hour = datetime.now().hour
    greeting = ("Good morning" if hour < 12
                else "Good afternoon" if hour < 18 else "Good evening")

    return render_template(
        "dealer/dashboard.html",
        active="dashboard",
        orders=orders,
        drafts=drafts,
        amendments=amendments,
        action_orders=action_orders,
        greeting=greeting,
        first_name=g.user["short_name"],
    )


# ----------------------------------------------------------- My Orders ----
@bp.route("/orders")
@login_required("dealer")
def orders():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    order_type = request.args.get("type", "")
    date_range = request.args.get("date", "")

    # Build the SQL step by step, adding one condition per active filter.
    # The "?" placeholders keep user input out of the SQL text (this prevents
    # SQL injection) - always do it this way.
    sql = "SELECT * FROM orders WHERE dealer_id = ?"
    params = [g.user["id"]]
    if q:
        sql += " AND (order_number LIKE ? OR company_name LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if status in C.STATUSES:
        sql += " AND status = ?"
        params.append(status)
    if order_type in C.ORDER_TYPES:
        sql += " AND order_type = ?"
        params.append(order_type)
    # Date filter, relative to the real current time.
    now = datetime.now()
    since = {
        "today": now.replace(hour=0, minute=0),
        "7": now - timedelta(days=7),
        "30": now - timedelta(days=30),
        "year": now.replace(month=1, day=1, hour=0, minute=0),
    }.get(date_range)
    if since:
        sql += " AND updated_at >= ?"
        params.append(since.strftime("%Y-%m-%d %H:%M"))
    sql += " ORDER BY updated_at DESC"

    rows = get_db().execute(sql, params).fetchall()
    return render_template(
        "dealer/orders.html", active="orders", orders=rows,
        q=q, status=status, order_type=order_type, date_range=date_range,
    )


@bp.route("/search")
@login_required("dealer")
def search():
    """The search box in the top bar sends people to My Orders, filtered."""
    return redirect(url_for("dealer.orders", q=request.args.get("q", "")))


# --------------------------------------------------------- order detail ----
@bp.route("/orders/<order_number>")
@login_required("dealer")
def order_detail(order_number):
    order = _my_order_or_404(order_number)
    tab = request.args.get("tab", "overview")
    if tab not in TABS:
        tab = "overview"
    bundle = load_order_bundle(get_db(), order)
    return render_template(
        "dealer/order_detail.html", active="orders",
        order=order, b=bundle, tab=tab,
    )


# ------------------------------------------------- document preview ----
MIME = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


@bp.route("/orders/<order_number>/documents/<int:doc_id>")
@login_required("dealer")
def document_preview(order_number, doc_id):
    """Show an uploaded file. Only the owning dealer can open it."""
    order = _my_order_or_404(order_number)
    doc = get_db().execute("SELECT * FROM documents WHERE id = ? AND order_id = ?",
                           (doc_id, order["id"])).fetchone()
    if doc is None or not doc["stored_name"]:
        abort(404)
    path = os.path.join(upload_root(), order_number, doc["stored_name"])
    if not os.path.isfile(path):
        abort(404)
    ext = doc["stored_name"].rsplit(".", 1)[-1].lower()
    response = send_file(path, mimetype=MIME.get(ext, "application/octet-stream"),
                         as_attachment=(ext == "xlsx"), download_name=doc["filename"])
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# ----------------------------------------------------------------- help ----
@bp.route("/help")
@login_required("dealer")
def help():
    return render_template("dealer/help.html", active="help")
