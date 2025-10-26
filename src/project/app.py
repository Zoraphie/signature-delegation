from fastapi import FastAPI, Body, Response, status, File, UploadFile
from typing import Annotated
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy import update
from datetime import datetime

from project.models import (
    Organization, User, UserHierarchy, UserSchema, Delegation, DelegationSchema,
    DocumentUserLink, Document, DocumentSchema
)
from project.clients.db_connector import MariaDbConnector
from project.clients.minio_client import AsyncMinioClient
from project.organizations import add_user_link, remove_link, get_childs
from project.users import update_delegation_threshold, update_availability
from project.delegations import create_db_delegation, get_user_delegation, revoke_db_delegation
from project.utils import compute_timedelta_from_string
from project.documents import is_owner, get_pending_signatures_db, sign_document, get_delegation_signing_user
from project.logger import configure_basic, get_logger

app = FastAPI()

APP_LOGGER = None
# Globals will be configured by `setup_connectors`. Defaults kept for backwards compat.
CLIENTS: dict[str, MariaDbConnector | AsyncMinioClient | None] = {
    "mariadb": None,
    "minio": None
}

# Run initialization on FastAPI startup (avoids side-effects on import)
@app.on_event("startup")
async def _startup():
    global APP_LOGGER

    # ensure connectors exist
    if CLIENTS["mariadb"] is None or CLIENTS["minio"] is None:
        raise RuntimeError("Connectors are not properly initialized. Call setup_connectors first.")
    await CLIENTS["mariadb"].init_db()
    configure_basic()
    APP_LOGGER = get_logger("app")
    await CLIENTS["minio"].create_bucket()

@app.post("/organizations", status_code=200)
async def create_organization(name: Annotated[str, Body(..., embed=True)]):
    new_org = Organization(name=name)
    await CLIENTS["mariadb"].insert_items([new_org])
    return new_org

@app.post("/users", status_code=200)
async def create_user(
    fullname: Annotated[str, Body(..., embed=True)],
    email: Annotated[str, Body(..., embed=True)],
    organization_id: Annotated[int, Body(..., embed=True)],
    response: Response,
    parent_id: Annotated[int | None, Body(..., embed=True)] = None
):
    new_user = User(full_name=fullname, organization_id=organization_id, email=email)
    try:
        session = CLIENTS["mariadb"].create_session()
        await CLIENTS["mariadb"].insert_items([new_user], session=session)
        self_link = UserHierarchy(organization_id=organization_id, ancestor_id=new_user.id, descendant_id=new_user.id, depth=0)
        await CLIENTS["mariadb"].insert_items([self_link], session=session, commit=False)
        if parent_id is not None:
            await add_user_link(session, organization_id, parent_id, new_user.id, commit=False)
        await session.commit()
    except IntegrityError as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"message": "Organization does not exist or user email is already taken"}
    except Exception as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"message": "An unknown error has occured"}
    finally:
        await session.close()
    return {
        "message": "User was properly created",
        "user_data": new_user
    }

@app.put("/users/link", status_code=200)
async def create_user_link(
    organization_id: Annotated[int, Body(..., embed=True)],
    parent_id: Annotated[int, Body(..., embed=True)],
    child_id: Annotated[int, Body(..., embed=True)],
    response: Response
):
    session = CLIENTS["mariadb"].create_session()
    try:
        await add_user_link(session, organization_id, parent_id, child_id)
    except ValueError as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"message": "A circling relationship was detected between users, link was not created"}
    except Exception as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"message": "An unknown error has occured"}
    finally:
        await session.close()
    return {
        "message": "Users were properly linked"
    }

@app.delete("/users/unlink", status_code=200)
async def delete_user_link(
    organization_id: Annotated[int, Body(..., embed=True)],
    parent_id: Annotated[int, Body(..., embed=True)],
    child_id: Annotated[int, Body(..., embed=True)],
    response: Response
):
    session = CLIENTS["mariadb"].create_session()
    try:
        await remove_link(session, organization_id, parent_id, child_id)
    except Exception as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"message": "An unknown error has occured"}
    finally:
        await session.close()
    return {
        "message": "Users were properly unlinked"
    }

@app.get("/users/potential_delegates", status_code=200)
async def get_potential_delegates(
    user_id: int,
    response: Response
):
    session = CLIENTS["mariadb"].create_session()
    try:
        user = await session.get(User, user_id)
        child_users = await get_childs(session, user_id, 1, user.delegation_threshold)
    except Exception as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"message": "An unknown error has occured"}
    finally:
        await session.close()
    return {
        "users": [UserSchema.model_validate(user).model_dump() for user in child_users]
    }

@app.put("/users/{user_id}/delegation_threshold")
async def set_delegation_threshold(user_id: int, delegation_threshold: Annotated[int, Body(..., embed=True)], response: Response):
    session = CLIENTS["mariadb"].create_session()
    try:
        user = await update_delegation_threshold(session, user_id, delegation_threshold)
    except Exception as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"message": "An unknown error has occured"}
    finally:
        await session.close()
    return {"user": UserSchema.model_validate(user).model_dump()}

@app.put("/users/{user_id}/availability")
async def set_availability(user_id: int, available: Annotated[bool, Body(..., embed=True)], response: Response):
    session = CLIENTS["mariadb"].create_session()
    try:
        await update_availability(session, user_id, available)
    except Exception as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"message": "An unknown error has occured"}
    await session.close()
    available = "available" if available else "unavailable"
    return {"message": f"User {user_id} is now {available}"}

