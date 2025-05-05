from datetime import date, timedelta
from typing import Sequence

from sqlalchemy import text, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from config import constants
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

    async def get_weekly_karma(self, limit: int):
        stmt = text(f"""
                select sum(num) as total, d.description
                from user_audit ua
                join drivers d on d.id = ua.driver_id
                where action in ('DRAW_KARMA','GAME_KARMA','GET_ADMIN_KARMA')
                  and current_day >= date('now','-7 days')
                  and current_day < date('now','+{constants.new_day_offset} hour')
                  and d.id != :excluded_id
                group by d.description
                order by total desc, d.description
                limit :limit
            """)
        result = await self.session.execute(stmt, {"excluded_id": 1, "limit": limit})
        return result.all()

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

    async def get_actions_by_period(self, driver_id: int, period_in_days: int, current_day: date) -> Sequence[
        UserAudit]:
        result = await self.session.execute(
            select(UserAudit)
            .where(and_(
                UserAudit.driver_id.is_(driver_id),
                UserAudit.current_day >= current_day - timedelta(days=period_in_days),
                UserAudit.current_day < current_day
            ))
            .order_by(UserAudit.action_time))
        return result.scalars().all()
