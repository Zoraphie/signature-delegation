from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import exists, select

from models import DocumentUserLink, Document, Delegation

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
