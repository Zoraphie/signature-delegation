from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models import Delegation

async def get_user_delegation(session: AsyncSession, user_id: int) -> list[Delegation]:
    result = await session.execute((
        select(Delegation)
        .where(Delegation.user_id_owner == user_id)
    ))
    return [delegation[0] for delegation in result.all()]

async def get_user_delegation_as_delegated(session: AsyncSession, user_id: int, bounded_only: bool = False) -> list[Delegation]:
    query = select(Delegation).where(Delegation.user_id_delegate == user_id)
    if bounded_only:
        query = query.where(Delegation.bounded == True)
    result = await session.execute(query)
    return [delegation[0] for delegation in result.all()]

async def create_db_delegation(session: AsyncSession, delegation: Delegation, overwrite: bool = False, commit: bool = True) -> Delegation:
    result = await session.execute((
        select(Delegation)
        .where(Delegation.user_id_owner == delegation.user_id_owner, Delegation.user_id_delegate == delegation.user_id_delegate)
    ))
    extracted_delegation = result.scalar_one_or_none()
    if extracted_delegation is not None:
        if overwrite:
            await update_delegation(session, delegation)
        return extracted_delegation
    session.add(delegation)
    if commit:
        await session.commit()
    await session.refresh(delegation)
    return delegation

async def update_delegation(session: AsyncSession, delegation: Delegation):
    #If the delegation is created automatically, it has no expiration date and should be bounded
    #Otherwise only the expiration date is updated
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
    await session.execute(
        delete(Delegation)
        .where(Delegation.user_id_owner == user_id, Delegation.user_id_delegate == user_id_delegate)
    )
    if commit:
        await session.commit()
