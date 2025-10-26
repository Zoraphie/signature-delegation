from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from project.models import Delegation

async def get_user_delegation(session: AsyncSession, user_id: int) -> list[Delegation]:
    """
    Return delegations where the given user is the owner.

    Args:
        session: AsyncSession used to query the database.
        user_id: ID of the owner whose delegations to fetch.

    Returns:
        List of Delegation instances owned by the specified user.
    """
    result = await session.execute((
        select(Delegation)
        .where(Delegation.user_id_owner == user_id)
    ))
    return [delegation[0] for delegation in result.all()]

async def get_user_delegation_as_delegated(session: AsyncSession, user_id: int, bounded_only: bool = False) -> list[Delegation]:
    """
    Return delegations where the given user is the delegate.

    Args:
        session: AsyncSession used to query the database.
        user_id: ID of the delegate user.
        bounded_only: If True, return only delegations that are bounded.

    Returns:
        List of Delegation instances where the specified user is the delegate.
    """
    query = select(Delegation).where(Delegation.user_id_delegate == user_id)
    if bounded_only:
        query = query.where(Delegation.bounded == True)
    result = await session.execute(query)
    return [delegation[0] for delegation in result.all()]

async def create_db_delegation(session: AsyncSession, delegation: Delegation, overwrite: bool = False, commit: bool = True) -> Delegation:
    """
    Create a new delegation in the database or return an existing one.

    If a delegation between the same owner and delegate already exists, either return it
    or overwrite it depending on the `overwrite` flag.

    Otherwise, add the new delegation to the database and optionally commit.

    Args:
        session: AsyncSession used to query and persist data.
        delegation: Delegation instance to create.
        overwrite: If True and a matching delegation exists, update it instead of creating a new one.
        commit: If True, commit the transaction after creating/updating.

    Returns:
        The created or existing Delegation instance.
    """
    result = await session.execute((
        select(Delegation)
        .where(Delegation.user_id_owner == delegation.user_id_owner, Delegation.user_id_delegate == delegation.user_id_delegate)
    ))
    extracted_delegation = result.scalar_one_or_none()
    if extracted_delegation is not None:
        if overwrite:
            await update_delegation(session, delegation)
            if commit:
                await session.commit()
        return extracted_delegation
    session.add(delegation)
    if commit:
        await session.commit()
    await session.refresh(delegation)
    return delegation

async def update_delegation(session: AsyncSession, delegation: Delegation):
    """
    Update an existing delegation's bounded flag or expiration date.

    If the provided delegation has no expiration_date, the function updates the bounded flag.
    Otherwise it updates the expiration_date. The change is committed.

    Args:
        session: AsyncSession used to execute the update.
        delegation: Delegation instance containing the new values.

    Returns:
        None
    """
    if delegation.expiration_date is None:
        update_kwargs = {"bounded": delegation.bounded}
    else:
        update_kwargs = {"expiration_date": delegation.expiration_date}
    await session.execute((
        update(Delegation)
        .where(Delegation.user_id_owner == delegation.user_id_owner, Delegation.user_id_delegate == delegation.user_id_delegate)
        .values(**update_kwargs)
    ))
    await session.commit()

async def revoke_db_delegation(session: AsyncSession, user_id: int, user_id_delegate: int, commit: bool = True):
    """
    Revoke (delete) a delegation between an owner and a delegate.

    Args:
        session: AsyncSession used to execute the delete.
        user_id: ID of the owner.
        user_id_delegate: ID of the delegate to revoke.
        commit: If True, commit the transaction after deletion.

    Returns:
        None
    """
    await session.execute(
        delete(Delegation)
        .where(Delegation.user_id_owner == user_id, Delegation.user_id_delegate == user_id_delegate)
    )
    if commit:
        await session.commit()
