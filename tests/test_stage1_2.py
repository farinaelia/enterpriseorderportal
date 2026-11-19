"""Automated checks for Stages 1-2.

Run them with:   python -m unittest discover -s tests -v

Each test starts a fresh app with a temporary database, so your real data
in instance/portal.sqlite is never touched.
"""
import os
import tempfile
import unittest

from portal import create_app


class PortalTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "DATABASE": os.path.join(self.tmp.name, "test.sqlite"),
            "UPLOAD_FOLDER": os.path.join(self.tmp.name, "uploads"),
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def sign_in(self, role):
        return self.client.post(f"/login/as/{role}", follow_redirects=True)


class LoginTests(PortalTestCase):
    def test_login_page_loads(self):
        r = self.client.get("/login")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"PROTOTYPE ACCESS", r.data)

    def test_dealer_pages_require_login(self):
        r = self.client.get("/dealer")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_email_login(self):
        r = self.client.post("/login", data={"email": "syufaiq@example.com",
                                             "password": "x"},
                             follow_redirects=True)
        self.assertIn(b"Good", r.data)

    def test_unknown_email_rejected(self):
        r = self.client.post("/login", data={"email": "nobody@example.com",
                                             "password": "x"})
        self.assertIn(b"could not find", r.data)

    def test_inactive_user_rejected(self):
        r = self.client.post("/login", data={"email": "izzati@example.com",
                                             "password": "x"})
        self.assertIn(b"could not find", r.data)

    def test_processor_cannot_open_dealer_area(self):
        self.sign_in("processor")
        self.assertEqual(self.client.get("/dealer").status_code, 403)

    def test_logout(self):
        self.sign_in("dealer")
        self.client.get("/logout")
        self.assertEqual(self.client.get("/dealer").status_code, 302)


