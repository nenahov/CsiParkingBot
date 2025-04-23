from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Column, Integer, DateTime, Date, String, Enum as SQLEnum, ForeignKey

from config.database import Base


class UserActionType(PyEnum):
    DRAW_KARMA = "Розыгрыш кармы"
    TAKE_SPOT = "Занял место"
    RELEASE_SPOT = "Освободить место"
    JOIN_QUEUE = "Занял очередь"
    LEAVE_QUEUE = "Покинул очередь"
    GET_ADMIN_KARMA = "Получил карму от админа"
    SPEND_KARMA = "Потратил карму на ..."
    CHOOSE_AVATAR = "Выбрал аватар"
    GAME = "Играет в мини-игры"
    GAME_KARMA = "Получил карму в мини-игре"


class UserAudit(Base):
    __tablename__ = 'user_audit'

    id = Column(Integer, primary_key=True)
    action_time = Column(DateTime, default=datetime.now, nullable=False)
    current_day = Column(Date, nullable=False)
    driver_id = Column(Integer, ForeignKey('drivers.id'), nullable=False)
    action = Column(SQLEnum(UserActionType), nullable=False)
    num = Column(Integer)
    description = Column(String)
