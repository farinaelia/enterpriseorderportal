"""The Create Order wizard (Stage 3).

Six steps, one URL pattern:

    /dealer/orders/new                    start a new order (step 1)
    /dealer/orders/ORD-2026-00131/edit?step=3

Buttons on a step send an `action` value with the form:

    save        "Save Draft"   - lenient save, stay on this step
    next        "Continue"     - validate, save, go to the next step
    back        "Back"         - save leniently, go to the previous step
    add_line / dup_line:2 / del_line:2   - change the subscription lines

Documents (step 4) use their own small routes because they upload files.
"""
import os
import uuid

from flask import (Blueprint, abort, flash, g, redirect,
                   render_template, request, url_for)

from . import constants as C
from . import forms
from .auth import login_required
from .db import get_db
from .dealer import _my_order_or_404
from .helpers import load_order_bundle, upload_root

bp = Blueprint("wizard", __name__, url_prefix="/dealer/orders")

LAST_STEP = 6
# Statuses in which the dealer may change the order.
EDITABLE = ("Draft", "Amendment Required")


# ----------------------------------------------------------- small tools ----
def _step_from_request():
    try:
        step = int(request.values.get("step", 1))
    except ValueError:
        step = 1
    return min(max(step, 1), LAST_STEP)


def _event(db, order_id, title, status, note=None):
    db.execute(
        """INSERT INTO order_events (order_id, title, status, actor, actor_role, note, ts)
           VALUES (?, ?, ?, ?, 'Dealer', ?, ?)""",
        (order_id, title, status, g.user["name"], note, forms.now_str()))


def _toast(kind, title, body=""):
    flash([title, body], kind)


def _create_draft(db):
    """Insert an empty draft and return it."""
    ts = forms.now_str()
    number = forms.next_order_number(db)
    db.execute(
        """INSERT INTO orders (order_number, dealer_id, status, created_at, updated_at,
                               partner_name, submissions)
           VALUES (?, ?, 'Draft', ?, ?, ?, 0)""",
        (number, g.user["id"], ts, ts, g.user["team"] or g.user["name"]))
    order = db.execute("SELECT * FROM orders WHERE order_number = ?", (number,)).fetchone()
    _event(db, order["id"], "Draft created", "Draft")
    return order


def _stepper(db, order):
    """For each step: 'done' when its data is valid. Used to colour the stepper."""
    if order is None:
        return {n: False for n, _ in C.WIZARD_STEPS}
    errs = forms.step_errors(db, order)
    b = load_order_bundle(db, order)
    done = {n: not errs.get(n) for n in (1, 2, 3, 5)}
    done[4] = b["required_uploaded"] == b["required_total"]
    done[6] = False
    return done


def _render_step(db, order, step, values, errors, banner=None):
    """Draw one step. `values` are the field values, `errors` the messages."""
    done = _stepper(db, order)
    ctx = dict(
        active="create", order=order, step=step, values=values, errors=errors,
        done=done, banner=banner,
        step_title=dict(C.WIZARD_STEPS)[step],
    )
    if order is not None:
        ctx["order_type"] = (values.get("order_type") if step == 1 else order["order_type"])
    else:
        ctx["order_type"] = values.get("order_type")

    if step == 3:
        ctx["plans"] = C.plans_for(ctx["order_type"])
    if order is not None and order["status"] == "Amendment Required":
        ctx["amend_sections"] = forms.split_sections(order["amendment_sections"])
        ctx["amend_steps"] = {C.AMEND_SECTIONS[x] for x in ctx["amend_sections"]}
    if step in (4, 6) and order is not None:
        ctx["b"] = load_order_bundle(db, order)
    if step == 4 and order is not None:
        # One slot per required document, then an optional "other" slot.
        by_key = {d["doc_key"]: d for d in ctx["b"]["docs"]}
        required = C.required_doc_keys(order["customer_type"], order["order_type"])
        keys = required + [k for k in ("other",) if k not in required]
        ctx["slots"] = [dict(key=k, label=C.DOC_LABELS[k], required=k in required,
                             file=by_key.get(k)) for k in keys]
    if step == 6 and order is not None:
        all_errors = forms.step_errors(db, order)
        ctx["step_errors_all"] = all_errors
        ctx["ready"] = (not any(all_errors.values())
                        and ctx["b"]["required_uploaded"] == ctx["b"]["required_total"])
        ctx["tab"] = "review"
    return render_template("dealer/wizard.html", **ctx)


