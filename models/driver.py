from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import relationship

from config.database import Base
from models.parking_spot import parking_spot_driver_association


class Driver(Base):
    __tablename__ = 'drivers'

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True)
    username = Column(String)
    title = Column(String)
    description = Column(String)
    enabled = Column(Boolean)

    parking_spots = relationship("ParkingSpot", secondary=parking_spot_driver_association, back_populates="drivers")

    reservations = relationship("Reservation", back_populates="driver")
