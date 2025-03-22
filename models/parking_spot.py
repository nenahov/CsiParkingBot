from enum import Enum as PyEnum

from sqlalchemy import Column, Integer, ForeignKey, Enum
from sqlalchemy import Table
from sqlalchemy.orm import relationship

from config.database import Base


class SpotStatus(PyEnum):
    FREE = "free"
    OCCUPIED = "occupied"
    OCCUPIED_WITHOUT_DEMAND = "occupied_without_demand"

parking_spot_driver_association = Table(
    'parking_spot_driver',
    Base.metadata,
    Column('parking_spot_id', Integer, ForeignKey('parkingspots.id')),
    Column('driver_id', Integer, ForeignKey('drivers.id'))
)


class ParkingSpot(Base):
    __tablename__ = 'parkingspots'
    id = Column(Integer, primary_key=True, autoincrement=False)
    x = Column(Integer)
    y = Column(Integer)
    width = Column(Integer)
    height = Column(Integer)

    status = Column(Enum(SpotStatus), default=SpotStatus.FREE)
    current_driver_id = Column(Integer, ForeignKey('drivers.id'))

    drivers = relationship("Driver", secondary=parking_spot_driver_association, back_populates="parking_spots")
    reservations = relationship("Reservation", back_populates="parking_spot")
