from sqlalchemy import update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from delegations import create_db_delegation
from organizations import get_childs
from models import User, Delegation

async def update_delegation_threshold(session: AsyncSession, user_id: int, delegation_threshold: int) -> User:
    await session.execute((
        update(User)
        .where(User.id == user_id)
        .values(delegation_threshold=delegation_threshold)
    ))
    await session.commit()
    return await session.get(User, user_id)

async def update_availability(session: AsyncSession, user_id: int, availability: bool) -> None:
    await session.execute((
        update(User)
        .where(User.id == user_id)
        .values(available=availability)
    ))
    await session.commit()
    if availability:
        await disable_delegations(session, user_id)
    else:
        await enable_delegations(session, user_id)
    await session.commit()

async def enable_delegations(session: AsyncSession, user_id: int):
    user = await session.get(User, user_id)
    for i in range(1, user.delegation_threshold+1):
        childs = await get_childs(session, user_id, i, i, available_only=True)
        if len(childs) > 0:
            for delegated_user in childs:
                await create_db_delegation(
                    session,
                    Delegation(expiration_date=None, user_id_owner=user_id, user_id_delegate=delegated_user.id, bounded=True),
                    overwrite=True
                )
            break

async def disable_delegations(session: AsyncSession, user_id: int):
    await session.execute(
        delete(Delegation)
        .where(Delegation.user_id_owner == user_id, Delegation.bounded == True, Delegation.expiration_date == None)
    )
    await session.execute(
        update(Delegation)
        .where(Delegation.user_id_owner == user_id)
        .values(bounded=False)
    )
