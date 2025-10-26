import pytest
from unittest.mock import AsyncMock, MagicMock
from project.organizations import add_user_link, check_for_circling_relationships, remove_link, get_childs
from sqlalchemy import text

@pytest.mark.asyncio
async def test_check_for_circling_relationships_raises_on_cycle():
    session = AsyncMock()
    # return a result whose scalar() is True to indicate cycle present
    mock_result = MagicMock()
    mock_result.scalar.return_value = True
    session.execute.return_value = mock_result
    with pytest.raises(ValueError):
        await check_for_circling_relationships(session, org_id=1, parent_id=2, child_id=3)
    session.execute.assert_awaited_once()

@pytest.mark.asyncio
async def test_add_user_link_deletes_and_inserts_and_commits(monkeypatch):
    session = AsyncMock()
    # patch check_for_circling_relationships to be a no-op
    monkeypatch.setattr("project.organizations.check_for_circling_relationships", AsyncMock())
    session.execute = AsyncMock()
    await add_user_link(session, organization_id=5, parent_id=10, child_id=11, commit=True)
    # should call execute for delete and for insert and then commit via session.execute calls
    assert session.execute.await_count >= 2

@pytest.mark.asyncio
async def test_remove_link_executes_delete_and_commits():
    session = AsyncMock()
    session.execute = AsyncMock()
    await remove_link(session, organization_id=1, parent_id=2, child_id=3, commit=True)
    session.execute.assert_awaited()
    session.commit.assert_awaited()

@pytest.mark.asyncio
async def test_get_childs_returns_rows():
    session = AsyncMock()
    mock_result = MagicMock()
    mock_row = ("user_row",)
    mock_result.fetchall.return_value = [mock_row]
    session.execute.return_value = mock_result
    rows = await get_childs(session, user_id=1, min_depth=1, max_depth=2, available_only=False)
    assert rows == [mock_row]
    session.execute.assert_awaited_once()