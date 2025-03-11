from sqlalchemy import Column, Integer, Table, ForeignKey
from sqlalchemy.orm import relationship

from config.database import Base

parking_spot_driver_association = Table(
    'parking_spot_driver',
    Base.metadata,
    Column('parking_spot_id', Integer, ForeignKey('parkingspots.id')),
    Column('driver_id', Integer, ForeignKey('drivers.id'))
)


class ParkingSpot(Base):
    __tablename__ = 'parkingspots'
    id = Column(Integer, primary_key=True)
    x = Column(Integer)
    y = Column(Integer)
    width = Column(Integer)
    height = Column(Integer)

    drivers = relationship("Driver", secondary=parking_spot_driver_association)
    reservations = relationship("Reservation", back_populates="parking_spot")
