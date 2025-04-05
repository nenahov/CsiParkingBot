from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from config.database import Base


class Reservation(Base):
    __tablename__ = 'reservations'

    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey('drivers.id'), index=True)
    day_of_week = Column(Integer)
    UniqueConstraint('driver_id', 'day_of_week', name='uq_reservations_driver_id_day_of_week')

    parking_spot_id = Column(Integer, ForeignKey('parkingspots.id'), index=True)

    parking_spot = relationship("ParkingSpot", back_populates="reservations")
    driver = relationship("Driver", back_populates="reservations", lazy="selectin")
