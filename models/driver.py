from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, Date
from sqlalchemy.dialects.sqlite.json import JSON
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import relationship

from config.database import Base
from models.parking_spot import parking_spot_driver_association, SpotStatus, ParkingSpot
from models.queue import Queue
from models.reservation import Reservation


class Driver(Base):
    __tablename__ = 'drivers'

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, unique=True, index=True)
    username = Column(String)
    title = Column(String)
    description = Column(String)
    absent_until = Column(Date, index=True)
    attributes = Column(MutableDict.as_mutable(JSON), default={})
    enabled = Column(Boolean)

    parking_spots = relationship("ParkingSpot",
                                 secondary=parking_spot_driver_association,
                                 back_populates="drivers")

    reservations = relationship(Reservation, back_populates="driver")
    queue = relationship(Queue, back_populates="driver")

    def is_absent(self, day: datetime) -> bool:
        return (self.absent_until is not None) and (self.absent_until > day)

    def my_spots(self) -> list[ParkingSpot]:
        return sorted([spot for spot in self.parking_spots if spot.status != SpotStatus.HIDEN], key=lambda s: s.id)
