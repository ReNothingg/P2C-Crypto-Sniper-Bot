from aiogram.fsm.state import State, StatesGroup


class ConnectAccount(StatesGroup):
    api_key = State()


class ConfigureLimits(StatesGroup):
    values = State()
