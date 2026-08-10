from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.api.api_routes import api_router
from app.api.endpoints.draft_routes import edit_draft
from app.schemas.requests import DraftEditRequest
from app.schemas.responses import DraftEditResponse


def _response(path: str) -> DraftEditResponse:
    return DraftEditResponse(
        edit_type="full_rewrite" if path == "heavy" else "replace",
        original_text="old",
        edited_text="new",
        markdown_content="new",
        edit_summary="Updated draft.",
        edit_path=path,
    )


class TestDraftEditRoutes(unittest.TestCase):
    def test_singular_draft_routes_are_registered(self):
        paths = {route.path for route in api_router.routes}
        self.assertIn("/api/draft/edit", paths)
        self.assertIn("/api/draft/versions", paths)
        self.assertIn("/api/draft/versions/{draft_id}", paths)
        self.assertIn("/api/drafts/{draft_id}", paths)

    def test_localized_instruction_routes_to_light_service(self):
        request = DraftEditRequest(
            draft_id="draft-1",
            instruction="Make this clearer",
            selected_text="old",
            current_content="old",
        )
        light = AsyncMock(return_value=_response("light"))
        heavy = AsyncMock(return_value=_response("heavy"))
        with (
            patch(
                "app.services.generation.draft_edit_service.process_light_edit",
                light,
            ),
            patch(
                "app.services.generation.draft_edit_service.process_heavy_edit",
                heavy,
            ),
        ):
            result = asyncio.run(edit_draft(request))

        self.assertEqual(result.edit_path, "light")
        light.assert_awaited_once_with(request)
        heavy.assert_not_awaited()

    def test_structural_instruction_routes_to_heavy_service(self):
        request = DraftEditRequest(
            draft_id="draft-1",
            instruction="Rewrite the entire document",
            current_content="old",
        )
        light = AsyncMock(return_value=_response("light"))
        heavy = AsyncMock(return_value=_response("heavy"))
        with (
            patch(
                "app.services.generation.draft_edit_service.process_light_edit",
                light,
            ),
            patch(
                "app.services.generation.draft_edit_service.process_heavy_edit",
                heavy,
            ),
        ):
            result = asyncio.run(edit_draft(request))

        self.assertEqual(result.edit_path, "heavy")
        heavy.assert_awaited_once_with(request)
        light.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