# ------------------------------------------------------- start / edit ----
@bp.route("/new", methods=["GET", "POST"])
@login_required("dealer")
def create():
    """A brand-new order. Nothing is stored until the first Save/Continue."""
    if request.method == "GET":
        values = {"order_type": "", "registration_type": ""}
        return _render_step(get_db(), None, 1, values, {})

    db = get_db()
    values = forms.parse_step(1, request.form)
    action = request.form.get("action", "next")
    errors = forms.validate_step(1, values)
    if action == "next" and errors:
        return _render_step(db, None, 1, values, errors,
                            banner="Please fix the highlighted fields before continuing.")
    order = _create_draft(db)
    forms.save_step(db, order, 1, values)
    db.commit()
    if action == "next":
        return redirect(url_for("wizard.edit", order_number=order["order_number"], step=2))
    _toast("success", "Draft saved", f"{order['order_number']} was created.")
    return redirect(url_for("wizard.edit", order_number=order["order_number"], step=1))


@bp.route("/<order_number>/edit", methods=["GET", "POST"])
@login_required("dealer")
def edit(order_number):
    db = get_db()
    order = _my_order_or_404(order_number)

    if order["status"] not in EDITABLE:
        _toast("error", "This order is locked",
               f"{order_number} is {order['status']} and can no longer be edited.")
        return redirect(url_for("dealer.order_detail", order_number=order_number))

    # Coming from "Edit and Resubmit": jump straight to the first flagged section.
    if (request.method == "GET" and "step" not in request.args
            and order["status"] == "Amendment Required"):
        flagged = [C.AMEND_SECTIONS[x] for x in forms.split_sections(order["amendment_sections"])]
        if flagged:
            return redirect(url_for("wizard.edit", order_number=order_number, step=min(flagged)))

    step = _step_from_request()

    if request.method == "GET":
        values = forms.load_values(db, order, step) if step != 4 and step != 6 else {}
        return _render_step(db, order, step, values, {})

    # ---------------------------------------------------------- POST ----
    action = request.form.get("action", "save")
    values = forms.parse_step(step, request.form)

    # Add / duplicate / delete a subscription line (step 3 only)
    if step == 3 and (action == "add_line" or action.startswith(("dup_line", "del_line"))):
        lines = values["lines"]
        if action == "add_line":
            if len(lines) < 20:
                lines.append(forms.blank_line(order["order_type"], order["registration_type"]))
        else:
            kind, _, idx = action.partition(":")
            i = forms.to_int(idx, -1)
            if 0 <= i < len(lines):
                if kind == "dup_line" and len(lines) < 20:
                    lines.insert(i + 1, dict(lines[i], addons=list(lines[i]["addons"]),
                                             services=list(lines[i]["services"])))
                elif kind == "del_line" and len(lines) > 1:
                    lines.pop(i)
        forms.save_step(db, order, 3, values)
        db.commit()
        return _render_step(db, order, 3, values, {})

    # Steps 4 and 6 hold no form fields; they only navigate.
    if step in (4, 6):
        return _navigate(db, order, step, action)

    errors = forms.validate_step(step, values, order)

    if action == "next":
        if errors:
            return _render_step(db, order, step, values, errors,
                                banner="Please fix the highlighted fields before continuing.")
        forms.save_step(db, order, step, values)
        db.commit()
        return redirect(url_for("wizard.edit", order_number=order_number, step=step + 1))

    # "save" and "back" are lenient: keep whatever was typed.
    forms.save_step(db, order, step, values)
    db.commit()
    if action == "back":
        return redirect(url_for("wizard.edit", order_number=order_number, step=max(step - 1, 1)))
    _toast("success", "Draft saved", f"{order_number} was saved at {forms.now_str()[-5:]}.")
    # Redirecting after a POST stops "resubmit form?" warnings on refresh.
    return redirect(url_for("wizard.edit", order_number=order_number, step=step))


