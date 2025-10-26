import os
import json
import uvicorn
import argparse
from project.clients.db_connector import MariaDbConnector, MariaDBAuthenticator
from project.clients.minio_client import AsyncMinioClient, MinioAuthenticator
from project.app import CLIENTS

def load_config_file(path: str) -> dict:
    """
    Load a JSON or YAML configuration file and return a dictionary.

    Supported formats: .json, .yaml, .yml
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    lower = path.lower()
    if lower.endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    # try yaml if available
    try:
        import yaml  # type: ignore
    except Exception:
        raise RuntimeError("YAML support not available; install pyyaml or use a JSON config")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def setup_connectors(config: dict, clients: dict[str, MariaDbConnector | AsyncMinioClient | None]):
    """
    Initialize clients from a config dict.

    If config is None, fallback to the original hardcoded defaults.
    Expected config structure example:
    {
      "mariadb": {"user": "...", "password": "...", "host": "...", "port": 3306, "db_name": "..."},
      "minio": {"username": "...", "password": "...", "host": "...", "port": 9000, "secure": false, "default_bucket": "app-bucket"}
    }
    """
    if "mariadb" in config:
        m = config["mariadb"]
        authenticator = MariaDBAuthenticator(
            user=m.get("user"), password=m.get("password"),
            host=m.get("host"), port=m.get("port", 3306),
            db_name=m.get("db_name")
        )
    else:
        raise ValueError("MariaDB configuration is required")
    clients["mariadb"] = MariaDbConnector(authenticator)

    if "minio" in config:
        mm = config["minio"]
        minio_authenticator = MinioAuthenticator(
            username=mm.get("username"), password=mm.get("password"),
            host=mm.get("host"), port=mm.get("port", 9000)
        )
        clients["minio"] = AsyncMinioClient(minio_authenticator, secure=mm.get("secure", False))
        if mm.get("default_bucket"):
            clients["minio"].set_default_bucket(mm.get("default_bucket"))
    else:
        raise ValueError("MinIO configuration is required")

# Provide a small CLI helper to start the app with a config file
def cli_entry(clients: dict[str, MariaDbConnector | AsyncMinioClient | None]):
    """
    Simple CLI entrypoint to run the app with an optional --config path.

    Usage: python -m project.app --config /path/to/config.json
    """
    parser = argparse.ArgumentParser(prog="project.app")
    parser.add_argument("--config", "-c", help="Path to JSON or YAML configuration file", required=False)
    parser.add_argument("--host", help="Host to bind (uvicorn)", default="127.0.0.1")
    parser.add_argument("--port", help="Port to bind (uvicorn)", default=8000, type=int)
    args = parser.parse_args()

    if args.config:
        cfg = load_config_file(args.config)
        setup_connectors(cfg, clients)

    uvicorn.run("project.app:app", host=args.host, port=args.port, reload=False)

if __name__ == "__main__":
    cli_entry(CLIENTS)