class DealerPageTests(PortalTestCase):
    def setUp(self):
        super().setUp()
        self.sign_in("dealer")

    def test_dashboard(self):
        r = self.client.get("/dealer")
        self.assertEqual(r.status_code, 200)
        html = r.data.decode()
        self.assertIn("1 order that needs correction", html)
        self.assertIn("ORD-2026-00128", html)
        self.assertIn("Draft last saved 18 Mar 2026, 8:20 AM", html)
        # amendment first, then the draft
        self.assertLess(html.index("ORD-2026-00128"), html.index("ORD-2026-00130"))

    def test_my_orders_shows_only_my_seven(self):
        html = self.client.get("/dealer/orders").data.decode()
        self.assertIn("Showing <b>1&ndash;7</b> of <b>7</b>", html)
        self.assertNotIn("ORD-2026-00129", html)  # belongs to Aina
        self.assertIn("Submission #2", html)

    def test_my_orders_sorted_by_last_updated(self):
        html = self.client.get("/dealer/orders").data.decode()
        order = ["00124", "00130", "00128", "00126", "00121", "00117", "00109"]
        positions = [html.index(f"ORD-2026-{n}") for n in order]
        self.assertEqual(positions, sorted(positions))

    def test_filter_by_status(self):
        html = self.client.get("/dealer/orders?status=Completed").data.decode()
        self.assertIn("ORD-2026-00117", html)
        self.assertNotIn("ORD-2026-00130", html)
        self.assertIn("of <b>2</b>", html)

    def test_filter_by_type_and_search(self):
        html = self.client.get("/dealer/orders?type=IoT").data.decode()
        self.assertIn("of <b>2</b>", html)
        html = self.client.get("/dealer/orders?q=00128").data.decode()
        self.assertIn("Damage Ctrl", html)
        self.assertIn("of <b>1</b>", html)

    def test_filter_no_results(self):
        html = self.client.get("/dealer/orders?q=zzzz").data.decode()
        self.assertIn("No orders match your filters", html)

    def test_sql_injection_attempt_is_harmless(self):
        r = self.client.get("/dealer/orders?q=' OR 1=1 --")
        self.assertEqual(r.status_code, 200)
        self.assertIn("No orders match", r.data.decode())

    def test_top_search_redirects(self):
        r = self.client.get("/dealer/search?q=00124")
        self.assertEqual(r.status_code, 302)
        self.assertIn("q=00124", r.headers["Location"])

    def test_every_order_every_tab_loads(self):
        for n in ["00109", "00117", "00121", "00124", "00126", "00128", "00130"]:
            for tab in ["overview", "customer", "subscription", "documents", "activity"]:
                r = self.client.get(f"/dealer/orders/ORD-2026-{n}?tab={tab}")
                self.assertEqual(r.status_code, 200, f"{n} {tab}")

    def test_unknown_tab_falls_back_to_overview(self):
        r = self.client.get("/dealer/orders/ORD-2026-00126?tab=hax")
        self.assertEqual(r.status_code, 200)

    def test_amendment_order(self):
        html = self.client.get("/dealer/orders/ORD-2026-00128").data.decode()
        self.assertIn("Returned 17 Mar 2026, 3:24 PM by Farina Elia", html)
        self.assertIn("Edit and Resubmit", html)
        self.assertIn("RM 1,914.00", html)
        self.assertIn("RM 1,800.00", html)
        self.assertIn("Awaiting Dealer correction", html)
        self.assertIn("CORRECTION REQUESTED", html)
        docs = self.client.get("/dealer/orders/ORD-2026-00128?tab=documents").data.decode()
        self.assertIn("4 of 5 required documents uploaded", docs)
        self.assertIn("Missing", docs)

    def test_draft_order(self):
        html = self.client.get("/dealer/orders/ORD-2026-00130").data.decode()
        self.assertIn("Continue draft", html)
        self.assertIn("RM 408.00", html)
        docs = self.client.get("/dealer/orders/ORD-2026-00130?tab=documents").data.decode()
        self.assertIn("3 of 5 required documents uploaded", docs)

    def test_submitted_order_is_locked(self):
        html = self.client.get("/dealer/orders/ORD-2026-00126").data.decode()
        self.assertIn("Editing locked", html)
        self.assertIn("Issued after approval", html)

    def test_under_review_order(self):
        html = self.client.get("/dealer/orders/ORD-2026-00124").data.decode()
        self.assertIn("Being validated by the processing team", html)
        self.assertIn("RM 640.00", html)
        self.assertIn("RM 900.00", html)
        docs = self.client.get("/dealer/orders/ORD-2026-00124?tab=documents").data.decode()
        self.assertIn("6 of 6 required documents uploaded", docs)  # Business Solution

    def test_approved_order_shows_reference(self):
        html = self.client.get("/dealer/orders/ORD-2026-00121").data.decode()
        self.assertIn("REF-MVP-77310", html)
        self.assertIn("Approved by", html)
        self.assertIn("11 Mar 2026, 11:00 AM", html)

    def test_completed_order_with_resolved_amendment(self):
        html = self.client.get("/dealer/orders/ORD-2026-00117").data.decode()
        self.assertIn("Resolved amendments", html)
        self.assertIn("Customer confirmed 50 tracker modules", html)
        self.assertIn("1 amendment cycle", html)
        self.assertIn("RM 1,250.00", html)
        self.assertIn("RM 1,750.00", html)
        act = self.client.get("/dealer/orders/ORD-2026-00117?tab=activity").data.decode()
        self.assertIn("Order marked completed", act)
        self.assertIn("Draft created", act)

    def test_sensitive_numbers_are_masked(self):
        html = self.client.get("/dealer/orders/ORD-2026-00126?tab=customer").data.decode()
        self.assertIn("2026******67", html)
        self.assertIn("*****4589", html)
        self.assertIn("******-**-1234", html)
        self.assertNotIn("202601234567", html)
        self.assertNotIn("900101-14-1234", html)

    def test_cannot_open_another_dealers_order(self):
        # ORD-2026-00129 belongs to Aina Rahman, not Syufaiq
        self.assertEqual(self.client.get("/dealer/orders/ORD-2026-00129").status_code, 404)
        self.assertEqual(self.client.get("/dealer/orders/ORD-2026-00129/edit").status_code, 404)
        self.assertEqual(self.client.get("/dealer/orders/NOPE").status_code, 404)

    def test_help(self):
        html = self.client.get("/dealer/help").data.decode()
        self.assertIn("Status glossary", html)
        self.assertIn("Which file types can I upload?", html)

    def test_sidebar_badge_counts_amendments(self):
        html = self.client.get("/dealer").data.decode()
        self.assertIn('<span class="nav-badge">1</span>', html)


class OtherRoleTests(PortalTestCase):
    def test_processor_and_admin_landing(self):
        self.sign_in("processor")
        r = self.client.get("/processor")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Processor workspace", r.data)
        self.assertIn(b"Work Queue", r.data)
        self.client.get("/logout")
        self.sign_in("admin")
        r = self.client.get("/admin")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Admin workspace", r.data)

    def test_seed_totals_match_pdf(self):
        from portal.db import get_db
        with self.app.app_context():
            db = get_db()
            counts = dict(db.execute(
                "SELECT status, COUNT(*) FROM orders GROUP BY status").fetchall())
            self.assertEqual(counts, {
                "Draft": 2, "Submitted": 4, "Under Review": 2,
                "Amendment Required": 2, "Approved": 2, "Completed": 4})
            self.assertEqual(db.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 16)


if __name__ == "__main__":
    unittest.main()
