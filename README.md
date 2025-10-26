# Overview

This project an async Python backend project providing a document management and signing system with delegation support. The system allows organizations to manage their users with hierarchical relationships defining how signature delegations can be created when a user becomes unavailable. Users can manual define delegates with an expiration period, create documents, ask people to sign them.

The main goal of the project is to make the signature process non blocking whenever a user is unavailable for a given period.

## Features

The service can be accessed through an API exposing most of the feature a user can use. It should be used following the steps below:

- An organization wants to start using the system
- A request should be sent to create an organization
- Then the initial user should create the users within its organization and create the relationships between the users
- Users can upload any document to the system and share them with other users
- Users can ask other users to sign document
- Users can list document with pending request that they can sign
- Users can create manual delegations to other users with an expiration date
- Whenever a user is unavailable, automatic delegations will be created according to the delegation depth allowed by the user
- Users can control their delegation depth and access the potential delegates if they went unavailable
- Users can sign the documents they are allowed to, either directly or through delegation

In addition to the main service, there is a cronjob checking for expired delegations to ensure they are properly deleted when needed.

The service should be enhanced with a notification system to remind users to sign documents and when a document is about to expire on the system.
An archiving system should be added to make sure documents does not stay indefinitely on the system after being signed.

## Setup

Before starting the project you should check the following sections

### Prerequisites

- Python 3.13+ (uses modern type syntax)
- MariaDB/MySQL server
- S3 bucket/MinIO

You can install a MariaDB server and a MinIO S3 bucket locally by using the supplied docker-compose.yml file.

Once you have Docker and Docker compose installed, create a directory with the supplied docker-compose.yml file and env_file renamed as .env.

Fill the environment variables as you want to and then just run:

```bash
docker compose up -d
```

### Installation

At the root project, create and enter a new virtualenv.
The install all the dependencies by running:

```bash
pip install .
```

### Startup

You should be able to start the application by running:

```bash
python -m src.project.main --host 127.0.0.1 --port 8000 --config /path/to/config
```

The config file should be either a JSON or YAML file having the following structure

```json
{
    "mariadb": {
        "user": "root",
        "password": "password",
        "host": "127.0.0.1",
        "port": 3306,
        "db_name": "app-db"
    },
    "minio": {
        "username": "admin",
        "password": "password",
        "host": "127.0.0.1",
        "port": 9000,
        "default_bucket": "app-bucket"
    }
}
```

You can access the fastAPI swagger at http://127.0.0.1:8000/docs if you used the startup command above.

## Database overview

Here is an overview of the database topology:

![Database topology](docs/diagram.png)

The database is used to store four main different entities:
- Organizations
- Users
- Documents
- Delegations

Along with these four entities, there is an association table called `DocumentUserLink`.

It is used to store the permissions a user has on a specific file, which is either `sign` or `read`. The entries with `sign` permissions can also have their `signed_at` and `signed_by` attributes filled whenever they are signed. A user can have both permissions at the same time on the same file but should not have two entries with the same (document_id, permission_type) couple.

The database also contains a closure table name `UserHierarchy` to represents each organizations hierarchy.

This table stores every relation between users, direct or indirect. If three users A, B and C have the following relationship A -> B -> C, the table will contain 6 entries:
- 3 entries with depth 0 because each user should be linked to themselves
- 2 entries with depth 1 between A -> B and B -> C
- 1 entry with depth 2 between A -> C

## Tests

The project have several basic tests [here](tests/).

To install the dependencies and then run all the tests:

```bash
pip install .[test]
pytest
```
