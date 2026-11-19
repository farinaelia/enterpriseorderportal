"""Sample data copied from the prototype PDF.

All names, numbers and dates are fictional. Running `flask --app run reset-db`
wipes the database and runs `load()` again, so you can experiment freely.
"""
from .constants import required_doc_keys

PROC = "Farina Elia"

# ---------------------------------------------------------------- users ----
USERS = [
    # name, short_name, email, role, team, region, status, last_active
    ("Muhammad Syufaiq", "Syufaiq", "syufaiq@example.com", "dealer", "Partner Channel", "Central", "Active", "2026-03-18 08:52"),
    ("Aina Rahman", "Aina", "aina.r@example.com", "dealer", "Partner Channel", "Northern", "Active", "2026-03-17 17:20"),
    ("Daniel Wong", "Daniel", "daniel.w@example.com", "dealer", "Enterprise Sales", "Southern", "Active", "2026-03-18 07:41"),
    ("Nur Izzati", "Nur", "izzati@example.com", "dealer", "Direct", "Sabah", "Inactive", "2026-02-26 11:05"),
    ("Farina Elia", "Farina", "farina.e@example.com", "processor", "Order Processing", "Central", "Active", "2026-03-18 09:02"),
    ("Hafiz Kamal", "Hafiz", "hafiz.k@example.com", "processor", "Order Processing", "Central", "Active", "2026-03-18 08:15"),
    ("System Administrator", "Admin", "admin@example.com", "admin", "Portal Administration", "All", "Active", "2026-03-18 09:00"),
]

# Default file for each document type: (filename, type, size in MB)
DOC_DEFAULTS = {
    "company_registration": ("company_registration_document.pdf", "PDF", 0.4),
    "financial": ("financial_document.pdf", "PDF", 0.9),
    "authorised_rep_id": ("authorised_representative_identification.pdf", "JPG", 1.1),
    "director_id": ("director_or_owner_identification.pdf", "PDF", 1.5),
    "proof_employment": ("proof_of_employment.pdf", "PDF", 0.7),
    "authorisation_letter": ("authorisation_or_nomination_letter.pdf", "JPG", 2.3),
    "signed_form": ("signed_registration_form.pdf", "PDF", 2.6),
    "other": ("other_supporting_document.pdf", "PDF", 0.8),
}


# ------------------------------------------------------------- helpers ----
def line(reg, plan, monthly, n, months, addons="", services="Voice,Data",
         device=None, dqty=0, dprice=0, notes=None, fixed_ip=0):
    """Describe one subscription line item."""
    return dict(registration_type=reg, rate_plan=plan, monthly=monthly,
                num_lines=n, contract_months=months, addons=addons,
                services=services, device_model=device, device_qty=dqty,
                device_price=dprice, notes=notes, fixed_ip=fixed_ip)


def ev(title, status, actor, role, note, ts, category=None):
    """Describe one entry in an order's activity history."""
    return dict(title=title, status=status, actor=actor, actor_role=role,
                note=note, ts=ts, category=category)


def std_events(status, dealer, t, ref=None):
    """Build the normal event trail for an order that has no amendments."""
    events = [ev("Draft created", "Draft", dealer, "Dealer", None, t["created"])]
    if status == "Draft":
        return events
    events.append(ev("Order submitted", "Submitted", dealer, "Dealer",
                     "Initial submission.", t["submitted"]))
    if status == "Submitted":
        return events
    events.append(ev("Review started", "Under Review", PROC, "Processor",
                     None, t["review"]))
    if status == "Under Review":
        return events
    events.append(ev("Order approved", "Approved", PROC, "Processor",
                     "All documents verified.", t["approved"]))
    events.append(ev("Reference ID added", "Approved", PROC, "Processor",
                     f"Reference ID {ref} recorded.", t["approved"]))
    if status == "Approved":
        return events
    events.append(ev("Order marked completed", "Completed", PROC, "Processor",
                     "Activation confirmed for all lines.", t["completed"]))
    return events