def _navigate(db, order, step, action):
    number = order["order_number"]
    if action == "back":
        return redirect(url_for("wizard.edit", order_number=number, step=step - 1))
    if action == "next" and step == 4:
        b = load_order_bundle(db, order)
        if b["required_uploaded"] != b["required_total"]:
            return _render_step(db, order, 4, {}, {},
                                banner="Upload every required document before continuing.")
        return redirect(url_for("wizard.edit", order_number=number, step=5))
    return redirect(url_for("wizard.edit", order_number=number, step=step))


# ------------------------------------------------------------ documents ----
MAGIC = {
    "pdf": (b"%PDF",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "xlsx": (b"PK\x03\x04",),
}


def upload_dir(number):
    path = os.path.join(upload_root(), number)
    os.makedirs(path, exist_ok=True)
    return path


def _editable_order_or_403(order_number):
    order = _my_order_or_404(order_number)
    if order["status"] not in EDITABLE:
        abort(403)
    return order


def _store_document(db, order, doc_key, filename, data):
    """Save bytes to disk and record the document (replacing any older file)."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    file_type = "JPG" if ext in ("jpg", "jpeg") else ext.upper()
    stored = f"{doc_key}-{uuid.uuid4().hex[:8]}.{ext}"
    with open(os.path.join(upload_dir(order["order_number"]), stored), "wb") as fh:
        fh.write(data)
    old = db.execute("SELECT * FROM documents WHERE order_id = ? AND doc_key = ?",
                     (order["id"], doc_key)).fetchall()
    for row in old:
        _delete_file(order["order_number"], row["stored_name"])
        db.execute("DELETE FROM documents WHERE id = ?", (row["id"],))
    db.execute(
        """INSERT INTO documents (order_id, doc_key, filename, file_type, size_mb, uploaded_at, stored_name)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (order["id"], doc_key, filename[:120], file_type,
         max(round(len(data) / 1048576, 2), 0.01), forms.now_str(), stored))
    db.execute("UPDATE orders SET updated_at = ? WHERE id = ?", (forms.now_str(), order["id"]))
    db.commit()


def _delete_file(number, stored_name):
    if stored_name:
        try:
            os.remove(os.path.join(upload_dir(number), stored_name))
        except OSError:
            pass


def _back_to_docs(order_number):
    return redirect(url_for("wizard.edit", order_number=order_number, step=4))


@bp.route("/<order_number>/documents/upload", methods=["POST"])
@login_required("dealer")
def upload(order_number):
    order = _editable_order_or_403(order_number)
    doc_key = request.form.get("doc_key", "")
    if doc_key not in C.DOC_LABELS:
        abort(400)
    file = request.files.get("file")
    if file is None or not file.filename:
        _toast("error", "No file chosen", "Choose a file to upload.")
        return _back_to_docs(order_number)

    name = os.path.basename(file.filename.replace("\\", "/"))
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in C.ALLOWED_UPLOAD_EXTENSIONS:
        _toast("error", "File type not allowed",
               "Upload a PDF, JPG, PNG or XLSX file.")
        return _back_to_docs(order_number)

    data = file.read(C.MAX_UPLOAD_MB * 1048576 + 1)
    if len(data) > C.MAX_UPLOAD_MB * 1048576:
        _toast("error", "File too large", f"The maximum size is {C.MAX_UPLOAD_MB} MB.")
        return _back_to_docs(order_number)
    if not data:
        _toast("error", "Empty file", "That file has no content.")
        return _back_to_docs(order_number)
    if not any(data.startswith(m) for m in MAGIC[ext]):
        # The extension says one thing, the file's first bytes say another.
        _toast("error", "File does not match its type",
               f"This does not look like a real .{ext} file.")
        return _back_to_docs(order_number)

    _store_document(get_db(), order, doc_key, name, data)
    _toast("success", "Document uploaded", f"{C.DOC_LABELS[doc_key]}: {name}")
    return _back_to_docs(order_number)


