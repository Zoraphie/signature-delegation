from sqlalchemy.ext.asyncio import AsyncSession

from models import DocumentUserLink

async def create_document_links(session: AsyncSession, links: list[DocumentUserLink], commit: bool = True):
    session.add_all(links)
    if commit:
        await session.commit()
    (await session.refresh(link) for link in links)
