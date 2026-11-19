# Enterprise Order Portal (prototype)

This is part of my Work-Based Learning phase 2 project with the company I am currently interning at.
The title of the main project is **Design and Development of a Web-Based Order Submission and Tracking Portal For Telecommunications Services**. 
It is a based on a real-life project with an existing client. Though, **all data here is fictional**.
Passwords are not checked (prototype shortcut): use the *Prototype access* buttons on the sign-in page.
This portal has three roles:

**Role**       | **What They Can Do**
**Dealer**     |    Dashboard, create orders in a 6-step wizard, save drafts, upload documents, submit, track status, fix and resubmit returned orders
**Processor**  |    Work queue, review an order, approve (reference ID is generated), request an amendment, mark completed
**Admin**      |    Read-only overview, all orders, status history, users, reports, CSV export

# Order lifecycle

```
Draft -> Submitted -> Under Review -> Approved -> Completed
                          |
                          +-> Amendment Required -> (dealer fixes) -> Submitted again
```

## Quick start (Mac / Linux / Windows)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py                    # then open http://127.0.0.1:8000
```

The database is created and filled with sample data on first run
(`instance/portal.sqlite`).

## Run with Docker

```bash
docker compose up --build        # open http://127.0.0.1:8000
docker compose down              # stop (data is kept in a volume)
docker compose down -v           # stop AND delete the data
```

Or without compose:

```bash
docker build -t order-portal .
docker run -p 8000:8000 -v portal-data:/data -e SECRET_KEY=change-me order-portal
```

# Useful commands

**Task**                             | **Command**
1. Run the app on another port       | `python run.py 8001`
2. Reset the database to sample data | `flask --app run reset-db`
3. Run automated test                | `python -m unittest discover -s tests -v`

# Project layout

```
run.py                  start the app
portal/
  __init__.py           create_app(): settings, blueprints, error pages
  constants.py          statuses, plans, document rules (change business rules here)
  db.py, seed.py        SQLite schema and the sample data
  auth.py               sign-in, roles, @login_required
  dealer.py             dealer dashboard, My Orders, order detail
  wizard.py, forms.py   Create Order / amendment wizard and its validation
  staff.py              Processor and Admin pages
  helpers.py            template filters and shared helpers
  templates/, static/   HTML, CSS, JavaScript
tests/                  automated tests (70+)
docs/                   step-by-step guides for each stage
Dockerfile, docker-compose.yml, .github/workflows/tests.yml
```

# Guides

* [`docs/STAGE_1_2_GUIDE.md`](docs/STAGE_1_2_GUIDE.md): setup, code reading order, glossary
* [`docs/STAGE_3_GUIDE.md`](docs/STAGE_3_GUIDE.md): the wizard
* [`docs/STAGE_4_7_GUIDE.md`](docs/STAGE_4_7_GUIDE.md): Processor, amendments, Admin, Docker

# Known limits of the prototype

* No real password check, no password reset, no user management.
* Uploaded files are validated (type, size, content signature) but not virus-scanned.
* SQLite and one gunicorn worker: fine for a demo, not for heavy traffic.
* No email notifications; the bell icon is decorative.
* Processors see sensitive identifiers masked, the same as dealers.
