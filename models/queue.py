from sqlalchemy import Column, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from config.database import Base


class Queue(Base):
    __tablename__ = 'queue'

    id = Column(Integer, primary_key=True)
    created = Column(DateTime)

    position = Column(Integer)

    driver_id = Column(Integer, ForeignKey('drivers.id'))

    driver = relationship("Driver", back_populates="queue", lazy="selectin")
