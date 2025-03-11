from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from config.database import Base
from models.parking_spot import parking_spot_driver_association


class Driver(Base):
    __tablename__ = 'drivers'

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True)
    username = Column(String)

    parking_spots = relationship("ParkingSpot", secondary=parking_spot_driver_association)
    reservations = relationship("Reservation", back_populates="driver")
