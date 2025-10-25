from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import exists, select, update
from sqlalchemy.orm import aliased

from models import DocumentUserLink, Document, Delegation, User

async def create_document_links(session: AsyncSession, links: list[DocumentUserLink], commit: bool = True):
    session.add_all(links)
    if commit:
        await session.commit()
    (await session.refresh(link) for link in links)

async def is_owner(session: AsyncSession, user_id: int, document_id: str) -> bool | None:
    query = select(exists().where(
        Document.id == document_id, Document.created_by == user_id
    ))
    result = await session.execute(query)
    return result.scalar()

async def get_pending_signatures_db(session: AsyncSession, user_id) -> list[Document]:
    return await get_signature_documents(session, user_id) + await get_signature_delegated_documents(session, user_id)

async def get_signature_documents(session: AsyncSession, user_id: int) -> list[Document]:
    query = (
        select(Document)
        .join(DocumentUserLink)
        .where(
            DocumentUserLink.user_id == user_id,
            DocumentUserLink.permission_type == "sign",
        )
        .distinct()
    )
    result = await session.execute(query)
    return result.scalars().all()

async def get_signature_delegated_documents(session: AsyncSession, user_id: int) -> list[Document]:
    query = (
        select(Document)
        .join(DocumentUserLink, DocumentUserLink.document_id == Document.id)
        .join(Delegation, Delegation.user_id_owner == DocumentUserLink.user_id)
        .where(
            DocumentUserLink.permission_type == "sign",
            Delegation.user_id_delegate == user_id,
        )
        .distinct()
    )
    result = await session.execute(query)
    return result.scalars().all()

async def sign_document(session: AsyncSession, user_id: int, signing_user_id: int, document_id: int, commit: bool = True):
    # Update DocumentUserLink entry to notify the document has been signed
    await session.execute(
        update(DocumentUserLink)
        .where(
            DocumentUserLink.permission_type == "sign",
            DocumentUserLink.user_id == user_id,
            DocumentUserLink.document_id == document_id
        )
        .values(signed_by=signing_user_id)
    )

    # Check if there is any remaining signatures needed on this document
    result = await session.execute(
        select(DocumentUserLink.id)
        .where(
            DocumentUserLink.document_id == document_id,
            DocumentUserLink.permission_type == "sign",
            DocumentUserLink.signed_by == None
        )
        .limit(1)
    )
    signatures_remaning = result.scalar() is not None
    if not signatures_remaning:
        await session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status="signed")
        )
    if commit:
        await session.commit()

async def get_delegation_signing_user(session: AsyncSession, document_id: int, user_id: int) -> list[User]:
    query = (
        select(User)
        .join(DocumentUserLink, DocumentUserLink.user_id == User.id)
        .join(Delegation, Delegation.user_id_owner == User.id)
        .where(
            DocumentUserLink.document_id == document_id,
            DocumentUserLink.permission_type == "sign",
            Delegation.user_id_delegate == user_id,
        )
        .distinct()
    )

    result = await session.execute(query)
    owners = result.scalars().all()
    return owners
