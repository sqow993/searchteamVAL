from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    """Главное меню"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔗 Привязать Tracker", callback_data="link_tracker")
    builder.button(text="👤 Мой профиль", callback_data="my_profile")
    builder.button(text="🎮 Найти тиммейта", callback_data="find_teammate")
    builder.button(text="❌ Отвязать аккаунт", callback_data="unlink")
    builder.adjust(2, 2)
    return builder.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    """Кнопка возврата"""
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад в меню", callback_data="main_menu")
    return builder.as_markup()


def teammate_actions(telegram_id: int) -> InlineKeyboardMarkup:
    """Кнопки под карточкой найденного игрока"""
    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Написать", url=f"tg://user?id={telegram_id}")
    builder.button(text="🔄 Ещё", callback_data="find_teammate")
    builder.button(text="◀️ В меню", callback_data="main_menu")
    builder.adjust(1, 2)
    return builder.as_markup()