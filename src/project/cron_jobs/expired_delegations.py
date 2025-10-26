import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from ..clients.db_connector import MariaDBAuthenticator, MariaDbConnector
from ..models import Delegation, User
from ..delegations import get_user_delegation
from ..users import disable_expired_delegation, enable_delegations_from_owner

async def main():
    AUTHENTICATOR = MariaDBAuthenticator(
        user="root", password="password", host="192.168.1.157",
        port=3306, db_name="orm_async"
    )
    CONNECTOR = MariaDbConnector(AUTHENTICATOR)
    session = CONNECTOR.create_session()

    delegations = await get_expired_delegations_with_owner_status(session)
    for d in delegations:
        await disable_expired_delegation(session, d.delegation_id, commit=False)
        if not d.owner_available:
            await create_delegations_for_absent_owner(session, d.user_id_owner)
    await session.commit()
    await session.close()

async def get_expired_delegations_with_owner_status(session: AsyncSession) -> list:
    """
    Return delegations that have expired along with the owner's availability flag.

    This query selects delegations whose expiration_date is set and in the past,
    joining the owner user to also return whether the owner is currently marked available.

    Args:
        session: AsyncSession used to execute the query.

    Returns:
        A list of result rows (named tuples) containing:
            - delegation_id: int (Delegation.id)
            - expiration_date: datetime
            - user_id_owner: int
            - owner_available: bool
    """
    now = datetime.now(timezone.utc)

    result = await session.execute(
        select(
            Delegation.id.label("delegation_id"),
            Delegation.expiration_date,
            Delegation.user_id_owner,
            User.available.label("owner_available")
        )
        .join(User, Delegation.user_id_owner == User.id)
        .where(
            Delegation.expiration_date.is_not(None),
            Delegation.expiration_date < now
        )
    )
    return result.all()

async def create_delegations_for_absent_owner(session: AsyncSession, user_id: int):
    """
    Create automatic (bounded) delegations for an owner who has no existing delegations.

    This helper checks whether the given owner already has any delegations. If none exist,
    it calls the routine that enables delegations from the owner (typically creating bounded,
    automatic delegations for eligible descendants).

    Args:
        session: AsyncSession used to perform the check and creation.
        user_id: ID of the owner to inspect.

    Returns:
        None
    """
    if len(await get_user_delegation(session, user_id)) == 0:
        await enable_delegations_from_owner(session, user_id)

if __name__ == "__main__":
    asyncio.run(main())

