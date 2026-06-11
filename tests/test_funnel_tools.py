import sqlite3
import tempfile
import unittest
from pathlib import Path

from funnel_tools import (
    audit_site_html,
    build_dashboard_model,
    build_fallback_site,
    build_gallery_html,
    extract_html_document,
)


class FunnelToolsTest(unittest.TestCase):
    def test_extract_html_document_strips_markdown_and_preface(self):
        raw = "Generated for you.\n```html\n<!DOCTYPE html>\n<html><body>OK</body></html>\n```"

        result = extract_html_document(raw)

        self.assertEqual(result, "<!DOCTYPE html>\n<html><body>OK</body></html>")

    def test_audit_site_html_flags_truncated_documents(self):
        issues = audit_site_html("<!DOCTYPE html>\n<html><body><section>Services")

        self.assertIn("missing_closing_html", issues)
        self.assertIn("missing_contact_link", issues)

    def test_build_fallback_site_uses_actual_lead_contact_data(self):
        lead = {
            "company_name": "Dental Excellence",
            "category": "Dentist",
            "website_style": "clean, modern, calming",
            "website_goal": "book_appointment",
            "phone": "064 1838998",
            "email": "marko.mirkovicdentist@gmail.com",
            "address": "Novi Sad",
            "services": ["Extraction"],
            "usp": ["Exceptional 4.7-star rating from customers"],
            "review_summary": "Professional, kind, recommended",
        }

        html = build_fallback_site(lead)

        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertTrue(html.rstrip().endswith("</html>"))
        self.assertIn("Dental Excellence", html)
        self.assertIn("mailto:marko.mirkovicdentist@gmail.com", html)
        self.assertIn("tel:0641838998", html)
        self.assertEqual(audit_site_html(html), [])

    def test_build_gallery_html_uses_real_folder_names(self):
        sites = [
            {
                "folder": "004_kljuc╠Мar",
                "name": "Ključar",
                "category": "Locksmith",
                "email": "a@example.com",
                "score": 97,
                "issues": [],
            }
        ]

        html = build_gallery_html(sites)

        self.assertIn("Total websites: <span>1</span>", html)
        self.assertIn('href="004_kljuc╠Мar/index.html"', html)

    def test_build_dashboard_model_counts_funnel_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "businesses.sqlite"
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE businesses (
                    business_id TEXT,
                    business_name TEXT,
                    category TEXT,
                    email TEXT,
                    email_source TEXT,
                    has_website INTEGER,
                    is_active INTEGER,
                    lead_status TEXT,
                    purchase_probability_score INTEGER
                )
                """
            )
            conn.executemany(
                "INSERT INTO businesses VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    ("1", "A", "Dentist", "a@example.com", "duckduckgo", 0, 1, "HIGH_PRIORITY", 99),
                    ("2", "B", "Plumber", "", "", 0, 1, "HIGH_PRIORITY", 91),
                    ("3", "C", "Cafe", None, None, 1, 1, "LOW", 20),
                ],
            )
            conn.commit()
            conn.close()

            model = build_dashboard_model(db_path, generated_count=1, email_count=1)

        self.assertEqual(model["metrics"]["total_businesses"], 3)
        self.assertEqual(model["metrics"]["active_no_website"], 2)
        self.assertEqual(model["metrics"]["high_priority"], 2)
        self.assertEqual(model["metrics"]["high_priority_with_email"], 1)
        self.assertEqual(model["metrics"]["generated_sites"], 1)


if __name__ == "__main__":
    unittest.main()