def make_sample_pdf(title):
    """Build a tiny but valid one-page PDF (no extra library needed)."""
    safe = "".join(ch for ch in title if ch.isalnum() or ch in " -_.")[:60]
    stream = f"BT /F1 18 Tf 72 720 Tm (SAMPLE - {safe}) Tj ET\n" \
             f"BT /F1 11 Tf 72 696 Tm (Prototype placeholder document. Fictional data.) Tj ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


@bp.route("/<order_number>/documents/sample", methods=["POST"])
@login_required("dealer")
def sample(order_number):
    """Prototype shortcut: attach a generated sample PDF to a document slot."""
    order = _editable_order_or_403(order_number)
    doc_key = request.form.get("doc_key", "")
    if doc_key not in C.DOC_LABELS:
        abort(400)
    label = C.DOC_LABELS[doc_key]
    filename = label.lower().replace(" ", "_") + "_sample.pdf"
    _store_document(get_db(), order, doc_key, filename, make_sample_pdf(label))
    _toast("success", "Sample document attached", label)
    return _back_to_docs(order_number)


@bp.route("/<order_number>/documents/<int:doc_id>/remove", methods=["POST"])
@login_required("dealer")
def remove(order_number, doc_id):
    order = _editable_order_or_403(order_number)
    db = get_db()
    doc = db.execute("SELECT * FROM documents WHERE id = ? AND order_id = ?",
                     (doc_id, order["id"])).fetchone()
    if doc is None:
        abort(404)
    _delete_file(order_number, doc["stored_name"])
    db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    db.execute("UPDATE orders SET updated_at = ? WHERE id = ?", (forms.now_str(), order["id"]))
    db.commit()
    _toast("success", "Document removed", C.DOC_LABELS[doc["doc_key"]])
    return _back_to_docs(order_number)


# --------------------------------------------------------------- submit ----
@bp.route("/<order_number>/submit", methods=["POST"])
@login_required("dealer")
def submit(order_number):
    """Submit a draft, or resubmit an order returned for amendment."""
    db = get_db()
    order = _editable_order_or_403(order_number)
    resubmit = order["status"] == "Amendment Required"
    review = url_for("wizard.edit", order_number=order_number, step=6)

    if request.form.get("declaration") != "on":
        _toast("error", "Declaration required",
               "Tick the declaration box before submitting.")
        return redirect(review)

    response = request.form.get("response", "").strip()
    if resubmit and (len(response) < 5 or len(response) > 500):
        _toast("error", "Response required",
               "Tell the processor what you changed (5 to 500 characters).")
        return redirect(review)

    problems = forms.step_errors(db, order)
    b = load_order_bundle(db, order)
    if any(problems.values()) or b["required_uploaded"] != b["required_total"]:
        _toast("error", "Order is not ready",
               "Complete every step and upload all required documents first.")
        return redirect(review)

    ts = forms.now_str()
    db.execute(
        "UPDATE orders SET status = 'Submitted', submissions = submissions + 1, "
        "submitted_at = ?, updated_at = ? WHERE id = ?", (ts, ts, order["id"]))
    if resubmit:
        _event(db, order["id"], "Order resubmitted", "Submitted", f"Dealer response: {response}")
    else:
        _event(db, order["id"], "Order submitted", "Submitted",
               "Submitted by the dealer for processing.")
    db.commit()
    return redirect(url_for("wizard.submitted", order_number=order_number))


@bp.route("/<order_number>/submitted")
@login_required("dealer")
def submitted(order_number):
    order = _my_order_or_404(order_number)
    if order["status"] == "Draft":
        return redirect(url_for("wizard.edit", order_number=order_number, step=6))
    return render_template("dealer/submitted.html", active="orders", order=order)