# -------------------------------------------------------------- orders ----
def build_orders():
    """Return the list of sample orders (a list of dictionaries)."""
    S, A, D = "Muhammad Syufaiq", "Aina Rahman", "Daniel Wong"
    orders = []

    def add(number, company, dealer, status, otype, reg, created, updated,
            lines, docs=None, events=None, t=None, ref=None, submissions=1,
            cycles=0, other_req=None, contact="Authorised Contact",
            category="Mid-Market", region="Central", device="Generic 5G Phone A",
            device_qty=10, extra=None):
        t = t or {}
        t.setdefault("created", created)
        o = dict(
            order_number=number, company_name=company, dealer=dealer,
            status=status, order_type=otype, registration_type=reg,
            created_at=created, updated_at=updated, reference_id=ref,
            submissions=submissions, amendment_cycles=cycles,
            other_requirements=other_req, contact_name=contact,
            customer_category=category, region=region, device_model=device,
            device_quantity=device_qty, lines=lines,
            docs=docs if docs is not None else required_doc_keys("Corporate Account", otype),
            events=events if events is not None else std_events(
                status, dealer, t, ref),
            submitted_at=t.get("submitted"),
            approved_at=t.get("approved"), completed_at=t.get("completed"),
        )
        if status in ("Approved", "Completed"):
            o["approved_by"] = PROC
        if status == "Completed":
            o["completed_by"] = PROC
        if extra:
            o.update(extra)
        orders.append(o)

    # ---- Syufaiq's orders (the dealer you log in as) ----
    add("ORD-2026-00109", "Kirana Health Sdn. Bhd.", S, "Completed",
        "Business Solution", "New Connection", "2026-02-24 09:10",
        "2026-02-26 15:00",
        [line("New Connection", "Managed Solution Basic", 320, 2, 36,
              device="Managed Gateway Unit", dqty=2, dprice=450)],
        t=dict(submitted="2026-02-24 10:00", review="2026-02-25 09:30",
               approved="2026-02-25 10:00", completed="2026-02-26 15:00"),
        ref="REF-MVP-76102", category="Large Enterprise",
        device="Managed Gateway Unit", device_qty=2)

    add("ORD-2026-00117", "Seri Ikhlas Sdn. Bhd.", S, "Completed", "IoT",
        "New Connection", "2026-03-02 09:05", "2026-03-06 16:30",
        [line("New Connection", "IoT Connect 500", 25, 50, 24,
              services="Data", device="IoT Tracker Module", dqty=50, dprice=35)],
        ref="REF-MVP-78421", submissions=2, cycles=1,
        other_req="Fleet tracking deployment across 3 depots.",
        region="Southern", device="IoT Tracker Module", device_qty=50,
        t=dict(submitted="2026-03-02 10:14", approved="2026-03-05 10:03",
               completed="2026-03-06 16:30"),
        events=[
            ev("Draft created", "Draft", S, "Dealer", None, "2026-03-02 09:05"),
            ev("Order submitted", "Submitted", S, "Dealer", "Initial submission.", "2026-03-02 10:14"),
            ev("Review started", "Under Review", PROC, "Processor", None, "2026-03-04 09:48"),
            ev("Amendment requested", "Amendment Required", PROC, "Processor",
               "Device quantity does not match the number of IoT lines requested. "
               "Confirm whether 40 or 50 tracker modules are required.",
               "2026-03-04 11:20", category="Subscription Detail Issue"),
            ev("Order edited", "Amendment Required", S, "Dealer",
               "Updated device quantity in line 1 from 40 to 50.", "2026-03-04 14:55"),
            ev("Order resubmitted", "Submitted", S, "Dealer",
               "Dealer response: Customer confirmed 50 tracker modules. Quantity corrected.",
               "2026-03-04 15:10"),
            ev("Review restarted", "Under Review", PROC, "Processor", None, "2026-03-05 09:12"),
            ev("Order approved", "Approved", PROC, "Processor", "All documents verified.", "2026-03-05 10:03"),
            ev("Reference ID added", "Approved", PROC, "Processor",
               "Reference ID REF-MVP-78421 recorded.", "2026-03-05 10:03"),
            ev("Order marked completed", "Completed", PROC, "Processor",
               "Activation confirmed for all 50 lines.", "2026-03-06 16:30"),
        ])

    add("ORD-2026-00121", "Bayu Agro Sdn. Bhd.", S, "Approved", "IoT",
        "New Connection", "2026-03-10 09:00", "2026-03-11 11:00",
        [line("New Connection", "IoT Connect 100", 12, 20, 24, services="Data")],
        t=dict(submitted="2026-03-10 11:12", review="2026-03-11 09:50",
               approved="2026-03-11 11:00"),
        ref="REF-MVP-77310")

    add("ORD-2026-00124", "CBL Sdn. Bhd.", S, "Under Review",
        "Business Solution", "Add Service", "2026-03-13 09:15",
        "2026-03-18 08:40",
        [line("Add Service", "Managed Solution Basic", 320, 2, 36,
              device="Managed Gateway Unit", dqty=2, dprice=450)],
        t=dict(submitted="2026-03-13 09:47", review="2026-03-18 08:40"),
        contact="Lee Mei Ling", category="Large Enterprise",
        device="Managed Gateway Unit", device_qty=2)

    add("ORD-2026-00126", "Orkid Media Sdn. Bhd.", S, "Submitted",
        "Mobile & Broadband", "New Connection", "2026-03-17 09:30",
        "2026-03-17 10:27",
        [line("New Connection", "Business Essential", 68, 6, 24)],
        t=dict(submitted="2026-03-17 10:27"))

    # Needs correction. The Processor says the company registration document
    # is missing, so only 4 of 5 required documents are uploaded.
    add("ORD-2026-00128", "Damage Ctrl Sdn. Bhd.", S, "Amendment Required",
        "Mobile & Broadband", "New Connection", "2026-03-16 09:20",
        "2026-03-17 15:24",
        [line("New Connection", "Business Plus", 98, 15, 12,
              addons="Extra Data 20GB", device="Generic 5G Phone A",
              dqty=15, dprice=120,
              notes="Contract period stated as 24 months in signed form."),
         line("Add Service", "Business Premium", 148, 3, 24,
              services="Data,VPN Access", fixed_ip=1)],
        docs=["authorised_rep_id", "director_id", "authorisation_letter", "signed_form"],
        contact="Aiman Hakimi", other_req="Delivery before end of month preferred.",
        cycles=1, ref=None,
        events=[
            ev("Draft created", "Draft", S, "Dealer", None, "2026-03-16 09:20"),
            ev("Order submitted", "Submitted", S, "Dealer", "Initial submission.", "2026-03-16 10:05"),
            ev("Review started", "Under Review", PROC, "Processor", None, "2026-03-17 09:40"),
            ev("Amendment requested", "Amendment Required", PROC, "Processor",
               "The supporting company-registration document is missing, and the "
               "selected contract period does not match the subscription entry. "
               "Upload the required document and review the contract period.",
               "2026-03-17 15:24", category="Supporting Document Issue"),
        ],
        t=dict(submitted="2026-03-16 10:05", review="2026-03-17 09:40"),
        extra=dict(
            amendment_category="Supporting Document Issue",
            amendment_reason=(
                "The supporting company-registration document is missing, and the "
                "selected contract period does not match the subscription entry. "
                "Upload the required document and review the contract period."),
            amendment_sections="Supporting Documents,Subscription Details",
            amendment_by=PROC, amendment_at="2026-03-17 15:24",
            amendment_due="2026-03-24"))

    # A draft: only 3 of 5 required documents so far.
    add("ORD-2026-00130", "Teratai Retail Sdn. Bhd.", S, "Draft",
        "Mobile & Broadband", "New Connection", "2026-03-18 08:05",
        "2026-03-18 08:20",
        [line("New Connection", "Business Essential", 68, 6, 24)],
        docs=["company_registration", "authorised_rep_id", "authorisation_letter"],
        submissions=0)

    # ---- Other dealers' orders (you will see these as Processor/Admin) ----
    add("ORD-2026-00112", "Mutiara Hotels Sdn. Bhd.", A, "Draft",
        "Mobile & Broadband", "New Connection", "2026-03-11 08:30",
        "2026-03-11 09:00",
        [line("New Connection", "Business Essential", 68, 4, 24)],
        docs=["company_registration"], submissions=0)

    add("ORD-2026-00115", "Sinar Marine Sdn. Bhd.", D, "Completed",
        "Transfer of Ownership", "Transfer of Ownership", "2026-02-26 10:00",
        "2026-03-01 14:00",
        [line("Transfer of Ownership", "Business Essential", 68, 3, 24)],
        t=dict(submitted="2026-02-26 11:00", review="2026-02-27 09:00",
               approved="2026-02-28 10:00", completed="2026-03-01 14:00"),
        ref="REF-MVP-76550", region="Southern")

    add("ORD-2026-00119", "Delima Tech Sdn. Bhd.", A, "Completed",
        "Business Solution", "New Connection", "2026-03-12 09:00",
        "2026-03-18 08:00",
        [line("New Connection", "Managed Solution Basic", 320, 2, 36)],
        t=dict(submitted="2026-03-12 10:00", review="2026-03-14 09:00",
               approved="2026-03-17 10:00", completed="2026-03-18 08:00"),
        ref="REF-MVP-76988", region="Northern", category="Large Enterprise")

    add("ORD-2026-00120", "Pelangi Motors Sdn. Bhd.", D, "Approved", "IoT",
        "New Connection", "2026-03-08 09:00", "2026-03-10 11:00",
        [line("New Connection", "IoT Connect 100", 12, 30, 24, services="Data")],
        t=dict(submitted="2026-03-08 10:00", review="2026-03-09 09:00",
               approved="2026-03-10 11:00"),
        ref="REF-MVP-77105", region="Southern")

    add("ORD-2026-00122", "Cahaya Edu Sdn. Bhd.", A, "Amendment Required",
        "Mobile & Broadband", "New Connection", "2026-03-12 09:00",
        "2026-03-13 14:00",
        [line("New Connection", "Business Essential", 68, 8, 24)],
        docs=["company_registration", "authorised_rep_id", "director_id",
              "authorisation_letter"],
        cycles=1, region="Northern",
        events=[
            ev("Draft created", "Draft", A, "Dealer", None, "2026-03-12 09:00"),
            ev("Order submitted", "Submitted", A, "Dealer", "Initial submission.", "2026-03-12 10:00"),
            ev("Review started", "Under Review", PROC, "Processor", None, "2026-03-13 09:00"),
            ev("Amendment requested", "Amendment Required", PROC, "Processor",
               "The signed registration form is missing. Upload the signed copy.",
               "2026-03-13 14:00", category="Supporting Document Issue"),
        ],
        t=dict(submitted="2026-03-12 10:00", review="2026-03-13 09:00"),
        extra=dict(
            amendment_category="Supporting Document Issue",
            amendment_reason="The signed registration form is missing. Upload the signed copy.",
            amendment_sections="Supporting Documents",
            amendment_by=PROC, amendment_at="2026-03-13 14:00",
            amendment_due="2026-03-20"))

    add("ORD-2026-00123", "Gemilang Foods Sdn. Bhd.", D, "Under Review",
        "Mobile Number Portability", "New Connection", "2026-03-14 09:00",
        "2026-03-15 10:00",
        [line("New Connection", "Business Essential", 68, 5, 24)],
        t=dict(submitted="2026-03-14 10:00", review="2026-03-15 10:00"),
        region="Southern")

    add("ORD-2026-00125", "Lestari Build Sdn. Bhd.", A, "Submitted",
        "Mobile & Broadband", "New Connection", "2026-03-15 09:00",
        "2026-03-15 11:30",
        [line("New Connection", "Business Essential", 68, 12, 24)],
        t=dict(submitted="2026-03-15 11:30"), region="Northern")

    add("ORD-2026-00127", "Puncak Data Sdn. Bhd.", D, "Submitted",
        "Business Solution", "New Connection", "2026-03-12 09:00",
        "2026-03-17 15:10",
        [line("New Connection", "Managed Solution Basic", 320, 6, 36)],
        submissions=2, cycles=1, region="Southern",
        events=[
            ev("Draft created", "Draft", D, "Dealer", None, "2026-03-12 09:00"),
            ev("Order submitted", "Submitted", D, "Dealer", "Initial submission.", "2026-03-12 10:00"),
            ev("Review started", "Under Review", PROC, "Processor", None, "2026-03-13 09:00"),
            ev("Amendment requested", "Amendment Required", PROC, "Processor",
               "Primary contact designation is missing. Provide the designation "
               "of the authorised contact.", "2026-03-13 11:20",
               category="Customer Information Issue"),
            ev("Order resubmitted", "Submitted", D, "Dealer",
               "Dealer response: Designation added.", "2026-03-17 15:10"),
        ],
        t=dict(submitted="2026-03-12 10:00", review="2026-03-13 09:00"))

    add("ORD-2026-00129", "Nusantara Logistik Sdn. Bhd.", A, "Submitted",
        "IoT", "New Connection", "2026-03-17 09:00", "2026-03-17 17:52",
        [line("New Connection", "IoT Connect 100", 12, 20, 24, services="Data")],
        t=dict(submitted="2026-03-17 17:52"), region="Northern")

    return orders


