"""Checks for Stages 4-6: Processor actions, amendments, Admin pages.

Run with:   python -m unittest discover -s tests -v
"""
import unittest

from portal.db import get_db

from test_stage1_2 import PortalTestCase
from test_stage3 import LINE, STEP2, STEP5


class FlowTestCase(PortalTestCase):
    """Helpers to act as different people in the same test."""

    def as_role(self, role):
        self.client.get("/logout")
        self.sign_in(role)

    def row(self, number):
        with self.app.app_context():
            return dict(get_db().execute("SELECT * FROM orders WHERE order_number = ?",
                                         (number,)).fetchone())

    def events(self, number):
        with self.app.app_context():
            return [r["title"] for r in get_db().execute(
                "SELECT e.title FROM order_events e JOIN orders o ON o.id = e.order_id "
                "WHERE o.order_number = ? ORDER BY e.id", (number,))]

    def submit_new_order(self):
        """Dealer creates a complete order and submits it. Returns the number."""
        self.as_role("dealer")
        r = self.client.post("/dealer/orders/new", data={
            "action": "next", "order_type": "Mobile & Broadband",
            "registration_type": "New Connection"})
        n = r.headers["Location"].split("/")[3]
        base = f"/dealer/orders/{n}/edit?step="
        self.client.post(base + "2", data=dict(STEP2, step="2", action="next"))
        self.client.post(base + "3", data=dict(LINE, step="3", action="next"))
        from portal import constants as C
        for key in C.required_doc_keys("Corporate Account", "Mobile & Broadband"):
            self.client.post(f"/dealer/orders/{n}/documents/sample", data={"doc_key": key})
        self.client.post(base + "5", data=dict(STEP5, step="5", action="next"))
        self.client.post(f"/dealer/orders/{n}/submit", data={"declaration": "on"})
        self.assertEqual(self.row(n)["status"], "Submitted")
        return n


class ProcessorTests(FlowTestCase):
    def test_dashboard_queue_and_all_orders(self):
        self.as_role("processor")
        for url in ("/processor", "/processor/queue", "/processor/orders", "/processor/help"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        html = self.client.get("/processor/queue").data.decode()
        self.assertIn("ORD-2026-00124", html)          # an Under Review order
        self.assertNotIn("ORD-2026-00109", html)       # Completed is not in the queue

    def test_filters(self):
        self.as_role("processor")
        html = self.client.get("/processor/orders?status=Completed").data.decode()
        self.assertIn("ORD-2026-00109", html)
        self.assertNotIn("ORD-2026-00124", html)

    def test_happy_path_to_completed(self):
        n = self.submit_new_order()
        self.as_role("processor")
        self.assertIn(n, self.client.get("/processor/queue").data.decode())
        self.client.post(f"/processor/orders/{n}/start")
        self.assertEqual(self.row(n)["status"], "Under Review")
        self.client.post(f"/processor/orders/{n}/approve", data={"note": "Looks good"})
        row = self.row(n)
        self.assertEqual(row["status"], "Approved")
        self.assertRegex(row["reference_id"], r"^REF-MVP-\d+$")
        self.assertEqual(row["approved_by"], "Farina Elia")
        self.client.post(f"/processor/orders/{n}/complete")
        self.assertEqual(self.row(n)["status"], "Completed")
        self.assertEqual(self.events(n)[-4:], ["Review started", "Order approved",
                         "Reference ID added", "Order marked completed"])
        # the dealer sees the reference ID
        self.as_role("dealer")
        self.assertIn(self.row(n)["reference_id"].encode(),
                      self.client.get(f"/dealer/orders/{n}").data)

    def test_reference_ids_are_unique_and_increase(self):
        a, b = self.submit_new_order(), self.submit_new_order()
        self.as_role("processor")
        for n in (a, b):
            self.client.post(f"/processor/orders/{n}/start")
            self.client.post(f"/processor/orders/{n}/approve")
        ra, rb = self.row(a)["reference_id"], self.row(b)["reference_id"]
        self.assertNotEqual(ra, rb)
        self.assertLess(int(ra.split("-")[-1]), int(rb.split("-")[-1]))

    def test_invalid_transitions_are_refused(self):
        n = self.submit_new_order()
        self.as_role("processor")
        self.client.post(f"/processor/orders/{n}/approve")     # still Submitted
        self.client.post(f"/processor/orders/{n}/complete")
        self.client.post(f"/processor/orders/{n}/amend", data={"category": "Other"})
        self.assertEqual(self.row(n)["status"], "Submitted")
        self.client.post(f"/processor/orders/{n}/start")
        self.client.post(f"/processor/orders/{n}/start")       # twice
        self.assertEqual(self.events(n).count("Review started"), 1)

    def test_cannot_open_drafts_or_unknown(self):
        self.as_role("processor")
        self.assertEqual(self.client.get("/processor/orders/ORD-2026-00130").status_code, 404)
        self.assertEqual(self.client.get("/processor/orders/NOPE").status_code, 404)

    def test_other_roles_cannot_act(self):
        n = self.submit_new_order()           # dealer is signed in
        self.assertNotEqual(self.client.post(f"/processor/orders/{n}/start").status_code, 200)
        self.assertEqual(self.row(n)["status"], "Submitted")
        self.as_role("admin")
        self.client.post(f"/processor/orders/{n}/start")
        self.assertEqual(self.row(n)["status"], "Submitted")

    def test_processor_can_preview_uploaded_documents(self):
        n = self.submit_new_order()
        with self.app.app_context():
            doc = get_db().execute("SELECT d.id FROM documents d JOIN orders o ON o.id = d.order_id "
                                   "WHERE o.order_number = ? LIMIT 1", (n,)).fetchone()
        self.as_role("processor")
        r = self.client.get(f"/processor/orders/{n}/documents/{doc['id']}")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.startswith(b"%PDF"))
        r.close()


