"""Mapeo dominio -> DTO del feature `documents`. `drive_file_id`/`content_hash`
no se exponen al cliente: son detalles del proveedor de almacenamiento
(`sdd/fase4-nominas-documentos/design` — nunca se expone la URL/id de Drive)."""

from ..application.results import BulkFolderPlan, FolderBatchResult
from ..domain.models import Document, SyncRun
from .schemas import (
    BulkFolderPlanDTO,
    DocumentDTO,
    DocumentListDTO,
    FolderBatchResultDTO,
    FolderPlanEntryDTO,
    SyncRunDTO,
)


def document_to_dto(document: Document) -> DocumentDTO:
    return DocumentDTO(
        id=document.id,
        user_id=document.user_id,
        category=document.category,
        title=document.title,
        period=document.period,
        mime_type=document.mime_type,
        uploaded_by=document.uploaded_by,
        uploaded_at=document.uploaded_at,
        created_at=document.created_at,
    )


def documents_to_dto(documents: list[Document]) -> DocumentListDTO:
    return DocumentListDTO(documents=[document_to_dto(d) for d in documents])


def sync_run_to_dto(sync_run: SyncRun) -> SyncRunDTO:
    return SyncRunDTO(
        id=sync_run.id,
        started_at=sync_run.started_at,
        finished_at=sync_run.finished_at,
        status=sync_run.status,
        files_synced=sync_run.files_synced,
        error_detail=sync_run.error_detail,
    )


def folder_batch_result_to_dto(result: FolderBatchResult) -> FolderBatchResultDTO:
    return FolderBatchResultDTO(
        processed=result.processed,
        created=result.created,
        relocated=result.relocated,
        failed=result.failed,
        remaining=result.remaining,
    )


def bulk_folder_plan_to_dto(plan: BulkFolderPlan) -> BulkFolderPlanDTO:
    return BulkFolderPlanDTO(
        entries=[
            FolderPlanEntryDTO(
                user_id=entry.user_id,
                email=entry.email,
                entity_name=entry.entity_name,
                action=entry.action,
            )
            for entry in plan.entries
        ],
        entity_folders_to_create=plan.entity_folders_to_create,
        pending=plan.pending,
        already_done=plan.already_done,
        to_create=plan.to_create,
        to_move=plan.to_move,
        category_folders_to_create=plan.category_folders_to_create,
        estimated_drive_writes=plan.estimated_drive_writes,
    )
