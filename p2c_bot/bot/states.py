from aiogram.fsm.state import State, StatesGroup


class ConfigureLimits(StatesGroup):
    values = State()
