from sqlalchemy import Column, Integer, ForeignKey, Time
from sqlalchemy.orm import relationship

from config.database import Base


class Reservation(Base):
    __tablename__ = 'reservations'

    id = Column(Integer, primary_key=True)
    day_of_week = Column(Integer)
    start_time = Column(Time)
    end_time = Column(Time)

    parking_spot_id = Column(Integer, ForeignKey('parkingspots.id'))
    driver_id = Column(Integer, ForeignKey('drivers.id'))

    parking_spot = relationship("ParkingSpot", back_populates="reservations")
    driver = relationship("Driver", back_populates="reservations", lazy="selectin")
