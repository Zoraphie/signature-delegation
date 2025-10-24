from dataclasses import dataclass
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from models import Base, User, Organization

@dataclass
class MariaDBAuthenticator:
    user: str
    password: str
    host: str
    port: int
    db_name: str

    @property
    def database_connection_string(self):
        return f"mysql+asyncmy://{self.user}:{self.password}@{self.host}:{self.port}/{self.db_name}"

class MariaDbConnector:
    def __init__(self, authenticator: MariaDBAuthenticator):
        self.engine = create_async_engine(
            authenticator.database_connection_string,
            echo=True,
            pool_pre_ping=True
        )
        self.session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, class_=AsyncSession
        )
    
    async def init_db(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def insert_items(self, items: list[Base], session: AsyncSession | None = None) -> None:
        async def insert(session: AsyncSession):
            session.add_all(items)
            await session.commit()
            (await session.refresh(item) for item in items)

        if session is None:
            async with self.session_factory() as session:
                await insert(session)
        else:
            await insert(session)

    def create_session(self) -> AsyncSession:
        """Returns a new session object. It needs to be properly closed whenever it is not needed anymore."""
        return self.session_factory()