class AmendmentTests(FlowTestCase):
    def go_to_amendment(self):
        n = self.submit_new_order()
        self.as_role("processor")
        self.client.post(f"/processor/orders/{n}/start")
        return n

    def test_amendment_needs_valid_input(self):
        n = self.go_to_amendment()
        self.client.post(f"/processor/orders/{n}/amend", data={"category": "Other", "reason": "short"})
        self.assertEqual(self.row(n)["status"], "Under Review")
        self.client.post(f"/processor/orders/{n}/amend", data={
            "category": "Bogus", "sections": ["Supporting Documents"], "reason": "x" * 30})
        self.assertEqual(self.row(n)["status"], "Under Review")

    def test_full_amendment_cycle(self):
        n = self.go_to_amendment()
        self.client.post(f"/processor/orders/{n}/amend", data={
            "category": "Supporting Document Issue", "sections": ["Supporting Documents"],
            "reason": "The signed form is unreadable. Upload a clear copy.", "due": "2026-12-01"})
        row = self.row(n)
        self.assertEqual(row["status"], "Amendment Required")
        self.assertEqual(row["amendment_cycles"], 1)
        self.assertEqual(row["amendment_due"], "2026-12-01")

        # dealer sees it, is sent to the flagged step, can replace the document
        self.as_role("dealer")
        self.assertIn(b"unreadable", self.client.get(f"/dealer/orders/{n}").data)
        r = self.client.get(f"/dealer/orders/{n}/edit")
        self.assertTrue(r.headers["Location"].endswith("step=4"))
        self.client.post(f"/dealer/orders/{n}/documents/sample", data={"doc_key": "signed_form"})

        # resubmitting needs a declaration AND a response
        self.client.post(f"/dealer/orders/{n}/submit", data={"declaration": "on"})
        self.assertEqual(self.row(n)["status"], "Amendment Required")
        self.client.post(f"/dealer/orders/{n}/submit", data={"declaration": "on", "response": "Uploaded a clear scan."})
        row = self.row(n)
        self.assertEqual(row["status"], "Submitted")
        self.assertEqual(row["submissions"], 2)
        self.assertIn("Order resubmitted", self.events(n))
        page = self.client.get(f"/dealer/orders/{n}?tab=activity").data
        self.assertIn(b"Uploaded a clear scan.", page)

        # processor restarts review and approves
        self.as_role("processor")
        self.client.post(f"/processor/orders/{n}/start")
        self.assertIn("Review restarted", self.events(n))
        self.client.post(f"/processor/orders/{n}/approve")
        self.assertEqual(self.row(n)["status"], "Approved")

    def test_locked_order_cannot_be_edited_by_dealer(self):
        n = self.go_to_amendment()          # Under Review now
        self.as_role("dealer")
        r = self.client.get(f"/dealer/orders/{n}/edit", follow_redirects=True)
        self.assertIn(b"can no longer be edited", r.data)
        self.assertEqual(self.client.post(f"/dealer/orders/{n}/documents/sample",
                                          data={"doc_key": "other"}).status_code, 403)

    def test_seeded_amendment_order_can_be_resubmitted(self):
        # ORD-2026-00128 is returned for a missing document in the sample data
        self.as_role("dealer")
        n = "ORD-2026-00128"
        from portal import constants as C
        row = self.row(n)
        for key in C.required_doc_keys(row["customer_type"], row["order_type"]):
            self.client.post(f"/dealer/orders/{n}/documents/sample", data={"doc_key": key})
        self.client.post(f"/dealer/orders/{n}/submit", data={"declaration": "on", "response": "Missing document added."})
        self.assertEqual(self.row(n)["status"], "Submitted")


