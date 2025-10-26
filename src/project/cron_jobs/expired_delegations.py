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
    if len(await get_user_delegation(session, user_id)) == 0:
        await enable_delegations_from_owner(session, user_id)

if __name__ == "__main__":
    asyncio.run(main())

