"""Sign in / sign out and the "who is logged in?" logic.

PROTOTYPE NOTE: the password is NOT checked. Any password works for a known
email address. A real system must store hashed passwords
(werkzeug.security.generate_password_hash / check_password_hash).
"""
import functools

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, session, url_for)

from .db import get_db

bp = Blueprint("auth", __name__)

# Where each role lands after signing in.
HOME_ENDPOINT = {
    "dealer": "dealer.dashboard",
    "processor": "processor.dashboard",
    "admin": "admin.overview",
}


@bp.before_app_request
def load_logged_in_user():
    """Runs before every request: put the signed-in user (or None) in g.user."""
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def login_required(*roles):
    """Decorator: only allow signed-in users, optionally only certain roles.

    Usage:
        @bp.route("/dealer")
        @login_required("dealer")
        def dashboard(): ...
    """
    def decorator(view):
        @functools.wraps(view)
        def wrapped(**kwargs):
            if g.user is None:
                return redirect(url_for("auth.login"))
            if roles and g.user["role"] not in roles:
                abort(403)  # signed in, but this page is for another role
            return view(**kwargs)
        return wrapped
    return decorator


@bp.route("/")
def index():
    if g.user:
        return redirect(url_for(HOME_ENDPOINT[g.user["role"]]))
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = get_db().execute(
            "SELECT * FROM users WHERE email = ? AND status = 'Active'", (email,)
        ).fetchone()
        if user is None:
            flash("We could not find an active account for that email address.")
        else:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for(HOME_ENDPOINT[user["role"]]))
    return render_template("login.html")


@bp.route("/login/as/<role>", methods=("POST",))
def login_as(role):
    """The 'Prototype access' buttons: sign in as a demo user of that role."""
    demo_email = {
        "dealer": "syufaiq@example.com",
        "processor": "farina.e@example.com",
        "admin": "admin@example.com",
    }.get(role)
    if demo_email is None:
        abort(404)
    user = get_db().execute(
        "SELECT * FROM users WHERE email = ?", (demo_email,)).fetchone()
    session.clear()
    session["user_id"] = user["id"]
    return redirect(url_for(HOME_ENDPOINT[role]))


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
