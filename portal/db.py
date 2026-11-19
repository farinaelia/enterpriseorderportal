"""Database access (SQLite).

SQLite stores everything in one file, so there is nothing to install. We use
Python's built-in `sqlite3` module and plain SQL, which keeps the code easy to
read for a Python user.
"""
import os
import sqlite3

import click
from flask import current_app, g

# The tables. Read this once and you know what the portal stores.
SCHEMA = """
DROP TABLE IF EXISTS order_events;
DROP TABLE IF EXISTS documents;
DROP TABLE IF EXISTS order_lines;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    short_name TEXT NOT NULL,          -- how we greet them: 'Syufaiq'
    email   TEXT NOT NULL UNIQUE,
    role    TEXT NOT NULL,            -- 'dealer', 'processor' or 'admin'
    team    TEXT,
    region  TEXT,
    status  TEXT DEFAULT 'Active',
    last_active TEXT
);

CREATE TABLE orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number        TEXT NOT NULL UNIQUE,      -- e.g. ORD-2026-00128
    dealer_id           INTEGER NOT NULL REFERENCES users(id),
    status              TEXT NOT NULL,
    order_type          TEXT,                      -- e.g. Mobile & Broadband (empty in a new draft)
    registration_type   TEXT,                      -- e.g. New Connection
    customer_type       TEXT DEFAULT 'Corporate Account',  -- or Corporate Individual
    created_at          TEXT NOT NULL,             -- 'YYYY-MM-DD HH:MM'
    updated_at          TEXT NOT NULL,
    submitted_at        TEXT,
    reference_id        TEXT,
    submissions         INTEGER NOT NULL DEFAULT 0,
    amendment_cycles    INTEGER NOT NULL DEFAULT 0,
    other_requirements  TEXT,

    -- Customer information
    company_name        TEXT,                      -- empty until step 2 is filled in
    brn                 TEXT,                      -- new business registration no.
    old_brn             TEXT,
    tin                 TEXT,                      -- tax identification no.
    sst_no              TEXT,
    existing_account_no TEXT,
    address             TEXT,
    city                TEXT,
    postcode            TEXT,
    contact_name        TEXT,
    contact_id_no       TEXT,
    contact_designation TEXT,
    contact_phone       TEXT,
    contact_email       TEXT,

    -- Internal processing information
    partner_name        TEXT,
    channel             TEXT,
    region              TEXT,
    account_manager     TEXT,
    customer_category   TEXT,
    site_contact_name   TEXT,
    site_contact_number TEXT,
    device_model        TEXT,
    device_quantity     INTEGER,
    service_address     TEXT,
    installation_address TEXT,
    internal_notes      TEXT,

    -- Amendment (only filled when a Processor returns the order)
    amendment_category  TEXT,
    amendment_reason    TEXT,
    amendment_sections  TEXT,                      -- comma separated
    amendment_by        TEXT,
    amendment_at        TEXT,
    amendment_due       TEXT,

    -- Approval / completion
    approved_by         TEXT,
    approved_at         TEXT,
    completed_by        TEXT,
    completed_at        TEXT
);

CREATE TABLE order_lines (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id          INTEGER NOT NULL REFERENCES orders(id),
    position          INTEGER NOT NULL,
    registration_type TEXT NOT NULL,
    rate_plan         TEXT NOT NULL,
    addons            TEXT,                        -- comma separated
    services          TEXT,                        -- comma separated
    monthly           REAL NOT NULL,               -- RM per line per month
    num_lines         INTEGER NOT NULL,
    contract_months   INTEGER NOT NULL,
    device_model      TEXT,
    device_qty        INTEGER DEFAULT 0,
    device_price      REAL DEFAULT 0,
    upfront           REAL DEFAULT 0,
    deposit           REAL DEFAULT 0,
    billing_type      TEXT DEFAULT 'E-Bill Itemised',
    fixed_ip          INTEGER DEFAULT 0,
    notes             TEXT
);

CREATE TABLE documents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL REFERENCES orders(id),
    doc_key      TEXT NOT NULL,                    -- see constants.DOC_TYPES
    filename     TEXT NOT NULL,
    file_type    TEXT NOT NULL,                    -- PDF / JPG / PNG / XLSX
    size_mb      REAL NOT NULL,
    uploaded_at  TEXT NOT NULL,
    stored_name  TEXT                              -- file on disk (instance/uploads/...); NULL for seed data
);

CREATE TABLE order_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id  INTEGER NOT NULL REFERENCES orders(id),
    title     TEXT NOT NULL,                       -- e.g. 'Order submitted'
    status    TEXT,                                -- status after the event
    actor     TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    note      TEXT,
    category  TEXT,                                -- used by amendment events
    ts        TEXT NOT NULL
);
"""


def get_db():
    """Return this request's database connection (open it if needed)."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        # Row objects let us write row["status"] instead of row[3].
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(exception=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def reset_db():
    """Wipe the database and re-create it with the sample data."""
    from . import seed

    conn = get_db()
    conn.executescript(SCHEMA)
    seed.load(conn)
    conn.commit()


def init_app(app):
    app.teardown_appcontext(close_db)

    # First start: no database file yet, so create it.
    if not os.path.exists(app.config["DATABASE"]):
        with app.app_context():
            reset_db()

    # Command line helper:  flask --app run reset-db
    @app.cli.command("reset-db")
    def reset_db_command():
        """Delete all data and reload the sample data from the PDF."""
        reset_db()
        click.echo("Database reset with sample data.")
