from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import exists, select

from models import DocumentUserLink, Document

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
