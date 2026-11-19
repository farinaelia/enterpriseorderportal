# Stages 4 to 7 - Processor, Amendments, Admin and Docker
These stages finish off the main workflow. 
Processors can now review, approve or send orders back for amendment, 
dealers can fix and resubmit, and Admin gets a read-only view with reports. 
Stage 7 adds Docker so the whole thing can run with one command.

# Updating the project
Unzip the new files over your project folder and replace anything it asks about. 
The database tables haven't changed since Stage 3, so there's no need to reset this time. 
Just run python run.py and go to http://127.0.0.1:8000.

# Walking through the full workflow
This takes about ten minutes and touches every role
1. Sign in as Dealer, create an order and go through all 6 steps
2. Sign out and sign in as Processor. Open order from work queue and click Start Review
3. Click Request amendment. Pick category, tick documents, add reason and send
4. Back as Dealer, order now has banner. Edit and resubmit will take you to step that was flagged. Fix it, goto step 6
click Resubmit order and write short response
5. As processor again, the order is back in queue. Start review and click approve order. Reference ID will be generated
6. Click Mark Completed
7. Sign in as Admin, have a look at overview, Status History, Reports and Export orders (CSV)

# How its put together
**Processor** actions live in portal/staff.py under the processor blueprint. Each action is a POST route that follows the same pattern: check the order's current status, update it, log an order_events row, then redirect.
**Amendments** are split between staff.amend and wizard.py. The processor saves the reason, the flagged sections and a due date on the order, and the dealer's wizard reads those to show the message and highlight the right steps.
**Resubmitting** uses the same wizard.submit route as the first submission. The only difference is that if the order is in Amendment Required, it also needs a written response from the dealer.
**Admin** is in staff.py too, under its own admin blueprint. It's read-only – it reuses the same templates but without any action buttons.
**The order view** is shared. Each tab is a partial in templates/dealer/_*.html, and dealer, processor and admin all use the same ones, so a change there shows up for everyone.

# Status Rules
**Action**	            **Only allowed when the order is**	            **Moves it to**
Start review	          Submitted	                                      Under Review
Approve	                  Under Review, with all required 
                          documents uploaded	                          Approved
Request amendment	      Under Review	                                  Amendment Required
Resubmit (dealer)	      Amendment Required	                          Submitted
Mark completed	          Approved	                                      Completed

Since every route checks the status before doing anything, 
double-clicking a button or using an old browser tab can't push an order into the wrong state. 
tests/test_stage4_6.py covers these cases.

# Running it in Docker (Stage 7)

On a Mac, install Docker Desktop and make sure it's running (the whale icon in the menu bar). Then, from the project folder:
```
bash
docker compose up --build
```
Open http://127.0.0.1:8000. To stop it, press Ctrl+C and then run docker compose down. To wipe the demo data and start fresh, use docker compose down -v followed by docker compose up.

The Docker files:
* Dockerfile – builds the image: Python 3.12, installs Flask, copies the code in and runs it with gunicorn as a non-root user. /data is a volume, so the database and uploads are kept between restarts.
* docker-compose.yml – runs the image on port 8000 with a SECRET_KEY and the data volume. The key in there is a placeholder and should be changed.
* .dockerignore – keeps the virtual environment, git history and local database out of the image.
* /healthz – a small endpoint Docker uses to check the app is still up.

# Beyond the MVP
If this were going to become a real system, the next things I'd look at are: 
proper authentication (SSO or hashed passwords), moving to PostgreSQL, file storage like S3 with virus scanning, 
email notifications, pagination and search indexes for larger order volumes, audit exports, 
and a proper roles and permissions table instead of the three fixed roles.