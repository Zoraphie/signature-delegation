import asyncio
from fastapi import FastAPI, Body, Response, status, File, UploadFile
from typing import Annotated
from sqlalchemy.exc import IntegrityError, OperationalError
from datetime import datetime

from models import (
    Organization, User, UserHierarchy, UserSchema, Delegation, DelegationSchema,
    DocumentUserLink, Document, DocumentSchema
)
from db_connector import MariaDbConnector, MariaDBAuthenticator
from minio_client import MinioAuthenticator, AsyncMinioClient
from organizations import add_user_link, remove_link, get_childs
from users import update_delegation_threshold, update_availability
from delegations import create_db_delegation, get_user_delegation, revoke_db_delegation
from utils import compute_timedelta_from_string
from documents import create_document_links, is_owner
from logger import configure_basic, get_logger

app = FastAPI()

AUTHENTICATOR = MariaDBAuthenticator(
    user="root", password="password", host="192.168.1.157",
    port=3306, db_name="orm_async"
)
CONNECTOR = MariaDbConnector(AUTHENTICATOR)
MINIO_AUTHENTICATOR = MinioAuthenticator(username="admin", password="password", host="192.168.1.157", port=9000)
MINIO_CLIENT = AsyncMinioClient(MINIO_AUTHENTICATOR, secure=False)
MINIO_CLIENT.set_default_bucket("app-bucket")
APP_LOGGER = None

async def main():
    global APP_LOGGER
    await CONNECTOR.init_db()
    configure_basic()
    APP_LOGGER = get_logger("app")
    await MINIO_CLIENT.create_bucket()

asyncio.create_task(main())


@app.post("/organizations", status_code=200)
async def create_organization(name: Annotated[str, Body(..., embed=True)]):
    new_org = Organization(name=name)
    await CONNECTOR.insert_items([new_org])
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
        session = CONNECTOR.create_session()
        await CONNECTOR.insert_items([new_user], session=session)
        self_link = UserHierarchy(organization_id=organization_id, ancestor_id=new_user.id, descendant_id=new_user.id, depth=0)
        await CONNECTOR.insert_items([self_link], session=session, commit=False)
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
    session = CONNECTOR.create_session()
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
    session = CONNECTOR.create_session()
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
    session = CONNECTOR.create_session()
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
    session = CONNECTOR.create_session()
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
    session = CONNECTOR.create_session()
    try:
        await update_availability(session, user_id, available)
    except Exception as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"message": "An unknown error has occured"}
    await session.close()

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
    session = CONNECTOR.create_session()
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
    session = CONNECTOR.create_session()
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
    session = CONNECTOR.create_session()
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
    session = CONNECTOR.create_session()
    document = Document(filename=file.filename, created_by=owner_id)
    try:
        await CONNECTOR.insert_items([document], session)
        link = DocumentUserLink(document_id=document.id, user_id=owner_id, permission_type="read")
        await CONNECTOR.insert_items([link], session, commit=False)
        await MINIO_CLIENT.upload_file_from_bytes(str(document.id), file_content)
        await session.commit()
    except Exception as err:
        APP_LOGGER.error(err)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"message": "An unknown error has occured"}
    finally:
        await session.close()
    return {"document": DocumentSchema.model_validate(document).model_dump()}

@app.post("/documents/share")
async def share_document(
    owner_id: Annotated[int, Body(..., embed=True)],
    document_id: Annotated[int, Body(..., embed=True)],
    shared_users: Annotated[list[int], Body(..., embed=True)],
    response: Response
):
    session = CONNECTOR.create_session()
    try:
        if not await is_owner(session, owner_id, document_id):
            response.status_code = status.HTTP_404_NOT_FOUND
            return {"message": "File does not exist"}
        links = [DocumentUserLink(document_id=document_id, user_id=shared_user, permission_type="read") for shared_user in shared_users]
        await CONNECTOR.insert_items(links, session)
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

@app.post("/documents/ask_signature")
async def ask_signature(
    owner_id: Annotated[int, Body(..., embed=True)],
    document_id: Annotated[int, Body(..., embed=True)],
    signing_user: Annotated[int, Body(..., embed=True)],
    response: Response
):
    session = CONNECTOR.create_session()
    try:
        if not await is_owner(session, owner_id, document_id):
            response.status_code = status.HTTP_404_NOT_FOUND
            return {"message": "File does not exist"}
        link = DocumentUserLink(document_id=document_id, user_id=signing_user, permission_type="sign")
        await CONNECTOR.insert_items([link], session)
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


# @app.post("/documents/create")
# async def create_document(
#     owner_id: Annotated[int, Body(..., embed=True)],
#     signing_user: Annotated[int, Body(..., embed=True)],
#     shared_users: Annotated[list[int], Body(..., embed=True)],
#     filename: Annotated[str, Body(..., embed=True)],
#     recipient_email: Annotated[str, Body(..., embed=True)]
# ):
#     document = Document(filename=filename, created_by=owner_id)
#     session = CONNECTOR.create_session()
#     await CONNECTOR.insert_items([document], session, commit=False)
#     links = [DocumentUserLink(document_id=document.id, user_id=shared_user, permission_type="read") for shared_user in shared_users]
#     links.append(DocumentUserLink(document_id=document.id, user_id=signing_user, permission_type="sign"))
#     await create_document_links(session, links, commit=False)
#     await session.commit()
#     await session.close()
#     # Need to check availability of the signing_user, otherwise trigger delegation
#     # Need to trigger the notifications for the current org
#     # Need to send an email if remote recipient is not using the solution
#     # Otherwise, share the document with the other organization

