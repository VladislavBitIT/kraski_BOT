"""Definitions of FSM states used by the bot."""
from aiogram.fsm.state import State, StatesGroup


class LeadStates(StatesGroup):
    full_name = State()
    phone = State()
    done = State()


class CalculatorStates(StatesGroup):
    start = State()
    category_select = State()
    paint_select = State()
    q1_color = State()
    q2_area = State()
    q3_tool = State()
    q4_reserve = State()
    q5_surface = State()
    q6_primers = State()
    result = State()


class AdminStates(StatesGroup):
    waiting_excel = State()


STATE_SEQUENCE = [
    CalculatorStates.q1_color,
    CalculatorStates.q2_area,
    CalculatorStates.q3_tool,
    CalculatorStates.q4_reserve,
    CalculatorStates.q5_surface,
    CalculatorStates.q6_primers,
]
