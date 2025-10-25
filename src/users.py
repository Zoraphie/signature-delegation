from sqlalchemy import update, delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from delegations import create_db_delegation, get_user_delegation, get_user_delegation_as_delegated
from organizations import get_childs
from models import User, Delegation, UserHierarchy

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
    if not availability:
        delegation_as_delegated = await get_user_delegation_as_delegated(session, user_id, bounded_only=True)
        if len(await get_user_delegation(session, user_id)) == 0:
            await enable_delegations_from_owner(session, user_id)
        if len(delegation_as_delegated) > 0:
            for d in delegation_as_delegated:
                await enable_delegations(session, d.user_id_owner, user_id)
    else:
        await disable_delegations(session, user_id)
        await disable_lower_delegations(session, user_id)
    await session.commit()

async def enable_delegations_from_owner(session: AsyncSession, user_id: int):
    user = await session.get(User, user_id)
    await enable_delegations_with_depth(session, 1, user.delegation_threshold, user_id)

async def enable_delegations(session: AsyncSession, user_id_owner: int, user_id_base: int):
    link = await session.execute((
        select(UserHierarchy)
        .where(UserHierarchy.ancestor_id == user_id_owner, UserHierarchy.descendant_id == user_id_base)
    ))
    user_hierarchy = link.scalar_one_or_none()
    current_depth = user_hierarchy.depth
    user = await session.get(User, user_id_owner)
    max_depth = user.delegation_threshold
    await enable_delegations_with_depth(session, current_depth, max_depth, user_id_owner)

async def enable_delegations_with_depth(session: AsyncSession, start_depth: int, max_depth: int, user_id: int):
    break_out = False
    for i in range(start_depth, max_depth+1):
        childs = await get_childs(session, user_id, i, i)
        if len(childs) > 0:
            for delegated_user in childs:
                if delegated_user.available:
                    break_out = True
                await create_db_delegation(
                    session,
                    Delegation(expiration_date=None, user_id_owner=user_id, user_id_delegate=delegated_user.id, bounded=True),
                    overwrite=True
                )
            if break_out:
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


async def disable_lower_delegations(
    session: AsyncSession,
    reference_user_id: int
):
    """
    Delete all delegations with a depth (owner->delegated) is higher than the (owner->reference_user) one
    Delegations which are both bounded and manual just get their bounded flags removed
    """
    UH_src_dst = aliased(UserHierarchy)
    UH_src_ref = aliased(UserHierarchy)
    subquery = (
        select(UH_src_dst.ancestor_id, UH_src_dst.descendant_id)
        .join(
            UH_src_ref,
            UH_src_dst.ancestor_id == UH_src_ref.ancestor_id
        )
        .where(
            UH_src_ref.descendant_id == reference_user_id,
            UH_src_dst.depth > UH_src_ref.depth
        )
    )

    delete_bounded_only_stmt = (
        delete(Delegation)
        .where(
            tuple_(Delegation.user_id_owner, Delegation.user_id_delegate)
            .in_(subquery),
            Delegation.expiration_date == None
        )
    )
    update_bounded_and_manual_stmt = (
        update(Delegation)
        .where(
            tuple_(Delegation.user_id_owner, Delegation.user_id_delegate)
            .in_(subquery),
            Delegation.expiration_date != None
        )
        .values(bounded=False)
    )
    await session.execute(delete_bounded_only_stmt)
    await session.execute(update_bounded_and_manual_stmt)
    await session.commit()