class AdminTests(FlowTestCase):
    def test_pages_load(self):
        self.as_role("admin")
        for url in ("/admin", "/admin/orders", "/admin/history", "/admin/users", "/admin/reports",
                    "/admin/orders/ORD-2026-00124", "/admin/orders/ORD-2026-00124?tab=activity"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_admin_order_view_is_read_only(self):
        self.as_role("admin")
        html = self.client.get("/admin/orders/ORD-2026-00124").data.decode()
        self.assertIn("read-only", html)
        self.assertNotIn("Approve order", html)

    def test_filters_and_history(self):
        self.as_role("admin")
        html = self.client.get("/admin/orders?status=Completed").data.decode()
        self.assertIn("ORD-2026-00109", html)
        self.assertNotIn("ORD-2026-00124", html)
        h = self.client.get("/admin/history?q=Amendment").data.decode()
        self.assertIn("Amendment requested", h)
        self.assertNotIn("Order approved", h)

    def test_reports_numbers(self):
        self.as_role("admin")
        html = self.client.get("/admin/reports").data.decode()
        self.assertIn("Orders submitted", html)
        self.assertIn("14", html)            # 16 orders - 2 drafts

    def test_csv_export_and_formula_safety(self):
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE orders SET company_name = '=HYPERLINK(\"x\")' WHERE order_number = 'ORD-2026-00109'")
            db.commit()
        self.as_role("admin")
        r = self.client.get("/admin/reports/orders.csv")
        self.assertEqual(r.mimetype, "text/csv")
        text = r.data.decode()
        self.assertTrue(text.startswith("Order number,Status"))
        self.assertIn("'=HYPERLINK", text)
        self.assertEqual(len(text.strip().splitlines()), 17)

    def test_dealer_and_processor_cannot_open_admin(self):
        self.as_role("dealer")
        self.assertNotEqual(self.client.get("/admin").status_code, 200)
        self.as_role("processor")
        self.assertNotEqual(self.client.get("/admin/reports/orders.csv").status_code, 200)

    def test_logging_in_lands_on_each_home(self):
        for role, marker in (("processor", b"Processor workspace"), ("admin", b"Admin workspace")):
            self.as_role(role)
            self.assertIn(marker, self.client.get("/").data if False else self.client.get("/", follow_redirects=True).data)


if __name__ == "__main__":
    unittest.main()


class DeploymentTests(PortalTestCase):
    def test_healthz_needs_no_login(self):
        r = self.client.get("/healthz")
        self.assertEqual((r.status_code, r.data), (200, b"ok"))

    def test_error_pages(self):
        self.sign_in("dealer")
        r = self.client.get("/dealer/orders/NOPE")
        self.assertEqual(r.status_code, 404)
        self.assertIn(b"Page not found", r.data)
