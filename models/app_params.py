from sqlalchemy import Column, Integer
from sqlalchemy import String, Text
from sqlalchemy import UniqueConstraint

from config.database import Base


class AppParam(Base):
    __tablename__ = "app_params"
    __table_args__ = (UniqueConstraint('key', name='unique_key'),)

    id = Column(Integer, primary_key=True)
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)
    description = Column(Text)
