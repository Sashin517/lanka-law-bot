from __future__ import annotations

import base64
import json
import re
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.draft import (
    DraftContextSnapshot,
    DraftDocument,
    DraftDocumentChange,
    DraftDocumentVersion,
)
from app.schemas.drafts import (
    AgentEditDocumentResponse,
    CreateDraftDocumentRequest,
    DraftChangeResponse,
    DraftDocumentListItem,
    DraftDocumentResponse,
    DraftDocumentSpec,
    DraftExportFormat,
    DraftVersionResponse,
    ExportDocumentResponse,
    GenerateDocumentsRequest,
    GenerateDocumentsResponse,
    UpdateDraftDocumentRequest,
)
from app.services.agent_edit_operations import AgentEditOperationService
from app.services.document_converter import DocumentConverter
from app.services.draft_coordinator import DraftGenerationCoordinator

LOCAL_TENANT_ID = "local"
LOCAL_USER_ID = "local_user"

_GRAPH = None


class DraftNotFoundError(ValueError):
    pass


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        from app.agents.graph import build_graph

        _GRAPH = build_graph()
    return _GRAPH


class DraftWorkspaceService:
    def __init__(
        self,
        converter: DocumentConverter | None = None,
        coordinator: DraftGenerationCoordinator | None = None,
        operation_service: AgentEditOperationService | None = None,
    ) -> None:
        self.converter = converter or DocumentConverter()
        self.coordinator = coordinator or DraftGenerationCoordinator()
        self.operation_service = operation_service or AgentEditOperationService(self.converter)

    def create_document(
        self,
        db: Session,
        request: CreateDraftDocumentRequest,
    ) -> DraftDocumentResponse:
        document = DraftDocument(
            id=str(uuid4()),
            tenant_id=LOCAL_TENANT_ID,
            user_id=LOCAL_USER_ID,
            matter_id=request.matter_id,
            title=request.title,
            document_type=request.document_type or "unknown",
            status="draft",
            editor_json=_dump_json(
                request.editor_json
                or self.converter.markdown_to_tiptap_json(request.markdown_content)
            ),
            markdown_content=request.markdown_content
            or self.converter.tiptap_json_to_markdown(request.editor_json),
            html_content=request.html_content
            or self.converter.markdown_to_html(request.markdown_content),
            created_by=request.created_by,
        )
        db.add(document)
        db.flush()
        self._create_version(
            db=db,
            document=document,
            changed_by=request.created_by,
            change_summary=request.change_summary,
        )
        db.commit()
        db.refresh(document)
        return self.to_document_response(db, document)

    def list_documents(
        self,
        db: Session,
        matter_id: str | None = None,
    ) -> list[DraftDocumentListItem]:
        query = db.query(DraftDocument).filter(
            DraftDocument.tenant_id == LOCAL_TENANT_ID,
            DraftDocument.user_id == LOCAL_USER_ID,
        )
        if matter_id:
            query = query.filter(DraftDocument.matter_id == matter_id)
        documents = query.order_by(DraftDocument.updated_at.desc()).all()
        return [self.to_list_item(db, document) for document in documents]

    def get_document(self, db: Session, draft_id: str) -> DraftDocument:
        document = (
            db.query(DraftDocument)
            .filter(
                DraftDocument.id == draft_id,
                DraftDocument.tenant_id == LOCAL_TENANT_ID,
                DraftDocument.user_id == LOCAL_USER_ID,
            )
            .first()
        )
        if not document:
            raise DraftNotFoundError("Draft document not found.")
        return document

    def update_document(
        self,
        db: Session,
        draft_id: str,
        request: UpdateDraftDocumentRequest,
    ) -> DraftDocumentResponse:
        document = self.get_document(db, draft_id)
        before = _document_fingerprint(document)

        if request.title is not None:
            document.title = request.title
        if request.document_type is not None:
            document.document_type = request.document_type or "unknown"
        if request.status is not None:
            document.status = request.status
        if request.editor_json is not None:
            document.editor_json = _dump_json(request.editor_json)
            if request.markdown_content is None:
                document.markdown_content = self.converter.tiptap_json_to_markdown(
                    request.editor_json
                )
        if request.markdown_content is not None:
            document.markdown_content = request.markdown_content
        if request.html_content is not None:
            document.html_content = request.html_content
        elif request.markdown_content is not None or request.editor_json is not None:
            document.html_content = self.converter.markdown_to_html(
                document.markdown_content
            )

        if _document_fingerprint(document) != before:
            self._create_version(
                db=db,
                document=document,
                changed_by="user",
                change_summary=request.change_summary,
            )

        db.commit()
        db.refresh(document)
        return self.to_document_response(db, document)

    def list_versions(self, db: Session, draft_id: str) -> list[DraftVersionResponse]:
        self.get_document(db, draft_id)
        versions = (
            db.query(DraftDocumentVersion)
            .filter(DraftDocumentVersion.document_id == draft_id)
            .order_by(DraftDocumentVersion.version_number.desc())
            .all()
        )
        return [self.to_version_response(version) for version in versions]

    async def generate_documents(
        self,
        db: Session,
        request: GenerateDocumentsRequest,
    ) -> GenerateDocumentsResponse:
        specs = self.coordinator.resolve_specs(request)
        documents: list[DraftDocumentResponse] = []

        for spec in specs:
            question = self.coordinator.compose_generation_question(request.prompt, spec)
            generated = await _run_drafting_graph(
                question=question,
                matter_id=request.matter_id,
                document_ids=request.document_ids,
                document_specs=[spec.model_dump()],
            )
            draft_payload = (generated.get("draft_documents") or [{}])[0]
            markdown = (
                draft_payload.get("draft_markdown")
                or generated["markdown_content"]
                or generated["answer"]
            )
            if not markdown:
                markdown = f"# {spec.title}\n\n{spec.instructions or request.prompt}"

            source_refs = generated.get("sources", [])
            title = draft_payload.get("title") or generated.get("draft_title") or spec.title
            document_type = (
                draft_payload.get("document_type")
                or generated.get("draft_document_type")
                or spec.document_type
                or "draft"
            )
            document = DraftDocument(
                id=str(uuid4()),
                tenant_id=LOCAL_TENANT_ID,
                user_id=LOCAL_USER_ID,
                matter_id=request.matter_id,
                title=title,
                document_type=document_type,
                status="draft",
                editor_json=_dump_json(self.converter.markdown_to_tiptap_json(markdown)),
                markdown_content=markdown,
                html_content=self.converter.markdown_to_html(markdown),
                created_by="agent",
            )
            db.add(document)
            db.flush()

            snapshot = DraftContextSnapshot(
                id=str(uuid4()),
                matter_id=request.matter_id,
                document_id=document.id,
                query=question,
                source_refs=_dump_json(source_refs),
                uploaded_document_ids=_dump_json(request.document_ids),
                retrieved_context="",
                agent_memory=_dump_json(
                    {
                        "prompt": request.prompt,
                        "document_spec": spec.model_dump(),
                        "section_map": draft_payload.get("section_map")
                        or generated.get("section_map", {}),
                        "requires_completion": draft_payload.get("requires_completion")
                        or generated.get("requires_completion", False),
                        "sources_used": draft_payload.get("sources_used")
                        or generated.get("sources_used", []),
                        "route": generated.get("route"),
                    }
                ),
            )
            db.add(snapshot)
            db.flush()

            self._create_version(
                db=db,
                document=document,
                changed_by="agent",
                change_summary=draft_payload.get("change_summary")
                or generated.get("change_summary")
                or f"Generated {title}.",
                context_snapshot_id=snapshot.id,
            )
            documents.append(self.to_document_response(db, document))

        db.commit()
        return GenerateDocumentsResponse(matter_id=request.matter_id, documents=documents)

    async def agent_edit_document(
        self,
        db: Session,
        draft_id: str,
        instruction: str,
        section_ids: list[str],
        track_changes: bool,
    ) -> AgentEditDocumentResponse:
        document = self.get_document(db, draft_id)
        question = _compose_edit_question(document, instruction, section_ids)
        generated = await _run_drafting_graph(
            question=question,
            matter_id=document.matter_id,
            document_ids=[],
        )
        new_markdown = generated["markdown_content"] or generated["answer"]
        if not new_markdown:
            new_markdown = document.markdown_content

        operation_set = self.operation_service.operation_set_from_revised_markdown(
            current_markdown=document.markdown_content,
            revised_markdown=new_markdown,
            instruction=instruction,
            section_ids=section_ids,
            sources_used=generated.get("sources_used", []),
        )
        applied = self.operation_service.apply_operations(
            current_markdown=document.markdown_content,
            operation_set=operation_set,
        )
        document.markdown_content = applied.markdown_content
        document.editor_json = _dump_json(applied.editor_json)
        document.html_content = applied.html_content

        snapshot = DraftContextSnapshot(
            id=str(uuid4()),
            matter_id=document.matter_id,
            document_id=document.id,
            query=question,
            source_refs=_dump_json(generated.get("sources", [])),
            uploaded_document_ids="[]",
            retrieved_context="",
            agent_memory=_dump_json(
                {
                    "instruction": instruction,
                    "scope": {"document_ids": [draft_id], "section_ids": section_ids},
                    "track_changes": track_changes,
                    "operations": operation_set.get("operations", []),
                    "sources_used": applied.sources_used,
                    "route": generated.get("route"),
                }
            ),
        )
        db.add(snapshot)
        db.flush()

        version = self._create_version(
            db=db,
            document=document,
            changed_by="agent",
            change_summary=applied.change_summary,
            context_snapshot_id=snapshot.id,
        )

        changes: list[DraftDocumentChange] = []
        if track_changes:
            for applied_change in applied.changes:
                change = DraftDocumentChange(
                    id=str(uuid4()),
                    document_id=document.id,
                    version_id=version.id,
                    operation_type=applied_change.operation_type,
                    target=_dump_json(applied_change.target),
                    before_text=applied_change.before_text,
                    after_text=applied_change.after_text,
                    rationale=applied_change.rationale,
                    changed_by="agent",
                )
                db.add(change)
                changes.append(change)

        db.commit()
        db.refresh(document)
        db.refresh(version)
        for change in changes:
            db.refresh(change)

        return AgentEditDocumentResponse(
            document=self.to_document_response(db, document),
            version=self.to_version_response(version),
            changes=[self.to_change_response(change) for change in changes],
            change_summary=version.change_summary,
        )

    async def batch_agent_edit(
        self,
        db: Session,
        document_ids: list[str],
        instruction: str,
        section_ids: list[str],
        track_changes: bool,
    ) -> list[AgentEditDocumentResponse]:
        return [
            await self.agent_edit_document(
                db=db,
                draft_id=document_id,
                instruction=instruction,
                section_ids=section_ids,
                track_changes=track_changes,
            )
            for document_id in document_ids
        ]

    def export_document(
        self,
        db: Session,
        draft_id: str,
        export_format: DraftExportFormat,
    ) -> ExportDocumentResponse:
        document = self.get_document(db, draft_id)
        filename_base = _safe_filename(document.title or "draft-document")

        if export_format == "markdown":
            content = document.markdown_content.encode("utf-8")
            content_type = "text/markdown; charset=utf-8"
            filename = f"{filename_base}.md"
        elif export_format == "html":
            content = (
                document.html_content
                or self.converter.markdown_to_html(document.markdown_content)
            ).encode("utf-8")
            content_type = "text/html; charset=utf-8"
            filename = f"{filename_base}.html"
        elif export_format == "docx":
            content = self.converter.tiptap_json_to_docx(
                document.title,
                _load_json(document.editor_json, {}),
            )
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            filename = f"{filename_base}.docx"
        else:
            content = self.converter.html_to_pdf(
                document.title,
                document.html_content
                or self.converter.markdown_to_html(document.markdown_content),
            )
            content_type = "application/pdf"
            filename = f"{filename_base}.pdf"

        return ExportDocumentResponse(
            document_id=document.id,
            filename=filename,
            format=export_format,
            content_type=content_type,
            content_base64=base64.b64encode(content).decode("ascii"),
        )

    def to_document_response(
        self,
        db: Session,
        document: DraftDocument,
    ) -> DraftDocumentResponse:
        return DraftDocumentResponse(
            document_id=document.id,
            matter_id=document.matter_id,
            title=document.title,
            document_type=document.document_type,
            status=document.status,
            editor_json=_load_json(document.editor_json, {}),
            markdown_content=document.markdown_content,
            html_content=document.html_content,
            created_by=document.created_by,
            created_at=document.created_at,
            updated_at=document.updated_at,
            current_version=self._current_version_number(db, document.id),
        )

    def to_list_item(self, db: Session, document: DraftDocument) -> DraftDocumentListItem:
        return DraftDocumentListItem(
            document_id=document.id,
            matter_id=document.matter_id,
            title=document.title,
            document_type=document.document_type,
            status=document.status,
            created_by=document.created_by,
            created_at=document.created_at,
            updated_at=document.updated_at,
            current_version=self._current_version_number(db, document.id),
        )

    def to_version_response(self, version: DraftDocumentVersion) -> DraftVersionResponse:
        return DraftVersionResponse(
            version_id=version.id,
            document_id=version.document_id,
            version_number=version.version_number,
            markdown_content=version.markdown_content,
            change_summary=version.change_summary,
            changed_by=version.changed_by,
            agent_run_id=version.agent_run_id,
            context_snapshot_id=version.context_snapshot_id,
            created_at=version.created_at,
        )

    def to_change_response(self, change: DraftDocumentChange) -> DraftChangeResponse:
        return DraftChangeResponse(
            change_id=change.id,
            document_id=change.document_id,
            version_id=change.version_id,
            operation_type=change.operation_type,
            target=change.target,
            before_text=change.before_text,
            after_text=change.after_text,
            rationale=change.rationale,
            changed_by=change.changed_by,
            created_at=change.created_at,
        )

    def _create_version(
        self,
        db: Session,
        document: DraftDocument,
        changed_by: str,
        change_summary: str,
        context_snapshot_id: str | None = None,
        agent_run_id: str | None = None,
    ) -> DraftDocumentVersion:
        version_number = self._current_version_number(db, document.id) + 1
        version = DraftDocumentVersion(
            id=str(uuid4()),
            document_id=document.id,
            version_number=version_number,
            editor_json=document.editor_json,
            markdown_content=document.markdown_content,
            change_summary=change_summary,
            changed_by=changed_by,
            agent_run_id=agent_run_id,
            context_snapshot_id=context_snapshot_id,
        )
        db.add(version)
        db.flush()
        return version

    def _current_version_number(self, db: Session, document_id: str) -> int:
        value = (
            db.query(func.max(DraftDocumentVersion.version_number))
            .filter(DraftDocumentVersion.document_id == document_id)
            .scalar()
        )
        return int(value or 0)


