from sqlalchemy import update, delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from project.delegations import create_db_delegation, get_user_delegation, get_user_delegation_as_delegated
from project.organizations import get_childs
from project.models import User, Delegation, UserHierarchy

async def update_delegation_threshold(session: AsyncSession, user_id: int, delegation_threshold: int, commit: bool = True) -> User:
    """
    Update a user's delegation threshold value.

    Args:
        session: AsyncSession used to execute the update.
        user_id: ID of the user to update.
        delegation_threshold: New delegation threshold value.
        commit: If True, commit the transaction.

    Returns:
        The updated User instance retrieved from the database.
    """
    await session.execute((
        update(User)
        .where(User.id == user_id)
        .values(delegation_threshold=delegation_threshold)
    ))
    if commit:
        await session.commit()
    return await session.get(User, user_id)

async def update_availability(session: AsyncSession, user_id: int, availability: bool, commit: bool = True) -> None:
    """
    Update a user's availability and adjust delegations accordingly.

    When setting availability to False, this function checks existing delegations and enable delegations
    if there is none. It also enables delegations from owners who have delegated to this user.
    
    When setting availability to True, it disables delegations for the user and removes lower-level delegations
    that were created due to this user's unavailability.

    Args:
        session: AsyncSession used to execute updates.
        user_id: ID of the user to update.
        availability: New availability state.
        commit: If True, commit the transaction after changes.

    Returns:
        None
    """
    await session.execute((
        update(User)
        .where(User.id == user_id)
        .values(available=availability)
    ))
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
    if commit:
        await session.commit()

async def enable_delegations_from_owner(session: AsyncSession, user_id: int):
    """
    Enable delegations for the given owner starting at depth 1 up to their delegation threshold.

    This will create bounded delegations for eligible descendants up to the owner's threshold.

    Args:
        session: AsyncSession used to create delegations.
        user_id: ID of the owner user.

    Returns:
        None
    """
    user = await session.get(User, user_id)
    await enable_delegations_with_depth(session, 1, user.delegation_threshold, user_id)

async def enable_delegations(session: AsyncSession, user_id_owner: int, user_id_base: int):
    """
    Enable delegations for an owner relative to a base user.

    The function computes current depth between owner and base and then enables delegations
    for descendants starting from that depth up to the owner's threshold.

    Args:
        session: AsyncSession used to query hierarchy and create delegations.
        user_id_owner: ID of the owner user.
        user_id_base: ID of the base user (descendant used to compute current depth).

    Returns:
        None
    """
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
    """
    Walk descendant depths and create bounded delegations for eligible users.

    The function iterates depths from start_depth to max_depth. For each depth it creates
    bounded delegations for descendants found at that depth. If an available user is found
    at a depth, the function stops after processing that depth.

    Args:
        session: AsyncSession used to query descendants and create delegations.
        start_depth: Depth at which to start enabling delegations (inclusive).
        max_depth: Maximum depth to consider (inclusive).
        user_id: ID of the owner whose delegations are being enabled.

    Returns:
        None
    """
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
    """
    Disable automatic bounded delegations for an owner.

    This removes automatically created bounded delegations (expiration_date is None)
    and marks remaining delegations for the owner as unbounded.

    Args:
        session: AsyncSession used to execute updates and deletes.
        user_id: ID of the owner whose delegations will be disabled.

    Returns:
        None
    """
    await session.execute(
        delete(Delegation)
        .where(Delegation.user_id_owner == user_id, Delegation.bounded == True, Delegation.expiration_date == None)
    )
    await session.execute(
        update(Delegation)
        .where(Delegation.user_id_owner == user_id)
        .values(bounded=False)
    )
    await session.commit()


async def disable_lower_delegations(
    session: AsyncSession,
    reference_user_id: int
):
    """
    Delete all delegations with a depth (owner->delegated) higher than the (owner->reference_user) one
    Delegations which are both bounded and manual just get their bounded flags removed
    
    Args:
        session: AsyncSession used to execute deletions.
        reference_user_id: ID of the user to check lower depth user for.

    Returns:
        None
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

async def disable_expired_delegation(session: AsyncSession, delegation_id: int, commit: bool = True):
    """
    Disable or remove an expired delegation.

    If the delegation is unbounded (bounded == False) it is deleted.
    If it is bounded, its expiration_date is set to None (making it manual/unbounded).

    Args:
        session: AsyncSession used to execute update/delete.
        delegation_id: ID of the delegation to disable.
        commit: If True, commit the transaction after changes.

    Returns:
        None
    """
    await session.execute(
        delete(Delegation)
        .where(Delegation.id == delegation_id, Delegation.bounded == False)
    )
    await session.execute(
        update(Delegation)
        .where(Delegation.id == delegation_id, Delegation.bounded == True)
        .values(expiration_date=None)
    )
    if commit:
        await session.commit()
