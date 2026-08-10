from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.draft import DraftDocument
from app.schemas.responses import DraftVersionSnapshot
from app.services.draft_versions import DraftVersionConflictError, DraftVersionService


class TestDraftVersionService(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.session.add(
            DraftDocument(
                id="draft-1",
                tenant_id="local",
                user_id="local-user",
                title="Agreement",
                document_type="contract",
                status="draft",
                editor_json="{}",
                markdown_content="",
                html_content="",
                created_by="agent",
            )
        )
        self.session.commit()
        self.service = DraftVersionService()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _snapshot(self, number: int, parent: str | None) -> DraftVersionSnapshot:
        return DraftVersionSnapshot(
            id=f"version-{number}",
            draft_id="draft-1",
            version_number=number,
            content_json={"type": "doc", "content": []},
            content_markdown=f"Version {number}",
            sources=[{"citation_id": "[LAW-1]"}],
            created_at=f"2026-08-10T10:0{number}:00Z",
            created_by="ai" if number > 1 else "user",
            edit_summary=f"Saved version {number}.",
            parent_version_id=parent,
        )

    def test_snapshots_are_persisted_as_a_linked_chain(self):
        first_request = self._snapshot(1, None)
        first = self.service.save(self.session, first_request)
        second = self.service.save(self.session, self._snapshot(2, first.id))

        versions = self.service.list_for_draft(self.session, "draft-1")
        self.assertEqual([item.version_number for item in versions], [1, 2])
        self.assertEqual(second.parent_version_id, first.id)
        self.assertEqual(second.sources, [{"citation_id": "[LAW-1]"}])
        self.assertEqual(second.created_by, "ai")

        # The same immutable request is idempotent despite equivalent Z/+00:00 formats.
        repeated = self.service.save(self.session, first_request)
        self.assertEqual(repeated.id, first.id)

    def test_out_of_order_version_is_rejected(self):
        with self.assertRaises(DraftVersionConflictError):
            self.service.save(self.session, self._snapshot(2, None))


if __name__ == "__main__":
    unittest.main()