async def _run_drafting_graph(
    question: str,
    matter_id: str | None,
    document_ids: list[str],
    document_specs: list[dict] | None = None,
) -> dict:
    try:
        from app.agents.state import AgentState

        initial_state = AgentState(
            question=question,
            mode="drafting",
            document_ids=document_ids,
            matter_id=matter_id,
            document_specs=document_specs or [],
        )
        final_state = await get_graph().ainvoke(initial_state.model_dump())
        final_response = final_state.get("final_response") or {}
        return {
            "answer": final_response.get("answer", ""),
            "markdown_content": final_response.get("markdown_content", ""),
            "sources": final_response.get("sources", []),
            "route": final_response.get("route"),
            "draft_documents": final_response.get("draft_documents", []),
            "draft_title": final_response.get("draft_title", ""),
            "draft_document_type": final_response.get("draft_document_type", ""),
            "sources_used": final_response.get("sources_used", []),
            "requires_completion": final_response.get("requires_completion", False),
            "section_map": final_response.get("section_map", {}),
            "change_summary": final_response.get("change_summary", ""),
        }
    except Exception as exc:
        return {
            "answer": "",
            "markdown_content": "",
            "sources": [],
            "route": {"error": str(exc)},
            "draft_documents": [],
            "draft_title": "",
            "draft_document_type": "",
            "sources_used": [],
            "requires_completion": False,
            "section_map": {},
            "change_summary": "",
        }


def _compose_edit_question(
    document: DraftDocument,
    instruction: str,
    section_ids: list[str],
) -> str:
    scope = ", ".join(section_ids) if section_ids else "the full document"
    return (
        "Revise the existing legal draft according to the instruction below.\n\n"
        f"Instruction: {instruction}\n"
        f"Scope: {scope}\n\n"
        "Return the complete revised document, not only the changed text.\n\n"
        f"Existing document:\n{document.markdown_content}"
    )


def _document_fingerprint(document: DraftDocument) -> tuple[str, str, str, str, str]:
    return (
        document.title,
        document.document_type,
        document.status,
        document.editor_json,
        document.markdown_content,
    )


def _dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load_json(value: str | None, fallback: object) -> object:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _safe_filename(title: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-._")
    return value or "draft-document"
