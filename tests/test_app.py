import io
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

import app as platform


class PlatformTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        platform.app.config.update(
            TESTING=True,
            SECRET_KEY="test-session-key",
            DATABASE=str(root / "test.sqlite3"),
            UPLOAD_FOLDER=str(root / "uploads"),
        )
        with platform.app.app_context():
            platform.init_db()
        self.student = platform.app.test_client()
        self.admin = platform.app.test_client()
        self.register_student(self.student, "student@example.edu", "Student One")
        with platform.app.app_context():
            platform.get_db().execute(
                """INSERT INTO users (email, name, password_hash, role, department, semester, created_at)
                   VALUES (?, ?, ?, 'admin', '', '', ?)""",
                ("admin@example.edu", "Admin User", generate_password_hash("safe-test-password-123"), platform.utc_now()),
            )
            platform.get_db().commit()
        self.login(self.admin, "admin@example.edu", "safe-test-password-123")

    def tearDown(self):
        self.temp_dir.cleanup()

    def token(self, client):
        client.get("/")
        with client.session_transaction() as current:
            return current["_csrf_token"]

    def register_student(self, client, email, name):
        token = self.token(client)
        response = client.post(
            "/register",
            data={"csrf_token": token, "email": email, "name": name, "password": "safe-student-password-123"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

    def login(self, client, email, password):
        response = client.post(
            "/login",
            data={"csrf_token": self.token(client), "email": email, "password": password},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

    def upload_official(self, contents, version, department="Computer Science", semester="4"):
        response = self.admin.post(
            "/admin/documents",
            data={
                "csrf_token": self.token(self.admin),
                "title": "Academic Regulations",
                "version": version,
                "department": department,
                "semester": semester,
                "effective_date": f"2026-0{version}-01",
                "document": (io.BytesIO(contents.encode("utf-8")), "regulations.txt"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

    def test_document_answers_include_page_and_section_citations(self):
        self.upload_official("ATTENDANCE RULES:\nStudents must maintain at least 75 percent attendance.", "1")
        profile = self.student.post(
            "/profile",
            data={"csrf_token": self.token(self.student), "name": "Student One", "department": "Computer Science",
                  "year": "2nd year", "semester": "4", "courses": "Data Structures", "preferences": ""},
            follow_redirects=True,
        )
        self.assertEqual(profile.status_code, 200)
        response = self.student.post(
            "/ask",
            json={"query": "What attendance requirement applies to my semester?", "explain": True},
            headers={"X-CSRF-Token": self.token(self.student)},
        )
        result = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("75 percent attendance", result["answer"])
        self.assertTrue(any("Academic Regulations" in citation and "section ATTENDANCE RULES" in citation
                            for citation in result["citations"]))
        self.assertTrue(any(item.startswith("Semester: 4") for item in result["context_used"]))
        self.assertIn("Why this applies", result["answer"])
        self.assertIsNone(result["ticket_id"])

    def test_unsupported_question_creates_routed_ticket(self):
        response = self.student.post(
            "/ask",
            json={"query": "What is my highly unusual independent study approval process?"},
            headers={"X-CSRF-Token": self.token(self.student)},
        )
        result = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("could not verify", result["answer"])
        self.assertIsNotNone(result["ticket_id"])
        with platform.app.app_context():
            ticket = platform.get_db().execute("SELECT * FROM tickets WHERE id = ?", (result["ticket_id"],)).fetchone()
        self.assertEqual(ticket["status"], "Open")
        self.assertEqual(ticket["department"], "Student Services")

    def test_personal_documents_are_isolated_between_students(self):
        upload = self.student.post(
            "/documents/upload",
            data={"csrf_token": self.token(self.student), "document": (
                io.BytesIO(b"Private laboratory access phrase: violet-otter-932."), "private.txt"
            )},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(upload.status_code, 200)
        other_student = platform.app.test_client()
        self.register_student(other_student, "other@example.edu", "Student Two")
        response = other_student.post(
            "/ask",
            json={"query": "What is the violet otter laboratory access phrase?"},
            headers={"X-CSRF-Token": self.token(other_student)},
        )
        self.assertIn("could not verify", response.get_json()["answer"])
        self.assertNotIn("violet-otter-932", response.get_data(as_text=True))
        dashboard = other_student.get("/").get_data(as_text=True)
        self.assertNotIn("private.txt", dashboard)

    def test_comparison_cites_both_document_versions(self):
        self.upload_official("ATTENDANCE RULES:\nStudents must maintain at least 75 percent attendance.", "1")
        with platform.app.app_context():
            old_id = platform.get_db().execute("SELECT id FROM documents WHERE version = '1'").fetchone()["id"]
        self.upload_official("ATTENDANCE RULES:\nStudents must maintain at least 80 percent attendance.", "2")
        with platform.app.app_context():
            new_id = platform.get_db().execute("SELECT id FROM documents WHERE version = '2'").fetchone()["id"]
        response = self.student.post(
            "/compare",
            json={"old_id": old_id, "new_id": new_id},
            headers={"X-CSRF-Token": self.token(self.student)},
        )
        result = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(result["effective_date"], "2026-02-01")
        citations = result["changes"][0]["citations"]
        self.assertTrue(any("Academic Regulations" in citation and "version 1" in citation for citation in citations))
        self.assertTrue(any("Academic Regulations" in citation and "version 2" in citation for citation in citations))
        self.assertTrue(result["affected"])

    def test_admin_document_management_and_role_boundaries(self):
        self.upload_official("LIBRARY RULES:\nBooks may be renewed once.", "1")
        with platform.app.app_context():
            document_id = platform.get_db().execute("SELECT id FROM documents").fetchone()["id"]
        forbidden = self.student.post(
            f"/admin/documents/{document_id}/archive",
            data={"csrf_token": self.token(self.student)},
        )
        self.assertEqual(forbidden.status_code, 403)
        archived = self.admin.post(
            f"/admin/documents/{document_id}/archive",
            data={"csrf_token": self.token(self.admin)},
            follow_redirects=True,
        )
        self.assertEqual(archived.status_code, 200)
        self.assertIn("ARCHIVED", archived.get_data(as_text=True))

    def test_intent_and_entities_are_extracted(self):
        domain, entities = platform.detect_intent(
            "When is the mid-term exam in semester 4 for CS204 on 2026-11-03?"
        )
        self.assertEqual(domain, "Exams")
        self.assertEqual(entities["semester"], "4")
        self.assertEqual(entities["exam_type"], "mid-term")
        self.assertEqual(entities["course"], "CS204")
        self.assertEqual(entities["date"], "2026-11-03")

    def test_metadata_inference_and_email_validation(self):
        metadata = platform.infer_document_metadata(
            "Academic year 2025-26\nSemester: 4\nEffective from: 2026-08-01\nDepartment of Computer Science",
            "regulations-v2.txt",
        )
        self.assertEqual(metadata["academic_year"], "2025-26")
        self.assertEqual(metadata["semester"], "4")
        self.assertEqual(metadata["effective_date"], "2026-08-01")
        self.assertEqual(metadata["department"], "Computer Science")
        self.assertEqual(metadata["version"], "2")
        self.assertTrue(platform.valid_email("student@example.edu"))
        self.assertFalse(platform.valid_email("not-an-email"))

    def test_admin_cli_and_ticket_staff_workflow(self):
        cli_result = platform.app.test_cli_runner().invoke(
            args=[
                "create-admin",
                "--email", "new-admin@example.edu",
                "--name", "New Admin",
                "--password", "another-secure-password-123",
            ]
        )
        self.assertEqual(cli_result.exit_code, 0, cli_result.output)
        ticket_response = self.student.post(
            "/tickets",
            data={
                "csrf_token": self.token(self.student),
                "subject": "Urgent fee payment issue",
                "message": "Please review my payment before today's deadline.",
            },
            follow_redirects=True,
        )
        self.assertEqual(ticket_response.status_code, 200)
        with platform.app.app_context():
            ticket = platform.get_db().execute(
                "SELECT * FROM tickets WHERE subject = ?", ("Urgent fee payment issue",)
            ).fetchone()
        self.assertEqual(ticket["department"], "Fees")
        self.assertEqual(ticket["priority"], "High")
        updated = self.admin.post(
            f"/tickets/{ticket['id']}/update",
            data={
                "csrf_token": self.token(self.admin),
                "status": "Closed",
                "staff_response": "Payment verified by the fee office.",
            },
            follow_redirects=True,
        )
        self.assertEqual(updated.status_code, 200)
        student_dashboard = self.student.get("/").get_data(as_text=True)
        self.assertIn("Payment verified by the fee office.", student_dashboard)


if __name__ == "__main__":
    unittest.main()
