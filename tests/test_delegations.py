import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

import project.delegations as delegations
from project.models import Delegation

@pytest.mark.asyncio
async def test_get_user_delegation_returns_list_of_delegations():
    session = AsyncMock()
    # emulate result of session.execute().all() => list of row-tuples
    mock_result = MagicMock()
    mock_delegation = Delegation(id=1, user_id_owner=10, user_id_delegate=20)
    mock_result.all.return_value = [(mock_delegation,)]
    session.execute.return_value = mock_result

    res = await delegations.get_user_delegation(session, 10)
    assert isinstance(res, list)
    assert res == [mock_delegation]
    session.execute.assert_awaited_once()

@pytest.mark.asyncio
async def test_get_user_delegation_as_delegated_bounded_filter():
    session = AsyncMock()
    mock_result = MagicMock()
    mock_d1 = Delegation(id=1, user_id_owner=5, user_id_delegate=7, bounded=True)
    mock_result.all.return_value = [(mock_d1,)]
    session.execute.return_value = mock_result

    res = await delegations.get_user_delegation_as_delegated(session, 7, bounded_only=True)
    assert res == [mock_d1]
    session.execute.assert_awaited_once()

@pytest.mark.asyncio
async def test_create_db_delegation_creates_when_not_exists_and_commits_and_refreshes():
    session = AsyncMock()
    # no existing delegation
    mock_query_result = MagicMock()
    mock_query_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_query_result

    d = Delegation(user_id_owner=1, user_id_delegate=2, bounded=True)

    # ensure commit and refresh are awaited
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    res = await delegations.create_db_delegation(session, d, overwrite=False, commit=True)
    # the returned object should be same instance we added
    assert res is d
    session.execute.assert_awaited()
    session.commit.assert_awaited()
    session.refresh.assert_awaited_with(d)

@pytest.mark.asyncio
async def test_create_db_delegation_returns_existing_and_overwrite_calls_update():
    session = AsyncMock()
    existing = Delegation(id=42, user_id_owner=1, user_id_delegate=2)
    mock_query_result = MagicMock()
    mock_query_result.scalar_one_or_none.return_value = existing
    session.execute.return_value = mock_query_result

    # patch update_delegation to ensure called when overwrite=True
    delegations.update_delegation = AsyncMock()

    d = Delegation(user_id_owner=1, user_id_delegate=2)
    res = await delegations.create_db_delegation(session, d, overwrite=True, commit=True)
    assert res is existing
    delegations.update_delegation.assert_awaited_once()

@pytest.mark.asyncio
async def test_revoke_db_delegation_executes_delete_and_commits():
    session = AsyncMock()
    session.commit = AsyncMock()
    await delegations.revoke_db_delegation(session, user_id=5, user_id_delegate=6, commit=True)
    session.execute.assert_awaited()
    session.commit.assert_awaited()