# ------------------------------------------------------------- loader ----
def load(conn):
    """Insert the users and orders into an empty database."""
    # 1) users
    for u in USERS:
        conn.execute(
            "INSERT INTO users (name, short_name, email, role, team, region, status, last_active)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", u)
    user_id = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM users")}

    # 2) orders (+ their lines, documents and events)
    for o in build_orders():
        dealer = o["dealer"]
        partner_first = conn.execute(
            "SELECT short_name FROM users WHERE name = ?", (dealer,)).fetchone()[0]

        cur = conn.execute(
            """INSERT INTO orders (
                order_number, dealer_id, status, order_type, registration_type,
                customer_type, created_at, updated_at, submitted_at, reference_id,
                submissions, amendment_cycles, other_requirements,
                company_name, brn, old_brn, tin, sst_no, existing_account_no,
                address, city, postcode, contact_name, contact_id_no,
                contact_designation, contact_phone, contact_email,
                partner_name, channel, region, account_manager,
                customer_category, site_contact_name, site_contact_number,
                device_model, device_quantity, service_address,
                installation_address, internal_notes,
                amendment_category, amendment_reason, amendment_sections,
                amendment_by, amendment_at, amendment_due,
                approved_by, approved_at, completed_by, completed_at
            ) VALUES (""" + ", ".join(["?"] * 49) + """)""",
            (
                o["order_number"], user_id[dealer], o["status"], o["order_type"],
                o["registration_type"], "Corporate Account", o["created_at"],
                o["updated_at"], o["submitted_at"], o["reference_id"],
                o["submissions"], o["amendment_cycles"], o["other_requirements"],
                o["company_name"], "202601234567", None, "C2026001234", None,
                "123454589",
                "Level 8, Menara Contoh, Jalan Sampel 1", "Kuala Lumpur", "50450",
                o["contact_name"], "900101-14-1234", "Operations Manager",
                "+60 12-345 6789", "contact@example.com",
                f"{partner_first} Partner Network", "Partner", o["region"],
                "Account Manager A", o["customer_category"], "Site Coordinator",
                "+60 12-345 6789", o["device_model"], o["device_quantity"],
                "Level 8, Menara Contoh, Jalan Sampel 1, 50450 Kuala Lumpur",
                None, None,
                o.get("amendment_category"), o.get("amendment_reason"),
                o.get("amendment_sections"), o.get("amendment_by"),
                o.get("amendment_at"), o.get("amendment_due"),
                o.get("approved_by"), o.get("approved_at"),
                o.get("completed_by"), o.get("completed_at"),
            ),
        )
        order_id = cur.lastrowid

        for pos, ln in enumerate(o["lines"], start=1):
            conn.execute(
                """INSERT INTO order_lines (order_id, position, registration_type,
                   rate_plan, addons, services, monthly, num_lines, contract_months,
                   device_model, device_qty, device_price, notes, fixed_ip)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (order_id, pos, ln["registration_type"], ln["rate_plan"],
                 ln["addons"], ln["services"], ln["monthly"], ln["num_lines"],
                 ln["contract_months"], ln["device_model"], ln["device_qty"],
                 ln["device_price"], ln["notes"], ln["fixed_ip"]))

        uploaded_at = o["created_at"]
        for key in o["docs"]:
            filename, ftype, size = DOC_DEFAULTS[key]
            conn.execute(
                "INSERT INTO documents (order_id, doc_key, filename, file_type,"
                " size_mb, uploaded_at) VALUES (?,?,?,?,?,?)",
                (order_id, key, filename, ftype, size, uploaded_at))

        for e in o["events"]:
            conn.execute(
                "INSERT INTO order_events (order_id, title, status, actor,"
                " actor_role, note, category, ts) VALUES (?,?,?,?,?,?,?,?)",
                (order_id, e["title"], e["status"], e["actor"], e["actor_role"],
                 e["note"], e["category"], e["ts"]))
