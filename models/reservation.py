from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship

from config.database import Base


class Reservation(Base):
    __tablename__ = 'reservations'

    id = Column(Integer, primary_key=True, index=True)
    day_of_week = Column(Integer)

    parking_spot_id = Column(Integer, ForeignKey('parkingspots.id'), index=True)
    driver_id = Column(Integer, ForeignKey('drivers.id'), index=True)

    parking_spot = relationship("ParkingSpot", back_populates="reservations")
    driver = relationship("Driver", back_populates="reservations", lazy="selectin")
