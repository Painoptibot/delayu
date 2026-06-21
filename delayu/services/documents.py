"""M05 — документы: версии, подпись, привязка к делу."""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from delayu.models import DocumentFile


def _q_root(root_pk):
    return Q(pk=root_pk) | Q(root_document_id=root_pk)


def _next_version(root):
    last = (
        DocumentFile.objects.filter(_q_root(root.pk))
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
    )
    return (last or 0) + 1


@transaction.atomic
def create_document(*, subsystem, user, title, doc_type, description, case, file):
    from delayu.services.upload_validation import file_sha256

    sha = file_sha256(file) if file else ""
    doc = DocumentFile.objects.create(
        subsystem=subsystem,
        case=case,
        title=title,
        doc_type=doc_type,
        description=description or "",
        file=file,
        content_sha256=sha,
        version=1,
        is_current=True,
        uploaded_by=user,
        root_document=None,
    )
    scan_document_on_upload(doc)
    _sync_document_index(doc)
    return doc


def scan_document_on_upload(document: DocumentFile):
    """M79 — автоматическая AV-проверка после загрузки."""
    from delayu.services.exploitation import demo_scan_file

    name = document.file.name if document.file else document.title
    return demo_scan_file(
        subsystem=document.subsystem, filename=name, document=document
    )


@transaction.atomic
def upload_new_version(document: DocumentFile, user, file, title=None):
    from delayu.services.upload_validation import file_sha256

    if document.case_id and document.case.is_archived:
        raise ValueError("Нельзя добавить версию к документу архивного дела.")
    root = document.get_root()
    DocumentFile.objects.filter(_q_root(root.pk), is_current=True).update(is_current=False)
    new_doc = DocumentFile.objects.create(
        subsystem=root.subsystem,
        case=root.case,
        root_document=root,
        title=title or root.title,
        doc_type=root.doc_type,
        description=root.description,
        file=file,
        content_sha256=file_sha256(file) if file else "",
        version=_next_version(root),
        is_current=True,
        uploaded_by=user,
        is_signed=False,
        signature_meta={},
    )
    scan_document_on_upload(new_doc)
    _sync_document_index(new_doc)
    return new_doc


def find_duplicate_documents(subsystem, content_sha256: str, *, exclude_pk: int | None = None):
    if not content_sha256:
        return DocumentFile.objects.none()
    qs = DocumentFile.objects.filter(
        subsystem=subsystem, content_sha256=content_sha256, is_current=True
    ).select_related("case")
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs[:5]


def _sync_document_index(document: DocumentFile):
    if not document.is_current:
        return
    try:
        from delayu.services.search_index import _index_row

        _index_row(
            subsystem=document.subsystem,
            kind="document",
            object_id=document.pk,
            title=document.title,
            body=document.description or "",
        )
    except Exception:
        pass


def sign_document(document: DocumentFile, user):
    if document.case_id and document.case.is_archived:
        raise ValueError("Архивное дело: подпись недоступна.")
    document.is_signed = True
    document.signature_meta = {
        "signed_at": timezone.now().isoformat(),
        "signer": user.get_full_name() or user.username,
        "signer_id": user.pk,
        "demo": True,
    }
    document.save(update_fields=["is_signed", "signature_meta", "updated_at"])
    return document


def document_card_context(document: DocumentFile):
    from delayu.models import AvScanResult

    root = document.get_root()
    versions = list(
        DocumentFile.objects.filter(_q_root(root.pk))
        .select_related("uploaded_by", "case")
        .order_by("-version")
    )
    current = next((v for v in versions if v.is_current), versions[0] if versions else document)
    av_scan = (
        AvScanResult.objects.filter(document=current).order_by("-created_at").first()
    )
    return {
        "document": current,
        "root": root,
        "versions": versions,
        "case_archived": bool(current.case_id and current.case.is_archived),
        "av_scan": av_scan,
    }
