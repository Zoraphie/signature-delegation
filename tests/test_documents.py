import pytest
from unittest.mock import AsyncMock, MagicMock
from project.documents import (
    create_document_links, is_owner, get_signature_documents,
    get_signature_delegated_documents, sign_document, get_delegation_signing_user,
    get_pending_signatures_db
)
from project.models import Document, DocumentUserLink, User

@pytest.mark.asyncio
async def test_create_document_links_adds_and_commits_and_refreshes():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.add_all = MagicMock()
    session.refresh = AsyncMock()
    links = [DocumentUserLink(document_id=1, user_id=2, permission_type="sign")]

    await create_document_links(session, links, commit=True)
    session.add_all.assert_called_once_with(links)
    session.commit.assert_awaited()

@pytest.mark.asyncio
async def test_is_owner_true():
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = True
    session.execute.return_value = mock_result

    res = await is_owner(session, user_id=3, document_id=7)
    assert res is True
    session.execute.assert_awaited_once()

@pytest.mark.asyncio
async def test_get_signature_documents_returns_documents_scalars_all():
    session = AsyncMock()
    mock_result = MagicMock()
    doc = Document(id=1)
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [doc]
    mock_result.scalars.return_value = mock_scalars
    session.execute.return_value = mock_result

    res = await get_signature_documents(session, user_id=2)
    assert res == [doc]
    session.execute.assert_awaited_once()

@pytest.mark.asyncio
async def test_get_signature_delegated_documents_returns_documents():
    session = AsyncMock()
    mock_result = MagicMock()
    doc = Document(id=11)
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [doc]
    mock_result.scalars.return_value = mock_scalars
    session.execute.return_value = mock_result

    res = await get_signature_delegated_documents(session, user_id=8)
    assert res == [doc]
    session.execute.assert_awaited_once()

@pytest.mark.asyncio
async def test_get_delegation_signing_user_returns_owners():
    session = AsyncMock()
    mock_result = MagicMock()
    owner = User(id=99)
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [owner]
    mock_result.scalars.return_value = mock_scalars
    session.execute.return_value = mock_result

    res = await get_delegation_signing_user(session, document_id=10, user_id=20)
    assert res == [owner]
    session.execute.assert_awaited_once()

@pytest.mark.asyncio
async def test_get_pending_signatures_db_combines_direct_and_delegated(monkeypatch):
    session = AsyncMock()

    async def fake_direct(s, uid):
        return [Document(id=1)]
    async def fake_delegated(s, uid):
        return [Document(id=2)]

    monkeypatch.setattr("project.documents.get_signature_documents", fake_direct)
    monkeypatch.setattr("project.documents.get_signature_delegated_documents", fake_delegated)

    res = await get_pending_signatures_db(session, user_id=7)
    assert isinstance(res, list)
    assert any(isinstance(d, Document) for d in res)
    assert {d.id for d in res} == {1,2}