@app.put("/delegations/create")
async def create_delegation(
    user_id: Annotated[int, Body(..., embed=True)],
    delegated_user_id: Annotated[int, Body(..., embed=True)],
    duration: Annotated[str, Body(..., embed=True)],
    response: Response
):
    try:
        timedelta = compute_timedelta_from_string(duration)
    except ValueError as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"message": "Specified duration is incorrect, it should be something like 3w, 4d or 5h"}
    expiration_date=datetime.now()+timedelta
    delegation = Delegation(expiration_date=expiration_date, user_id_owner=user_id, user_id_delegate=delegated_user_id)
    session = CLIENTS["mariadb"].create_session()
    try:
        return_delegation = await create_db_delegation(session, delegation, overwrite=True)
    except IntegrityError as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"message": err.orig, "code": err._message()}
    except OperationalError as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"message": "Trying to create a delegation between the same user"}
    except Exception as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"message": "An unknown error has occured"}
    finally:
        await session.close()
    return {"delegation": DelegationSchema.model_validate(return_delegation).model_dump()}

@app.get("/delegations")
async def get_delegations(user_id: int):
    session = CLIENTS["mariadb"].create_session()
    try:
        delegations = await get_user_delegation(session, user_id)
    finally:
        await session.close()
    return {"delegations": [DelegationSchema.model_validate(delegation).model_dump() for delegation in delegations]}

@app.delete("/delegations/revoke")
async def revoke_delegation(
    user_id: Annotated[int, Body(..., embed=True)],
    delegated_user_id: Annotated[int, Body(..., embed=True)]
):
    session = CLIENTS["mariadb"].create_session()
    try:
        await revoke_db_delegation(session, user_id, delegated_user_id)
    finally:
        await session.close()
    return {"message": "Delegation was properly revoked"}

@app.post("/documents/create")
async def create_document(
    owner_id: Annotated[int, Body(..., embed=True)],
    response: Response,
    file: UploadFile = File(...)
):
    file_content = await file.read()
    session = CLIENTS["mariadb"].create_session()
    document = Document(filename=file.filename, created_by=owner_id)
    try:
        await CLIENTS["mariadb"].insert_items([document], session)
        link = DocumentUserLink(document_id=document.id, user_id=owner_id, permission_type="read")
        await CLIENTS["mariadb"].insert_items([link], session, commit=False)
        await CLIENTS["minio"].upload_file_from_bytes(str(document.id), file_content)
        await session.commit()
    except Exception as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"message": "An unknown error has occured"}
    finally:
        await session.close()
    return {"document": DocumentSchema.model_validate(document).model_dump()}

@app.post("/documents/{document_id}/share")
async def share_document(
    owner_id: Annotated[int, Body(..., embed=True)],
    document_id: int,
    shared_users: Annotated[list[int], Body(..., embed=True)],
    response: Response
):
    session = CLIENTS["mariadb"].create_session()
    try:
        if not await is_owner(session, owner_id, document_id):
            response.status_code = status.HTTP_404_NOT_FOUND
            return {"message": "File does not exist"}
        links = [DocumentUserLink(document_id=document_id, user_id=shared_user, permission_type="read") for shared_user in shared_users]
        await CLIENTS["mariadb"].insert_items(links, session)
    except IntegrityError as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"message": "Trying to share a document with non existant users or already shared users"}
    except Exception as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"message": "An unknown error has occured"}
    finally:
        await session.close()
    return {"message": "Document was properly shared"}

@app.post("/documents/{document_id}/request_signature")
async def ask_signature(
    owner_id: Annotated[int, Body(..., embed=True)],
    document_id: int,
    signing_user: Annotated[int, Body(..., embed=True)],
    response: Response
):
    session = CLIENTS["mariadb"].create_session()
    try:
        if not await is_owner(session, owner_id, document_id):
            response.status_code = status.HTTP_404_NOT_FOUND
            return {"message": "File does not exist"}
        link = DocumentUserLink(document_id=document_id, user_id=signing_user, permission_type="sign")
        await CLIENTS["mariadb"].insert_items([link], session, commit=False)
        await session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status="pending")
        )
        await session.commit()
    except IntegrityError as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"message": "Trying to make a user sign but the user does not exist or already have the right to."}
    except Exception as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"message": "An unknown error has occured"}
    finally:
        await session.close()
    return {"message": f"User {signing_user} was asked to sign document {document_id}"}

@app.get("/documents/pending")
async def get_pending_signatures(user_id: int, response: Response):
    session = CLIENTS["mariadb"].create_session()
    try:
        documents = await get_pending_signatures_db(session, user_id)
    except Exception as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"message": "An unknown error has occured"}
    finally:
        await session.close()
    return {"documents": documents}

@app.post("/documents/{document_id}/sign")
async def sign(
    document_id: int,
    user_id: Annotated[int, Body(..., embed=True)],
    response: Response
):
    session = CLIENTS["mariadb"].create_session()
    try:
        documents = await get_pending_signatures_db(session, user_id)
        document_signed = False
        for d in documents:
            if d.id == document_id:
                signature_owners = await get_delegation_signing_user(session, document_id, user_id)
                for owner in signature_owners:
                    await sign_document(session, owner.id, user_id, document_id)
                document_signed = True
    except Exception as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"message": "An unknown error has occured"}
    finally:
        await session.close()
    if not document_signed:
        response.status_code = status.HTTP_404_NOT_FOUND
        return {"message": "Document does not exist or you do not have permission to sign it"}
    return {"message": "Document was properly signed"}

