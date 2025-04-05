from dao.param_dao import ParamDAO


class ParamService:
    def __init__(self, session):
        self.param_dao = ParamDAO(session)

    async def get_parameter(self, key: str, default: str = None) -> str | None:
        param = await self.param_dao.get_param(key)
        return param.value if param else default

    async def set_parameter(self, key: str, value: str, description: str = None) -> str:
        await self.param_dao.set_param(key, value, description)
        return f"Параметр {key} успешно обновлен"

    async def delete_parameter(self, key: str) -> str:
        if await self.param_dao.delete_param(key):
            return f"Параметр {key} удален"
        return f"Параметр {key} не найден"

    async def list_parameters(self) -> dict:
        params = await self.param_dao.get_all_params()
        return {p.key: p.value for p in params}
