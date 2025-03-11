import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker

# Загрузка переменных окружения из .env
load_dotenv()

# Получение URL БД из переменных окружения
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./parking.db"
)

# Создание асинхронного движка
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # Логирование SQL-запросов (можно отключить для продакшена)
    future=True
)

# Базовый класс для моделей
Base = declarative_base()

# Фабрика сессий с настройками
async_session_maker = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)


async def get_async_session() -> AsyncSession:
    """
    Генератор сессий для зависимостей FastAPI или ручного использования
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()


async def create_database():
    """
    Создание таблиц в БД (альтернатива Alembic для разработки)
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
