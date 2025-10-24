from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, text

from models import UserHierarchy, User

async def add_user_link(session: AsyncSession, organization_id: int, parent_id: int, child_id: int):
    await check_for_circling_relationships(session, organization_id, parent_id, child_id)
    await session.execute(
        delete(UserHierarchy).where(
            UserHierarchy.organization_id == organization_id,
            UserHierarchy.descendant_id == child_id,
            UserHierarchy.depth > 0
        )
    )
    await session.execute(
        text("""INSERT INTO user_hierarchy (organization_id, ancestor_id, descendant_id, depth)
        SELECT
            :org_id,
            p.ancestor_id,
            c.descendant_id,
            p.depth + c.depth + 1
        FROM user_hierarchy AS p
        JOIN user_hierarchy AS c
          ON p.organization_id = c.organization_id
        WHERE p.organization_id = :org_id
          AND p.descendant_id = :parent_id
          AND c.ancestor_id = :child_id
        """),
        {"org_id": organization_id, "parent_id": parent_id, "child_id": child_id}
    )
    await session.commit()

async def check_for_circling_relationships(session: AsyncSession, org_id: int, parent_id: int, child_id: int):
    exists = await session.execute(
        text("""
        SELECT 1
        FROM user_hierarchy
        WHERE organization_id = :org_id
          AND ancestor_id = :child_id
          AND descendant_id = :parent_id
        LIMIT 1
        """),
        {"org_id": org_id, "parent_id": parent_id, "child_id": child_id}
    )
    if exists.scalar():
        raise ValueError("Cycle detected: cannot make a descendant into an ancestor.")

async def remove_link(session: AsyncSession, organization_id: int, parent_id: int, child_id: int):
    await session.execute(
        text("""DELETE h
        FROM user_hierarchy h
        JOIN user_hierarchy hp ON hp.organization_id = h.organization_id
        JOIN user_hierarchy hc ON hc.organization_id = h.organization_id
        WHERE hp.descendant_id = :parent_id
          AND hc.ancestor_id = :child_id
          AND h.ancestor_id = hp.ancestor_id
          AND h.descendant_id = hc.descendant_id
          AND h.organization_id = :org_id;"""),
        {"org_id": organization_id, "parent_id": parent_id, "child_id": child_id}
    )
    await session.commit()

async def get_childs(
    session: AsyncSession,
    user_id: int,
    min_depth: int,
    max_depth: int,
    available_only: bool = False
) -> list[User]:
    """min_depth should be strictly higher than 0"""
    available_part = "AND u.available" if available_only else ""
    result = await session.execute(
        text(f"""SELECT u.*
        FROM user_hierarchy uh
        JOIN users u
          ON u.id = uh.descendant_id
        WHERE uh.ancestor_id = :user_id
          AND uh.depth <= :max_depth
          AND uh.depth >= :min_depth
          {available_part}
        ORDER BY uh.depth ASC;"""),
        {"user_id": user_id, "max_depth": max_depth, "min_depth": min_depth}
    )
    return result.fetchall()
