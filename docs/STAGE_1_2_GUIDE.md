# Stages 1 and 2 - Setup Notes and Code Walkthrough
These are my notes for getting the portal running and finding your way around the code. The first
part is setup. The rest explains how the pieces fit together, mainly so I (or anyone) can change
things later without guessing.

# Getting it Running
What you need is Python 3.10 or newer, PyCharm or Vs Code.
How to check version:
python --version or py --version

# In PyCharm
1. Unzip enterprise-order-portal.zip somewhere with a short path, e.g. C:\Projects\enterprise-order-portal.
2. File > Open, and pick the enterprise-order-portal folder.
3. PyCharm normally offers to set up a virtual environment from requirements.txt. Say yes. If it doesn't ask, add one under File > Settings > Project > Python Interpreter > Add Interpreter > Add Local Interpreter > Virtualenv Environment > New, then run pip install -r requirements.txt in the Terminal tab.
4. Open run.py and hit the green Run arrow beside if __name__ == "__main__":.
5. The Run window will show Running on http://127.0.0.1:5000 – click it.

To stop the server, click the red square in the Run window (Ctrl+F2)

# From the command line / VS Code
`python -m venv .venv
.venv\Scripts\activate            # Windows
source .venv/bin/activate         # Mac / Linux
pip install -r requirements.txt
python run.py`

Then go to http://127.0.0.1:5000. In VS Code, install the Python extension and select the .venv interpreter (Ctrl+Shift+P > "Python: Select Interpreter").

If PowerShell complains that running scripts is disabled, either run Set-ExecutionPolicy -Scope CurrentUser RemoteSigned once or just use cmd.

# Quick tour once its up

Sign in as Dealer (under Prototype access). The dashboard shows one draft, one order waiting for amendment, and the recent orders table.
Click "Review and resubmit" on Damage Ctrl – this is the screen I spent the most time on. It shows the Processor's message, the progress bar with the amendment step, and amber dots on the tabs that need fixing. Have a look through the tabs too; ID numbers on Customer Information are masked, and Documents shows 4 of 5 uploaded.
My Orders has working filters. ORD-2026-00117 is a good one to open if you want to see a completed order where an amendment was already resolved.
Create New Order and Edit and Resubmit just show a "Coming in Stage 3 / 5" page for now. Processor and Admin logins work, but only the sidebar is real until Stages 4 and 6.

# How a page is put together
Every page goes through the same steps. Take /dealer/orders?status=Draft:
1. Flask matches the URL to orders() in dealer.py
2. That function queries the database (connection comes from get_db() in db.py).
3. It passes the rows to templates/dealer/orders.html
4. The template files in the HTML and Flask sends it back

So the Python function decides what to show and the template decides how it looks. Most
changes only touch one of the two. 

# Where things live
enterprise-order-portal/
|-- run.py                    start the server from here
|-- requirements.txt          just Flask
|-- README.md
|-- docs/                     these notes
|-- tests/test_stage1_2.py    30 automated checks
|-- instance/portal.sqlite    the database (made on first run)
`-- portal/
    |-- __init__.py           create_app() – wires everything up
    |-- constants.py          statuses, order types, required documents
    |-- db.py                 table definitions + DB connection
    |-- seed.py               sample data taken from the walkthrough PDF
    |-- helpers.py            formatting filters, order loader, sidebar
    |-- auth.py               sign in/out and role checks
    |-- dealer.py             dealer pages
    |-- stubs.py              placeholder pages for later stages
    |-- templates/            base.html, login, dealer pages, partials
    `-- static/               app.css (all styling), app.js

Templates starting with an underscore (_customer.html, _macros.html) are partials 
– they get pulled into other templates and are never loaded on their own.

# Reading the code
If youre going through it for the first time, this order makes the most sense.

1. run.py and portal/__init__.py – create_app() sets up the app and the database and registers the three blueprints (auth, dealer, stubs). A blueprint is just a group of related routes. Processor and admin will get their own later.
2. constants.py – I kept the business rules here so they only exist in one place. required_doc_keys() is the main one: corporate accounts need five documents, and Business Solution orders need a Financial Document on top. The order page and progress bar both read from this, and the Stage 3 upload wizard will too.
3. db.py – the schema is plain SQL with five tables: users, orders, order_lines (the subscription lines), documents and order_events (the activity history). row_factory = sqlite3.Row is what lets templates write order.status rather than using column numbers.
4. seed.py – each sample order is a dictionary. ORD-2026-00128 (Damage Ctrl) is worth reading, since it's the data behind the amendment screen: only four documents, so one is missing, plus the amendment_* fields and its event history.
5. auth.py – load_logged_in_user() runs before every request and puts the user in g.user. The @login_required("dealer") decorator sends signed-out users to the login page and gives other roles a 403. Passwords aren't actually checked yet (see the limitations below).
6. dealer.py – start with _my_order_or_404(). It looks orders up by number and the logged-in dealer's id, so a dealer can't open someone else's order by editing the URL. There's a test for this (test_cannot_open_another_dealers_order). After that, dashboard() runs one query and splits the results into drafts and amendments; orders() builds the query one filter at a time using ? placeholders (which is what keeps it safe from SQL injection – user input never goes straight into the SQL); and order_detail() checks the ?tab= value before loading the order.
7. helpers.py – the template filters (fmt_money, fmt_date, mask_id) are registered in init_app(). load_order_bundle() collects everything the order page needs and works out totals, progress-bar steps and resolved amendments. nav_for() builds each role's sidebar, including the badge count.
8. Templates – base.html has the sidebar, top bar and a {% block content %} that each page fills in. dealer/dashboard.html is a good simple example of loops and conditions. order_detail.html is the largest; it includes a different partial depending on which tab is open.
9. app.css – colours and sizes are variables at the top (--navy, --amber etc.), so changing one updates the whole portal.

# If something goes wrong
python not found – try py on Windows, or reinstall Python with "Add to PATH" ticked.
No module named 'flask' – the virtual environment isn't active or the packages aren't installed. Activate it and run pip install -r requirements.txt; in PyCharm, check the interpreter is the project's .venv.
Address already in use – the server is already running somewhere. Stop it with the red square, or change the port in run.py (app.run(debug=True, port=5001)).
Page has no styling – hard refresh with Ctrl+F5.
Template error – the error page shows the file and line; the last couple of lines are usually the useful bit.
Data looks off, or edits to db.py / seed.py don't show up – those only run when the database is created, so reset it with flask --app run reset-db (or delete instance/portal.sqlite and restart).

# Next: Stage 3
Stage 3 is the Create Order wizard: six steps with a progress bar, Save Draft at any point, validation messages, a running RM total on the Subscription step, real file uploads (10 MB limit and file-type checks), a review page with a declaration checkbox, and a confirmation dialog. It builds on constants.py and load_order_bundle(), 
so most of what's above carries straight over.