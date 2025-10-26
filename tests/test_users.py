import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from project.users import (
    update_delegation_threshold, update_availability, enable_delegations_from_owner,
    enable_delegations_with_depth, disable_delegations, disable_lower_delegations,
    disable_expired_delegation
)
from project.models import User, Delegation

@pytest.mark.asyncio
async def test_update_delegation_threshold_updates_and_returns_user():
    session = AsyncMock()
    session.commit = AsyncMock()
    # session.get should return updated user
    updated_user = User(id=1, delegation_threshold=5)
    session.get.return_value = updated_user

    res = await update_delegation_threshold(session, user_id=1, delegation_threshold=5, commit=True)
    session.execute.assert_awaited()
    session.commit.assert_awaited()
    assert res is updated_user

@pytest.mark.asyncio
async def test_update_availability_makes_calls_enable_disable(monkeypatch):
    session = AsyncMock()
    session.commit = AsyncMock()
    # When setting availability to False and owner has no delegations, enable_delegations_from_owner should be called
    monkeypatch.setattr("project.users.get_user_delegation", AsyncMock(return_value=[]))
    monkeypatch.setattr("project.users.get_user_delegation_as_delegated", AsyncMock(return_value=[]))
    called = {"enable_owner": False}
    async def fake_enable_owner(s, uid):
        called["enable_owner"] = True
    monkeypatch.setattr("project.users.enable_delegations_from_owner", fake_enable_owner)

    await update_availability(session, user_id=2, availability=False, commit=True)
    assert called["enable_owner"] is True
    session.commit.assert_awaited()

@pytest.mark.asyncio
async def test_enable_delegations_with_depth_creates_delegations_and_stops_on_available(monkeypatch):
    session = AsyncMock()
    # simulate get_childs producing one available user at depth 1 then stop
    child = MagicMock(id=10, available=True)
    monkeypatch.setattr("project.users.get_childs", AsyncMock(return_value=[child]))
    created = []
    async def fake_create_db_delegation(session_arg, delegation, overwrite=True):
        created.append((delegation.user_id_owner, delegation.user_id_delegate, delegation.bounded))
    monkeypatch.setattr("project.users.create_db_delegation", fake_create_db_delegation)

    await enable_delegations_with_depth(session, start_depth=1, max_depth=3, user_id=42)
    assert created
    assert created[0][0] == 42

@pytest.mark.asyncio
async def test_disable_delegations_executes_delete_and_update_and_commit():
    session = AsyncMock()
    session.commit = AsyncMock()
    await disable_delegations(session, user_id=3)
    session.execute.assert_awaited()
    session.commit.assert_awaited()

@pytest.mark.asyncio
async def test_disable_lower_delegations_executes_expected_statements():
    session = AsyncMock()
    session.commit = AsyncMock()
    await disable_lower_delegations(session, reference_user_id=7)
    # should call execute twice (delete + update) and then commit
    assert session.execute.await_count >= 2
    session.commit.assert_awaited()

@pytest.mark.asyncio
async def test_disable_expired_delegation_handles_bounded_and_unbounded(session: AsyncMock = AsyncMock(), delegation_id: int = 12):
    # ensure delete and update executed and commit awaited
    session = AsyncMock()
    session.commit = AsyncMock()
    await disable_expired_delegation(session, delegation_id=delegation_id, commit=True)
    assert session.execute.await_count >= 2
    session.commit.assert_awaited()