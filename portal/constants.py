"""Fixed lists and business rules in one place.

When a rule changes (for example a new document type or a new rate plan), you
change it here and every page and form picks it up.
"""

# ---- Order statuses -------------------------------------------------------
STATUSES = [
    "Draft",
    "Submitted",
    "Under Review",
    "Amendment Required",
    "Approved",
    "Completed",
]

# The five steps drawn in the progress bar on an order page.
PROGRESS_STEPS = ["Draft", "Submitted", "Under Review", "Approved", "Completed"]

# Which progress step each status sits on. "Amendment Required" is a detour
# that happens while the order is Under Review.
STEP_INDEX = {
    "Draft": 0,
    "Submitted": 1,
    "Under Review": 2,
    "Amendment Required": 2,
    "Approved": 3,
    "Completed": 4,
}

# Statuses in which the dealer may NOT edit the order.
LOCKED_STATUSES = {"Submitted", "Under Review", "Approved", "Completed"}

# What the "Next action" column says for each status (dealer view).
DEALER_NEXT_ACTION = {
    "Draft": "Complete and submit",
    "Submitted": "Awaiting review",
    "Under Review": "No action — in review",
    "Amendment Required": "Edit and resubmit",
    "Approved": "Awaiting completion",
    "Completed": "None — completed",
}

# What the "What happens next?" card says for each status.
WHAT_HAPPENS_NEXT = {
    "Draft": "This order is still a draft. Complete all steps and submit it when ready.",
    "Submitted": "Your order is waiting for a Processor to begin the review.",
    "Under Review": "Your order is currently being validated. Editing is temporarily disabled.",
    "Amendment Required": (
        "Updates are required before processing can continue. "
        "Review the reason below and resubmit the same order."
    ),
    "Approved": "Your order has been approved. The reference ID is available below.",
    "Completed": "This order has completed the MVP processing workflow.",
}

# ---- Order types ----------------------------------------------------------
ORDER_TYPES = [
    "Mobile & Broadband",
    "IoT",
    "Business Solution",
    "Mobile Number Portability",
    "Transfer of Ownership",
    "Special Number or Exception Request",
    "Other",
]

# Icon name + one-line description shown on each order-type card (step 1).
ORDER_TYPE_INFO = {
    "Mobile & Broadband": ("phone", "Mobile lines, data plans and broadband for staff"),
    "IoT": ("chip", "Connectivity for trackers, sensors and machines"),
    "Business Solution": ("briefcase", "Managed connectivity and bundled services"),
    "Mobile Number Portability": ("swap", "Port existing numbers into the account"),
    "Transfer of Ownership": ("user-cog", "Move lines between account holders"),
    "Special Number or Exception Request": ("star", "Requests outside standard plans"),
    "Other": ("dots", "Anything not covered above"),
}

REGISTRATION_TYPES = [
    "New Connection",
    "Reconnection",
    "Plan Upgrade",
    "Plan Downgrade",
    "Add Service",
    "Remove Service",
    "Transfer of Ownership",
    "Other",
]

# ---- Customer ---------------------------------------------------------------
CUSTOMER_TYPES = ["Corporate Account", "Corporate Individual"]
CUSTOMER_TYPE_INFO = {
    "Corporate Account": ("building", "A registered company with an authorised primary contact"),
    "Corporate Individual": ("user", "An individual subscribing under a company arrangement"),
}

# ---- Subscription lines -----------------------------------------------------
# Monthly price per line (RM). Used to pre-fill the "Monthly Commitment" box.
RATE_PLANS = {
    "Business Essential": 68,
    "Business Plus": 98,
    "Business Premium": 148,
    "IoT Connect 100": 12,
    "IoT Connect 500": 25,
    "Managed Solution Basic": 320,
}

# Which plans may be chosen for which order type (a business rule).
_MOBILE_PLANS = ["Business Essential", "Business Plus", "Business Premium"]
PLANS_BY_ORDER_TYPE = {
    "IoT": ["IoT Connect 100", "IoT Connect 500"],
    "Business Solution": ["Managed Solution Basic"],
}


def plans_for(order_type):
    """Rate plans a dealer may pick for this order type."""
    return PLANS_BY_ORDER_TYPE.get(order_type, _MOBILE_PLANS)


CONTRACT_MONTHS = [12, 24, 36]
BILLING_TYPES = ["E-Bill Itemised", "E-Bill Summary", "Paper Bill"]
ADDONS = ["Extra Data 20GB", "Roaming Pack", "Cloud Backup", "Static Voice Line", "Security Shield"]
SERVICES = ["Voice", "Data", "SMS", "VPN Access", "Priority Support"]
DEVICE_MODELS = ["Generic 5G Phone A", "Generic 5G Phone B", "IoT Tracker Module", "Managed Gateway Unit"]

# ---- Internal details (step 5) --------------------------------------------
CHANNELS = ["Partner", "Direct", "Online"]
REGIONS = ["Central", "Northern", "Southern", "Eastern", "Sabah", "Sarawak"]
CUSTOMER_CATEGORIES = ["SME", "Mid-Market", "Large Enterprise", "Government"]
ACCOUNT_MANAGERS = ["Account Manager A", "Account Manager B", "Account Manager C"]

# ---- The wizard -------------------------------------------------------------
WIZARD_STEPS = [
    (1, "Order Type"),
    (2, "Customer Information"),
    (3, "Subscription Details"),
    (4, "Supporting Documents"),
    (5, "Internal Details"),
    (6, "Review and Submit"),
]

# ---- Supporting documents -------------------------------------------------
# (key, label). The key is what we store in the database.
DOC_TYPES = [
    ("company_registration", "Company Registration Document"),
    ("financial", "Financial Document"),
    ("authorised_rep_id", "Authorised Representative Identification"),
    ("director_id", "Director or Owner Identification"),
    ("proof_employment", "Proof of Employment"),
    ("authorisation_letter", "Authorisation or Nomination Letter"),
    ("signed_form", "Signed Registration Form"),
    ("other", "Other Supporting Document"),
]
DOC_LABELS = dict(DOC_TYPES)

# Upload rules
ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "xlsx"}
MAX_UPLOAD_MB = 10


def required_doc_keys(customer_type, order_type):
    """Which documents are REQUIRED for this kind of order.

    This is a business rule, written once and used by the order pages, the
    upload step and the submit check:
      * A Corporate Account needs five documents.
      * A Corporate Individual needs four (their own ID, the authorisation
        letter, the signed form and proof of employment).
      * A Business Solution order also needs a Financial Document.
    """
    if customer_type == "Corporate Individual":
        required = [
            "authorised_rep_id",
            "proof_employment",
            "authorisation_letter",
            "signed_form",
        ]
    else:
        required = [
            "company_registration",
            "authorised_rep_id",
            "director_id",
            "authorisation_letter",
            "signed_form",
        ]
    if order_type == "Business Solution":
        required.insert(1, "financial")
    return required


# ---- Amendments (Stage 4/5) -------------------------------------------------
AMEND_CATEGORIES = [
    "Customer Information Issue",
    "Subscription Detail Issue",
    "Supporting Document Issue",
    "Internal Information Issue",
    "Other",
]
# Section name (shown to people) -> wizard step number
AMEND_SECTIONS = {
    "Customer Information": 2,
    "Subscription Details": 3,
    "Supporting Documents": 4,
    "Internal Details": 5,
}
AMEND_DAYS = 7          # default "please resubmit within" period
