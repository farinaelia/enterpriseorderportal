"""The portal package.

`create_app()` builds and configures the Flask application. Putting it in a
function (the "application factory" pattern) keeps things tidy and makes the
app easy to test.
"""
import os

from flask import Flask

from . import constants as C
from . import db, helpers


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    # SECRET_KEY signs the login cookie. For a prototype a fixed string is
    # fine; a real system would load a long random value from an environment
    # variable.
    # In Docker/production set the SECRET_KEY environment variable.
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True

    # Where the database and uploaded files live. Locally that is the
    # "instance" folder; in Docker we point PORTAL_DATA_DIR at a volume so
    # the data survives container restarts.
    data_dir = os.environ.get("PORTAL_DATA_DIR") or app.instance_path
    app.config["DATABASE"] = os.path.join(data_dir, "portal.sqlite")
    app.config["UPLOAD_FOLDER"] = os.path.join(data_dir, "uploads")

    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)

    # Database: opens/closes connections per request and creates + fills the
    # database file the very first time the app starts.
    db.init_app(app)

    # Jinja filters (money, date formatting, masking) and shared template data.
    helpers.init_app(app)

    # Blueprints = groups of related pages. Each later stage adds one.
    from . import auth, dealer, staff, wizard

    app.register_blueprint(auth.bp)
    app.register_blueprint(dealer.bp)
    app.register_blueprint(wizard.bp)
    app.register_blueprint(staff.processor)
    app.register_blueprint(staff.admin)

    # Uploads: Flask rejects a request bigger than this with a 413 error.
    app.config["MAX_CONTENT_LENGTH"] = (C.MAX_UPLOAD_MB + 2) * 1024 * 1024

    from flask import render_template

    @app.route("/healthz")
    def healthz():
        """Used by Docker to check the app is alive. No login needed."""
        return "ok"

    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def friendly_error(err):
        messages = {
            403: ("Not allowed", "You cannot do that with this order."),
            404: ("Page not found", "We could not find that page, or it is not yours to open."),
            413: ("File too large", f"Uploads can be at most {C.MAX_UPLOAD_MB} MB."),
        }
        title, text = messages[err.code]
        return render_template("errors.html", code=err.code, title=title, text=text), err.code

    return app
