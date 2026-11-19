# Stage 3 - The Create Order Wizard
Stage 3 adds the six-step Create Order wizard. These notes cover updating the project, 
what to try, and how the wizard code works.

# Updating the project
Unzip the new files over your existing project folder and let it replace anything it asks about. 
Then, with the virtual environment active:

```
flask --app run reset-db      # the tables changed, so rebuild once
python run.py                 # runs on http://127.0.0.1:8000
```

Sign in as Dealer and click Create Order.
reset-db wipes the database and reloads the sample data, so any test orders 
you made before will be gone. For prototype that is fine.

# Things to try
1. Click Create Order, pick an order type and press Continue. A new draft is created straight away (e.g. ORD-2026-00131).
2. On step 2, press Continue without filling anything in. You'll get red error messages and nothing is saved.
3. Fill in half the fields and press Save Draft instead. That one saves regardless, and you can pick it up later from My Orders > Continue draft.
4. On step 3, change the rate plan. The monthly commitment fills itself in and the order summary on the side updates as you go. Duplicate, Delete and Add another line all save to the database.
5. On step 4, either click Use sample or upload your own PDF, JPG, PNG or XLSX. Files are checked before they're stored, and you can preview or remove them afterwards.
6. On step 6, Submit Order asks for confirmation, then sets the status to Submitted and locks the order.

# What changed

```
portal/forms.py            new      validating, loading and saving each step
portal/wizard.py           new      the wizard routes ("wizard" blueprint)
portal/constants.py        changed  plans, devices, channels, upload rules
portal/db.py               changed  drafts can be empty; documents.stored_name
portal/dealer.py           changed  working date filter, document preview
portal/helpers.py          changed  upload_root(), nav link
portal/__init__.py         changed  registers wizard, error pages, upload limit
templates/dealer/wizard.html, wizard/_step1..6.html, _fields.html   new
templates/dealer/submitted.html, templates/errors.html              new
static/js/wizard.js        new
static/css/app.css         changed  wizard styles added at the bottom
tests/test_stage3.py       new      22 tests
```

# How a wizard step works
Once you understand one step, the rest are the same. It all happens in portal/forms.py.

When the page loads (a GET to something like /dealer/orders/ORD-2026-00131/edit?step=2), load_values() reads what's already saved and fills in the form.

When a button is pressed (a POST to the same URL), the form sends an action value and the code:

1. reads the form into a dict with parse_step(),
2. checks it with validate_step(), which returns any errors, e.g. {"brn": "must be 12 digits"},
3. writes it to the database with save_step(),
4. redirects to the next step, or back to the same one.
The three buttons behave differently on purpose:
1. Save Draft (action=save) saves whatever's there, even if incomplete.
2. Continue (action=next) validates first. If anything fails, the page is shown again with the errors and nothing gets saved.
3. Back (action=back) saves without validating, then goes back a step.
After a successful POST, the code redirects instead of rendering the page directly. That's what stops the browser asking "resubmit form?" if you refresh.
It's a common pattern called Post/Redirect/Get, and I'll be using it again in later stages.

