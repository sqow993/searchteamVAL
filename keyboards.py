from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from config import RANKS


def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔗 Привязать аккаунт", callback_data="link_tracker")
    builder.button(text="👤 Мой профиль", callback_data="my_profile")
    builder.button(text="🎮 Найти 1 тиммейта", callback_data="find_teammate")
    builder.button(text="👥 Найти команду (5 игроков)", callback_data="find_team")
    builder.button(text="❌ Отвязать аккаунт", callback_data="unlink")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад в меню", callback_data="main_menu")
    return builder.as_markup()


def ranks_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for rank in RANKS:
        builder.button(text=rank, callback_data=f"set_rank:{rank}")
    builder.adjust(3)
    builder.button(text="◀️ Назад", callback_data="main_menu")
    return builder.as_markup()


def profile_menu() -> InlineKeyboardMarkup:
    """Меню в профиле"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Редактировать анкету", callback_data="edit_profile")
    builder.button(text="🏆 Изменить ранг", callback_data="change_rank")
    builder.button(text="◀️ В меню", callback_data="main_menu")
    builder.adjust(1, 1, 1)
    return builder.as_markup()


def profile_skip_keyboard() -> InlineKeyboardMarkup:
    """Кнопка «Пропустить» при заполнении анкеты"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Пропустить", callback_data="skip_field")
    builder.button(text="❌ Отмена", callback_data="main_menu")
    builder.adjust(2)
    return builder.as_markup()


def teammate_actions(telegram_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Написать в Telegram", url=f"tg://user?id={telegram_id}")
    builder.button(text="🔄 Ещё", callback_data="find_teammate")
    builder.button(text="◀️ В меню", callback_data="main_menu")
    builder.adjust(1, 2)
    return builder.as_markup()