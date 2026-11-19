"""Automated checks for Stage 3: the Create Order wizard.

Run with:   python -m unittest discover -s tests -v
"""
import io
import os
import unittest

from portal import forms
from portal.db import get_db

from test_stage1_2 import PortalTestCase

STEP2 = {
    "customer_type": "Corporate Account", "company_name": "Test Sdn Bhd",
    "brn": "202601234567", "address": "1 Jpalan Test", "city": "Kuala Lumpur",
    "postcode": "50450", "contact_name": "Ali Test",
    "contact_id_no": "900101-14-1234", "contact_designation": "Manager",
    "contact_phone": "012-345 6789", "contact_email": "ali@test.my",
}
LINE = {"line_count": "1", "l0_registration_type": "New Connection",
        "l0_rate_plan": "Business Plus", "l0_monthly": "98", "l0_num_lines": "3",
        "l0_contract_months": "24", "l0_billing_type": "E-Bill Itemised",
        "l0_device_model": "", "l0_device_qty": "0", "l0_device_price": "0",
        "l0_upfront": "0", "l0_deposit": "0"}
STEP5 = {"channel": "Partner", "region": "Central", "account_manager": "Account Manager A",
         "customer_category": "SME"}


class WizardTests(PortalTestCase):
    def setUp(self):
        super().setUp()
        self.sign_in("dealer")

    # helpers ---------------------------------------------------------
    def create(self, **extra):
        data = {"step": "1", "action": "next", "order_type": "Mobile & Broadband",
                "registration_type": "New Connection"}
        data.update(extra)
        r = self.client.post("/dealer/orders/new", data=data)
        self.assertEqual(r.status_code, 302)
        return r.headers["Location"].split("/")[3]

    def post(self, number, step, data, action="next"):
        d = {"step": str(step), "action": action}
        d.update(data)
        return self.client.post(f"/dealer/orders/{number}/edit?step={step}", data=d)

    def db_row(self, number):
        with self.app.app_context():
            return dict(get_db().execute("SELECT * FROM orders WHERE order_number = ?",
                                         (number,)).fetchone())

    def upload_all_required(self, number):
        row = self.db_row(number)
        from portal import constants as C
        for key in C.required_doc_keys(row["customer_type"], row["order_type"]):
            self.client.post(f"/dealer/orders/{number}/documents/sample", data={"doc_key": key})

    def fill_everything(self):
        n = self.create()
        self.post(n, 2, STEP2)
        self.post(n, 3, LINE)
        self.upload_all_required(n)
        self.post(n, 5, STEP5)
        return n

    # step 1 ----------------------------------------------------------
    def test_new_page_loads_without_saving(self):
        r = self.client.get("/dealer/orders/new")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Not saved yet", r.data)
        self.assertEqual(self.count_orders(), 16)

    def count_orders(self):
        with self.app.app_context():
            return get_db().execute("SELECT COUNT(*) FROM orders").fetchone()[0]

    def test_step1_validation_blocks_and_creates_nothing(self):
        r = self.client.post("/dealer/orders/new", data={"action": "next"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Choose an order type.", r.data)
        self.assertEqual(self.count_orders(), 16)

    def test_first_new_order_follows_seed_data(self):
        n = self.create()
        year = n.split("-")[1]
        self.assertEqual(n, f"ORD-{year}-00131")
        self.assertEqual(self.create(), f"ORD-{year}-00132")

    def test_save_draft_keeps_partial_data(self):
        n = self.create()
        self.post(n, 2, {"company_name": "Half Done", "brn": "123"}, action="save")
        row = self.db_row(n)
        self.assertEqual(row["company_name"], "Half Done")
        self.assertEqual(row["brn"], "123")
        self.assertEqual(row["status"], "Draft")

    # step 2 ----------------------------------------------------------
    def test_step2_rules(self):
        n = self.create()
        bad = dict(STEP2, brn="123", postcode="50", contact_id_no="12345",
                   contact_phone="abc", contact_email="nope")
        r = self.post(n, 2, bad)
        self.assertEqual(r.status_code, 200)
        for msg in (b"12 digits", b"postcode must be 5 digits", b"900101-14-1234",
                    b"valid Malaysian phone", b"valid email"):
            self.assertIn(msg, r.data)
        self.assertIsNone(self.db_row(n)["company_name"])   # not saved on error
        r = self.post(n, 2, STEP2)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.db_row(n)["company_name"], "Test Sdn Bhd")

    def test_individual_does_not_need_brn(self):
        errors = forms.validate_step(2, dict(STEP2, customer_type="Corporate Individual",
                                             brn="", contact_designation=""))
        self.assertEqual(errors, {})
        errors = forms.validate_step(2, dict(STEP2, brn="", contact_designation=""))
        self.assertIn("brn", errors)
        self.assertIn("contact_designation", errors)

    # step 3 ----------------------------------------------------------
    def test_lines_add_duplicate_delete(self):
        n = self.create()
        self.post(n, 3, LINE, action="add_line")
        r = self.client.get(f"/dealer/orders/{n}/edit?step=3")
        self.assertIn(b"Subscription line 2", r.data)
        self.post(n, 3, dict(LINE, line_count="1"), action="dup_line:0")
        with self.app.app_context():
            c = get_db().execute("SELECT COUNT(*) FROM order_lines WHERE order_id = ?",
                                 (self.db_row(n)["id"],)).fetchone()[0]
        self.assertEqual(c, 2)
        # delete: the form now has 2 lines
        both = dict(LINE, line_count="2", **{k.replace("l0_", "l1_"): v for k, v in LINE.items() if k.startswith("l0_")})
        self.post(n, 3, both, action="del_line:1")
        r = self.client.get(f"/dealer/orders/{n}/edit?step=3")
        self.assertNotIn(b"Subscription line 2", r.data)

    def test_line_rules(self):
        e = forms.validate_step(3, {"lines": [], "other_requirements": ""})
        self.assertIn("lines", e)
        line = forms.blank_line("Mobile & Broadband")
        line.update(rate_plan="IoT Connect 100", monthly="0", num_lines="0")
        e = forms.validate_step(3, {"lines": [line], "other_requirements": ""},
                                {"order_type": "Mobile & Broadband"})
        self.assertIn("l0_rate_plan", e)       # plan not valid for this order type
        self.assertIn("l0_monthly", e)
        self.assertIn("l0_num_lines", e)
        line.update(rate_plan="Business Plus", monthly="98", num_lines="1", device_model="Generic 5G Phone A", device_qty="0")
        e = forms.validate_step(3, {"lines": [line], "other_requirements": ""},
                                {"order_type": "Mobile & Broadband"})
        self.assertIn("l0_device_qty", e)

    def test_iot_only_offers_iot_plans(self):
        n = self.create(order_type="IoT")
        html = self.client.get(f"/dealer/orders/{n}/edit?step=3").data.decode()
        self.assertIn("IoT Connect 100", html)
        self.assertNotIn('<option value="Business Premium"', html)

    # step 4 ----------------------------------------------------------
    def test_upload_rules(self):
        n = self.create()
        url = f"/dealer/orders/{n}/documents/upload"
        from portal.wizard import make_sample_pdf
        pdf = make_sample_pdf("Test")

        def up(name, data):
            return self.client.post(url, data={"doc_key": "signed_form",
                                               "file": (io.BytesIO(data), name)},
                                    content_type="multipart/form-data", follow_redirects=True)
        self.assertIn(b"File type not allowed", up("evil.exe", b"MZ").data)
        self.assertIn(b"does not look like a real", up("fake.pdf", b"not a pdf").data)
        self.assertIn(b"File too large", up("big.pdf", b"%PDF" + b"0" * (11 * 1024 * 1024)).data)
        self.assertIn(b"Document uploaded", up("form.pdf", pdf).data)
        with self.app.app_context():
            doc = get_db().execute(
                "SELECT d.* FROM documents d JOIN orders o ON o.id = d.order_id "
                "WHERE d.doc_key='signed_form' AND o.order_number = ?", (n,)).fetchone()
        self.assertEqual(doc["filename"], "form.pdf")
        path = os.path.join(self.app.config["UPLOAD_FOLDER"], n, doc["stored_name"])
        self.assertTrue(os.path.isfile(path))
        # replacing keeps one row
        up("form2.pdf", pdf)
        with self.app.app_context():
            c = get_db().execute(
                "SELECT COUNT(*) FROM documents d JOIN orders o ON o.id = d.order_id "
                "WHERE d.doc_key='signed_form' AND o.order_number = ?", (n,)).fetchone()[0]
        self.assertEqual(c, 1)

    def test_preview_remove_and_ownership(self):
        n = self.create()
        self.client.post(f"/dealer/orders/{n}/documents/sample", data={"doc_key": "signed_form"})
        with self.app.app_context():
            doc = dict(get_db().execute(
                "SELECT d.* FROM documents d JOIN orders o ON o.id = d.order_id "
                "WHERE d.doc_key='signed_form' AND o.order_number = ?", (n,)).fetchone())
        r = self.client.get(f"/dealer/orders/{n}/documents/{doc['id']}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/pdf")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertTrue(r.data.startswith(b"%PDF"))
        # another dealer cannot read it
        self.client.get("/logout")
        self.client.post("/login", data={"email": "aina.r@example.com", "password": "x"})
        self.assertEqual(self.client.get(f"/dealer/orders/{n}/documents/{doc['id']}").status_code, 404)
        self.client.get("/logout")
        self.sign_in("dealer")
        self.client.post(f"/dealer/orders/{n}/documents/{doc['id']}/remove")
        self.assertEqual(self.client.get(f"/dealer/orders/{n}/documents/{doc['id']}").status_code, 404)

    def test_step4_requires_documents(self):
        n = self.create()
        r = self.post(n, 4, {})
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Upload every required document", r.data)
        self.upload_all_required(n)
        self.assertEqual(self.post(n, 4, {}).status_code, 302)

    # step 5 + submit -----------------------------------------------------
    def test_step5_requires_fields(self):
        n = self.create()
        r = self.post(n, 5, {})
        self.assertIn(b"Choose a channel.", r.data)
        self.assertEqual(self.post(n, 5, STEP5).status_code, 302)

    def test_submit_blocked_until_ready(self):
        n = self.create()
        page = self.client.get(f"/dealer/orders/{n}/edit?step=6").data
        self.assertIn(b"not ready to submit", page)
        r = self.client.post(f"/dealer/orders/{n}/submit", data={"declaration": "on"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.db_row(n)["status"], "Draft")

    def test_submit_needs_declaration(self):
        n = self.fill_everything()
        self.client.post(f"/dealer/orders/{n}/submit", data={})
        self.assertEqual(self.db_row(n)["status"], "Draft")

    def test_full_flow_to_submitted(self):
        n = self.fill_everything()
        page = self.client.get(f"/dealer/orders/{n}/edit?step=6").data
        self.assertNotIn(b"not ready to submit", page)
        self.assertIn(b"Test Sdn Bhd", page)
        r = self.client.post(f"/dealer/orders/{n}/submit", data={"declaration": "on"},
                             follow_redirects=True)
        self.assertIn(b"Order submitted", r.data)
        row = self.db_row(n)
        self.assertEqual(row["status"], "Submitted")
        self.assertEqual(row["submissions"], 1)
        self.assertTrue(row["submitted_at"])
        # now locked: editing is refused and uploads are forbidden
        r = self.client.get(f"/dealer/orders/{n}/edit", follow_redirects=True)
        self.assertIn(b"can no longer be edited", r.data)
        r = self.client.post(f"/dealer/orders/{n}/documents/sample", data={"doc_key": "other"})
        self.assertEqual(r.status_code, 403)
        # activity shows the events
        act = self.client.get(f"/dealer/orders/{n}?tab=activity").data
        self.assertIn(b"Order submitted", act)
        self.assertIn(b"Draft created", act)

    # security + lists ----------------------------------------------------
    def test_cannot_edit_other_dealers_order(self):
        self.assertEqual(self.client.get("/dealer/orders/ORD-2026-00129/edit").status_code, 404)
        self.assertEqual(self.client.post("/dealer/orders/ORD-2026-00129/submit").status_code, 404)

    def test_resume_seed_draft(self):
        r = self.client.get("/dealer/orders/ORD-2026-00130/edit?step=2")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Company details", r.data)

    def test_amendment_order_opens_wizard_at_flagged_step(self):
        r = self.client.get("/dealer/orders/ORD-2026-00128/edit")
        self.assertEqual(r.status_code, 302)
        self.assertIn("step=", r.headers["Location"])
        page = self.client.get("/dealer/orders/ORD-2026-00128/edit?step=4").data
        self.assertIn(b"Edit and Resubmit", page)
        self.assertIn(b"Amendment Required", page)

    def test_blank_draft_appears_in_my_orders(self):
        self.create()
        html = self.client.get("/dealer/orders").data.decode()
        self.assertIn("Untitled draft", html)
        self.assertIn("ORD-2026-00131".replace("2026", str(__import__("datetime").datetime.now().year)), html)

    def test_date_filters(self):
        for value in ("today", "7", "30", "year", ""):
            self.assertEqual(self.client.get(f"/dealer/orders?date={value}").status_code, 200)

    def test_sensitive_values_masked_after_submit(self):
        n = self.fill_everything()
        html = self.client.get(f"/dealer/orders/{n}?tab=customer").data.decode()
        self.assertNotIn("202601234567", html)
        self.assertNotIn("900101-14-1234", html)


if __name__ == "__main__":
    unittest.main()
