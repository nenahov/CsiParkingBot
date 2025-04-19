from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from models.user_audit import UserActionType, UserAudit


class UserAuditDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, driver_id: int, action: UserActionType, current_day: date,
                     num: int = None,
                     description: str = None):
        audit_record = UserAudit(
            driver_id=driver_id,
            action=action,
            current_day=current_day,
            num=num,
            description=description
        )
        self.session.add(audit_record)
        await self.session.commit()
        return audit_record

    # async def get_karma_statistics(self, driver_id: int, days: int = None):
    #     query = self.session.execute(Select(func.sum(UserAudit.num)).filter(
    #         UserAudit.driver_id == driver_id,
    #         UserAudit.action.in_(
    #             [UserActionType.DRAW_KARMA, UserActionType.SPEND_KARMA, UserActionType.GET_ADMIN_KARMA])
    #     ))
    #
    #     if days:
    #         start_date = datetime.now() - timedelta(days=days)
    #         query = query.filter(UserAudit.action_time >= start_date)
    #
    #     return query.scalar() or 0
    #
    # async def get_spot_statistics(self, spot_number: int):
    #     return self.session.query(
    #         UserAudit.driver_id,
    #         func.count(UserAudit.id).label('actions_count')
    #     ).filter(
    #         or_(
    #             UserAudit.action == UserActionType.TAKE_SPOT,
    #             UserAudit.action == UserActionType.RELEASE_SPOT
    #         ),
    #         UserAudit.num == spot_number
    #     ).group_by(UserAudit.driver_id).all()
    #
    # async def get_actions_by_period(self, start_date: datetime, end_date: datetime):
    #     return self.session.query(UserAudit).filter(
    #         and_(
    #             UserAudit.action_time >= start_date,
    #             UserAudit.action_time <= end_date
    #         )
    #     ).all()
