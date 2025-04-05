from sqlalchemy import Column, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from config.database import Base


class Queue(Base):
    __tablename__ = 'queue'

    id = Column(Integer, primary_key=True)
    created = Column(DateTime)

    driver_id = Column(Integer, ForeignKey('drivers.id'), index=True)
    driver = relationship("Driver", back_populates="queue", lazy="selectin")

    spot_id = Column(Integer, ForeignKey('parkingspots.id'), index=True)
    spot = relationship("ParkingSpot", lazy="selectin")

    choose_before = Column(DateTime)
