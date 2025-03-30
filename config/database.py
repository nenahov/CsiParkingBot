import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base

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
    echo=False,  # Логирование SQL-запросов (можно отключить для продакшена)
    future=True
)

# Базовый класс для моделей
Base = declarative_base()

# Фабрика сессий с настройками
db_pool = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

async def create_database():
    """
    Создание таблиц в БД (альтернатива Alembic для разработки)
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
