from datetime import date
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from dao.user_audit_dao import UserAuditDAO
from models.user_audit import UserActionType, UserAudit


class AuditService:
    def __init__(self, session: AsyncSession):
        self.dao = UserAuditDAO(session)

    async def log_action(self, driver_id: int, action: UserActionType, current_day: date, num: int = None,
                         description: str = None):
        return await self.dao.create(driver_id, action, current_day, num, description)

    async def get_weekly_karma(self, limit: int, sign: int = 0, act: str = ''):
        return await self.dao.get_weekly_karma(limit, sign, act)

    async def get_actions_by_period(self, driver_id: int, period_in_days: int, current_day: date) -> Sequence[
        UserAudit]:
        return await self.dao.get_actions_by_period(driver_id, period_in_days, current_day)

    #
    # async def get_monthly_karma(self, driver_id: int):
    #     return await self.dao.get_karma_statistics(driver_id, days=30)
    #
    # async def get_spot_history(self, spot_number: int):
    #     return await self.dao.get_spot_statistics(spot_number)
    #
    # async def get_recent_actions(self, hours: int = 24):
    #     end_time = datetime.now()
    #     start_time = end_time - timedelta(hours=hours)
    #     return await self.dao.get_actions_by_period(start_time, end_time)
