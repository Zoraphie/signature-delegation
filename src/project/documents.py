from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import exists, select, update
from datetime import datetime, timezone

from project.models import DocumentUserLink, Document, Delegation, User

async def create_document_links(session: AsyncSession, links: list[DocumentUserLink], commit: bool = True):
    """
    Add DocumentUserLink instances to the session and optionally commit.

    Args:
        session: AsyncSession used to persist the links.
        links: List of DocumentUserLink instances to add.
        commit: If True, commit the transaction after adding.
    """
    session.add_all(links)
    if commit:
        await session.commit()
    (await session.refresh(link) for link in links)

async def is_owner(session: AsyncSession, user_id: int, document_id: str) -> bool | None:
    """
    Return whether a given user is the creator (owner) of a document.

    Args:
        session: AsyncSession used to run the query.
        user_id: ID of the user to check.
        document_id: ID of the document to check ownership for.

    Returns:
        True if the user is the document creator, False otherwise, or None if unknown.
    """
    query = select(exists().where(
        Document.id == document_id, Document.created_by == user_id
    ))
    result = await session.execute(query)
    return result.scalar()

async def get_pending_signatures_db(session: AsyncSession, user_id: int) -> list[Document]:
    """
    Return all documents that require a signature from the given user,
    including those assigned directly and those available via delegation.

    Args:
        session: AsyncSession used to run the queries.
        user_id: ID of the user for whom to fetch pending signatures.

    Returns:
        List of Document instances pending signature by the user.
    """
    return await get_signature_documents(session, user_id) + await get_signature_delegated_documents(session, user_id)

async def get_signature_documents(session: AsyncSession, user_id: int) -> list[Document]:
    """
    Return documents where the specified user has direct signing permission and has not signed yet.

    Args:
        session: AsyncSession used to run the query.
        user_id: ID of the user for whom to fetch pending signatures.

    Returns:
        List of distinct Document instances the user was asked to sign.
    """
    query = (
        select(Document)
        .join(DocumentUserLink)
        .where(
            DocumentUserLink.user_id == user_id,
            DocumentUserLink.permission_type == "sign",
            DocumentUserLink.signed_by == None
        )
        .distinct()
    )
    result = await session.execute(query)
    return result.scalars().all()

async def get_signature_delegated_documents(session: AsyncSession, user_id: int) -> list[Document]:
    """
    Return documents the specified user can sign because they are a delegate.

    Args:
        session: AsyncSession used to run the query.
        user_id: ID of the delegated user.

    Returns:
        List of distinct Document instances the user can sign via delegation.
    """
    query = (
        select(Document)
        .join(DocumentUserLink, DocumentUserLink.document_id == Document.id)
        .join(Delegation, Delegation.user_id_owner == DocumentUserLink.user_id)
        .where(
            DocumentUserLink.permission_type == "sign",
            Delegation.user_id_delegate == user_id,
            DocumentUserLink.signed_by == None
        )
        .distinct()
    )
    result = await session.execute(query)
    return result.scalars().all()

async def sign_document(session: AsyncSession, user_id: int, signing_user_id: int, document_id: int, commit: bool = True):
    """
    Mark a DocumentUserLink as signed by a user and update document status if all signatures are complete.

    Args:
        session: AsyncSession used to perform updates.
        user_id: ID of the user entry on the DocumentUserLink requested to sign a document.
        signing_user_id: ID of the user who performed the signature (could be a delegate).
        document_id: ID of the document being signed.
        commit: If True, commit the transaction after updates.
    """
    # Update DocumentUserLink entry to notify the document has been signed
    now = datetime.now(timezone.utc)
    await session.execute(
        update(DocumentUserLink)
        .where(
            DocumentUserLink.permission_type == "sign",
            DocumentUserLink.user_id == user_id,
            DocumentUserLink.document_id == document_id
        )
        .values(signed_by=signing_user_id, signed_at=now)
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
    """
    Return owners (users) who are signers for a document and for whom the given user is a delegate.

    Args:
        session: AsyncSession used to run the query.
        document_id: ID of the document to inspect.
        user_id: ID of the delegate user.

    Returns:
        List of User instances representing the owner(s) the delegate can sign for.
    """
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
