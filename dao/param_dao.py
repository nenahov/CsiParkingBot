from typing import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.app_params import AppParam


class ParamDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_params(self) -> Sequence[AppParam]:
        result = await self.session.execute(select(AppParam))
        return result.scalars().all()

    async def get_param(self, key: str) -> AppParam | None:
        result = await self.session.execute(
            select(AppParam).where(AppParam.key.is_(key)))
        return result.scalar_one_or_none()

    async def set_param(self, key: str, value: str, description: str = None) -> AppParam:
        # Try to update existing
        stmt = (
            update(AppParam)
            .where(AppParam.key.is_(key))
            .values(value=value, description=description)
            .returning(AppParam)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        param = result.scalar_one_or_none()

        # If not exists - create new
        if not param:
            param = AppParam(key=key, value=value, description=description)
            self.session.add(param)
            await self.session.commit()
            await self.session.refresh(param)

        return param

    async def delete_param(self, key: str) -> bool:
        param = await self.get_param(key)
        if param:
            await self.session.delete(param)
            await self.session.commit()
            return True
        return False
