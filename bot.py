import asyncio
import logging

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import BOT_TOKEN, SUPER_ADMIN_ID
from database import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = Database()


# ══════════════════════════════════════════════
#  FSM STATES
# ══════════════════════════════════════════════
class CategoryFSM(StatesGroup):
    waiting_name = State()
    waiting_item_name = State()
    waiting_item_chance = State()
    waiting_item_media = State()

class EditItemFSM(StatesGroup):
    waiting_chance = State()
    waiting_media = State()

class ModFSM(StatesGroup):
    waiting_id = State()


# ══════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════
def is_super(user_id: int) -> bool:
    return user_id == SUPER_ADMIN_ID

def user_mention(user: types.User) -> str:
    if user.username:
        return f"@{user.username}"
    return user.full_name

def plural_rolls(n: int) -> str:
    if n == 1:
        return "ролл"
    if 2 <= n <= 4:
        return "ролла"
    return "роллов"


# ══════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════
def kb_main(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📋 Список категорий",      callback_data="list_cats")],
        [InlineKeyboardButton(text="➕ Создать категорию",     callback_data="create_cat")],
        [InlineKeyboardButton(text="🎲 Крутить",               callback_data="spin_select")],
        [InlineKeyboardButton(text="⚙️ Управление",            callback_data="manage_select")],
        [InlineKeyboardButton(text="📜 История роллов",        callback_data="history")],
    ]
    if is_super(user_id):
        rows.append([InlineKeyboardButton(text="👥 Модераторы", callback_data="mods_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_back_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ])

def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
    ])

def kb_cats(categories, action: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"{action}:{cat_id}")]
        for cat_id, name in categories
    ]
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_spin_count(cat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1×", callback_data=f"doroll:{cat_id}:1"),
            InlineKeyboardButton(text="2×", callback_data=f"doroll:{cat_id}:2"),
            InlineKeyboardButton(text="3×", callback_data=f"doroll:{cat_id}:3"),
        ],
        [
            InlineKeyboardButton(text="4×", callback_data=f"doroll:{cat_id}:4"),
            InlineKeyboardButton(text="5×", callback_data=f"doroll:{cat_id}:5"),
            InlineKeyboardButton(text="6×", callback_data=f"doroll:{cat_id}:6"),
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="spin_select")],
    ])

def kb_manage_cat(cat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить предмет",          callback_data=f"additem:{cat_id}")],
        [InlineKeyboardButton(text="✏️ Редактировать предметы",   callback_data=f"edit_items:{cat_id}")],
        [InlineKeyboardButton(text="🗑️ Удалить предмет",          callback_data=f"delitem_list:{cat_id}")],
        [InlineKeyboardButton(text="🗑️ Удалить категорию",        callback_data=f"delcat:{cat_id}")],
        [InlineKeyboardButton(text="🔙 Назад",                     callback_data="manage_select")],
    ])

def kb_after_item(cat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить ещё",      callback_data=f"additem:{cat_id}")],
        [InlineKeyboardButton(text="✅ Готово",             callback_data=f"finish_cat:{cat_id}")],
        [InlineKeyboardButton(text="🗑️ Удалить категорию", callback_data=f"delcat:{cat_id}")],
    ])

def kb_skip_media(cat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Пропустить (без медиа)", callback_data=f"skip_media:{cat_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")],
    ])

def kb_edit_items(items, cat_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for item_id, name, chance, file_id, media_type in items:
        icon = "🖼️ " if file_id else ""
        buttons.append([InlineKeyboardButton(
            text=f"{icon}{name} ({chance}%)",
            callback_data=f"edit_item:{item_id}:{cat_id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage:{cat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_edit_item_actions(item_id: int, cat_id: int, has_media: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="✏️ Изменить %",      callback_data=f"editpct:{item_id}:{cat_id}")],
        [InlineKeyboardButton(text="🖼️ Изменить медиа",  callback_data=f"editmedia:{item_id}:{cat_id}")],
    ]
    if has_media:
        rows.append([InlineKeyboardButton(text="🗑️ Убрать медиа", callback_data=f"removemedia:{item_id}:{cat_id}")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"edit_items:{cat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_mods(moderators) -> InlineKeyboardMarkup:
    rows = []
    for uid, uname, _ in moderators:
        label = uname if uname else str(uid)
        rows.append([InlineKeyboardButton(text=f"❌ Удалить {label}", callback_data=f"del_mod:{uid}")])
    rows.append([InlineKeyboardButton(text="➕ Добавить модератора", callback_data="add_mod")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_approve_delcat(cat_id: int, requester_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Разрешить", callback_data=f"approve_delcat:{cat_id}:{requester_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"deny_delcat:{cat_id}:{requester_id}"),
    ]])

def kb_approve_delitem(item_id: int, cat_id: int, requester_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Разрешить", callback_data=f"approve_delitem:{item_id}:{cat_id}:{requester_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"deny_delitem:{item_id}:{cat_id}:{requester_id}"),
    ]])


# ══════════════════════════════════════════════
#  UTILS
# ══════════════════════════════════════════════
def cat_info_text(cat_id: int) -> str:
    cat = db.get_category(cat_id)
    items = db.get_items(cat_id)
    if not cat:
        return "❌ Категория не найдена."
    total = sum(i[2] for i in items)
    warn = " ⚠️ (сумма ≠ 100%!)" if items and abs(total - 100) > 0.01 else ""
    lines = [f"📦 <b>{cat[1]}</b>\n"]
    if items:
        for _, name, chance, file_id, _ in items:
            icon = " 🖼️" if file_id else ""
            lines.append(f"  • {name} — <b>{chance}%</b>{icon}")
        lines.append(f"\n<b>Итого: {total:.2f}%{warn}</b>")
    else:
        lines.append("<i>Предметов пока нет.</i>")
    return "\n".join(lines)


# ══════════════════════════════════════════════
#  ACCESS GUARDS
# ══════════════════════════════════════════════
async def guard_msg(message: Message) -> bool:
    if not db.is_allowed(message.from_user.id):
        return False
    return True

async def guard_cb(callback: CallbackQuery) -> bool:
    if not db.is_allowed(callback.from_user.id):
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return False
    return True

async def guard_super_cb(callback: CallbackQuery) -> bool:
    if not is_super(callback.from_user.id):
        await callback.answer("❌ Только главный администратор!", show_alert=True)
        return False
    return True

async def guard_super_msg(message: Message) -> bool:
    if not is_super(message.from_user.id):
        return False
    return True


# ══════════════════════════════════════════════
#  /start220
# ══════════════════════════════════════════════
@dp.message(Command(commands=["start220"]))
async def cmd_start(message: Message, state: FSMContext):
    if not await guard_msg(message):
        return
    await state.clear()
    await message.answer(
        f"👋 <b>{message.from_user.full_name}</b>, добро пожаловать!\n\n"
        "🎰 <b>Система круток</b> — выберите действие:",
        parse_mode="HTML",
        reply_markup=kb_main(message.from_user.id),
    )


# ══════════════════════════════════════════════
#  ГЛАВНОЕ МЕНЮ
# ══════════════════════════════════════════════
@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(cb: CallbackQuery, state: FSMContext):
    if not await guard_cb(cb):
        return
    await state.clear()
    await cb.message.edit_text(
        "🎰 <b>Система круток</b> — выберите действие:",
        parse_mode="HTML",
        reply_markup=kb_main(cb.from_user.id),
    )
    await cb.answer()


# ══════════════════════════════════════════════
#  МОДЕРАТОРЫ
# ══════════════════════════════════════════════
@dp.callback_query(F.data == "mods_menu")
async def cb_mods_menu(cb: CallbackQuery):
    if not await guard_super_cb(cb):
        return
    mods = db.get_moderators()
    text = "👥 <b>Модераторы:</b>\n\n"
    if mods:
        for uid, uname, _ in mods:
            text += f"• {uname or uid} (ID: <code>{uid}</code>)\n"
    else:
        text += "<i>Пока нет.</i>\n"
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb_mods(mods))
    await cb.answer()

@dp.callback_query(F.data == "add_mod")
async def cb_add_mod(cb: CallbackQuery, state: FSMContext):
    if not await guard_super_cb(cb):
        return
    await state.set_state(ModFSM.waiting_id)
    await cb.message.edit_text(
        "➕ <b>Добавить модератора</b>\n\nОтправь Telegram ID:\n<i>Узнать у @userinfobot</i>",
        parse_mode="HTML", reply_markup=kb_cancel(),
    )
    await cb.answer()

@dp.message(ModFSM.waiting_id)
async def fsm_mod_id(message: Message, state: FSMContext):
    if not await guard_super_msg(message):
        return
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ ID должен быть числом.", reply_markup=kb_cancel())
        return
    if uid == SUPER_ADMIN_ID:
        await message.answer("ℹ️ Это уже главный администратор.", reply_markup=kb_main(message.from_user.id))
        await state.clear()
        return
    db.add_moderator(uid, str(uid))
    await state.clear()
    await message.answer(f"✅ Пользователь <code>{uid}</code> добавлен.", parse_mode="HTML", reply_markup=kb_main(message.from_user.id))

@dp.callback_query(F.data.startswith("del_mod:"))
async def cb_del_mod(cb: CallbackQuery):
    if not await guard_super_cb(cb):
        return
    uid = int(cb.data.split(":")[1])
    db.remove_moderator(uid)
    mods = db.get_moderators()
    text = "👥 <b>Модераторы обновлены:</b>\n\n"
    for mid, uname, _ in mods:
        text += f"• {uname or mid} (ID: <code>{mid}</code>)\n"
    if not mods:
        text += "<i>Нет модераторов.</i>"
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb_mods(mods))
    await cb.answer(f"Удалён {uid}")


# ══════════════════════════════════════════════
#  СПИСОК КАТЕГОРИЙ
# ══════════════════════════════════════════════
@dp.callback_query(F.data == "list_cats")
async def cb_list_cats(cb: CallbackQuery):
    if not await guard_cb(cb):
        return
    cats = db.get_categories()
    if not cats:
        await cb.message.edit_text(
            "📋 Категорий пока нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать", callback_data="create_cat")],
                [InlineKeyboardButton(text="🔙 Назад",   callback_data="main_menu")],
            ]),
        )
        await cb.answer()
        return
    lines = ["📋 <b>Все категории:</b>\n"]
    for cat_id, name in cats:
        items = db.get_items(cat_id)
        total = sum(i[2] for i in items)
        warn = " ⚠️" if items and abs(total - 100) > 0.01 else ""
        lines.append(f"▫️ <b>{name}</b> — {len(items)} предм. ({total:.1f}%){warn}")
    await cb.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb_cats(cats, action="viewcat"))
    await cb.answer()

@dp.callback_query(F.data.startswith("viewcat:"))
async def cb_view_cat(cb: CallbackQuery):
    if not await guard_cb(cb):
        return
    cat_id = int(cb.data.split(":")[1])
    await cb.message.edit_text(
        cat_info_text(cat_id), parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К списку", callback_data="list_cats")]
        ]),
    )
    await cb.answer()


# ══════════════════════════════════════════════
#  СОЗДАНИЕ КАТЕГОРИИ
# ══════════════════════════════════════════════
@dp.callback_query(F.data == "create_cat")
async def cb_create_cat(cb: CallbackQuery, state: FSMContext):
    if not await guard_cb(cb):
        return
    await state.set_state(CategoryFSM.waiting_name)
    await cb.message.edit_text(
        "➕ <b>Новая категория</b>\n\nВведите название:",
        parse_mode="HTML", reply_markup=kb_cancel(),
    )
    await cb.answer()

@dp.message(CategoryFSM.waiting_name)
async def fsm_cat_name(message: Message, state: FSMContext):
    if not await guard_msg(message):
        return
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("❌ Слишком короткое название.", reply_markup=kb_cancel())
        return
    cat_id = db.create_category(name, message.from_user.id)
    if cat_id is None:
        await message.answer(f"❌ Категория <b>{name}</b> уже существует.", parse_mode="HTML", reply_markup=kb_cancel())
        return
    await state.update_data(cat_id=cat_id, cat_name=name)
    await state.set_state(CategoryFSM.waiting_item_name)
    await message.answer(
        f"✅ Категория <b>{name}</b> создана!\n\nВведите название первого предмета:",
        parse_mode="HTML", reply_markup=kb_cancel(),
    )

@dp.message(CategoryFSM.waiting_item_name)
async def fsm_item_name(message: Message, state: FSMContext):
    if not await guard_msg(message):
        return
    item_name = message.text.strip()
    if not item_name:
        await message.answer("❌ Пустое название.", reply_markup=kb_cancel())
        return
    await state.update_data(cur_item=item_name)
    data = await state.get_data()
    items = db.get_items(data["cat_id"])
    used = sum(i[2] for i in items)
    await state.set_state(CategoryFSM.waiting_item_chance)
    await message.answer(
        f"📝 Предмет: <b>{item_name}</b>\n\n"
        f"Введите шанс (%):\n"
        f"<i>Использовано: {used:.2f}%  |  Осталось: {100 - used:.2f}%</i>",
        parse_mode="HTML", reply_markup=kb_cancel(),
    )

@dp.message(CategoryFSM.waiting_item_chance)
async def fsm_item_chance(message: Message, state: FSMContext):
    if not await guard_msg(message):
        return
    raw = message.text.strip().replace(",", ".").replace("%", "")
    try:
        chance = float(raw)
        if chance <= 0 or chance > 100:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное число (например: 25 или 1.5)", reply_markup=kb_cancel())
        return
    data = await state.get_data()
    cat_id = data["cat_id"]
    item_name = data["cur_item"]
    items = db.get_items(cat_id)
    used = sum(i[2] for i in items)
    if used + chance > 100.001:
        await message.answer(
            f"❌ Сумма превысит 100%! Максимум: <b>{100 - used:.2f}%</b>",
            parse_mode="HTML", reply_markup=kb_cancel(),
        )
        return
    item_id = db.add_item(cat_id, item_name, chance)
    await state.update_data(cur_item_id=item_id)
    await state.set_state(CategoryFSM.waiting_item_media)
    await message.answer(
        f"✅ <b>{item_name}</b> ({chance}%) добавлен!\n\n"
        f"🖼️ Отправьте фото или GIF для этого предмета.\n"
        f"<i>Или нажмите «Пропустить».</i>",
        parse_mode="HTML",
        reply_markup=kb_skip_media(cat_id),
    )

@dp.message(CategoryFSM.waiting_item_media, F.photo | F.animation)
async def fsm_item_media(message: Message, state: FSMContext):
    if not await guard_msg(message):
        return
    data = await state.get_data()
    cat_id = data["cat_id"]
    item_id = data.get("cur_item_id")
    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = "photo"
    else:
        file_id = message.animation.file_id
        media_type = "animation"
    if item_id:
        db.update_item_media(item_id, file_id, media_type)
    await state.set_state(CategoryFSM.waiting_item_name)
    text = cat_info_text(cat_id)
    total_after = sum(i[2] for i in db.get_items(cat_id))
    suffix = "\n\n🎉 <b>Сумма ровно 100%!</b>" if abs(total_after - 100) < 0.01 else f"\n\n➕ Осталось: <b>{100 - total_after:.2f}%</b>"
    await message.answer(f"✅ Медиа сохранено!\n\n{text}{suffix}", parse_mode="HTML", reply_markup=kb_after_item(cat_id))

@dp.callback_query(F.data.startswith("skip_media:"))
async def cb_skip_media(cb: CallbackQuery, state: FSMContext):
    if not await guard_cb(cb):
        return
    cat_id = int(cb.data.split(":")[1])
    await state.set_state(CategoryFSM.waiting_item_name)
    text = cat_info_text(cat_id)
    total_after = sum(i[2] for i in db.get_items(cat_id))
    suffix = "\n\n🎉 <b>Сумма ровно 100%!</b>" if abs(total_after - 100) < 0.01 else f"\n\n➕ Осталось: <b>{100 - total_after:.2f}%</b>"
    await cb.message.edit_text(f"{text}{suffix}", parse_mode="HTML", reply_markup=kb_after_item(cat_id))
    await cb.answer()

@dp.callback_query(F.data.startswith("additem:"))
async def cb_additem(cb: CallbackQuery, state: FSMContext):
    if not await guard_cb(cb):
        return
    cat_id = int(cb.data.split(":")[1])
    cat = db.get_category(cat_id)
    if not cat:
        await cb.answer("❌ Категория не найдена", show_alert=True)
        return
    items = db.get_items(cat_id)
    used = sum(i[2] for i in items)
    await state.update_data(cat_id=cat_id, cat_name=cat[1])
    await state.set_state(CategoryFSM.waiting_item_name)
    await cb.message.edit_text(
        f"➕ Добавление в <b>{cat[1]}</b>\n"
        f"Использовано: {used:.2f}%  |  Осталось: {100 - used:.2f}%\n\nВведите название:",
        parse_mode="HTML", reply_markup=kb_cancel(),
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("finish_cat:"))
async def cb_finish_cat(cb: CallbackQuery, state: FSMContext):
    if not await guard_cb(cb):
        return
    cat_id = int(cb.data.split(":")[1])
    await state.clear()
    await cb.message.edit_text(
        f"✅ <b>Категория сохранена!</b>\n\n{cat_info_text(cat_id)}",
        parse_mode="HTML", reply_markup=kb_main(cb.from_user.id),
    )
    await cb.answer("✅ Готово!")


# ══════════════════════════════════════════════
#  РЕДАКТИРОВАНИЕ ПРЕДМЕТОВ
# ══════════════════════════════════════════════
@dp.callback_query(F.data.startswith("edit_items:"))
async def cb_edit_items(cb: CallbackQuery):
    if not await guard_cb(cb):
        return
    cat_id = int(cb.data.split(":")[1])
    cat = db.get_category(cat_id)
    items = db.get_items(cat_id)
    if not items:
        await cb.answer("❌ Нет предметов!", show_alert=True)
        return
    await cb.message.edit_text(
        f"✏️ <b>Редактировать — {cat[1]}</b>\n\n🖼️ = есть медиа\n\nВыберите предмет:",
        parse_mode="HTML",
        reply_markup=kb_edit_items(items, cat_id),
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("edit_item:"))
async def cb_edit_item(cb: CallbackQuery):
    if not await guard_cb(cb):
        return
    parts = cb.data.split(":")
    item_id, cat_id = int(parts[1]), int(parts[2])
    item = db.get_item(item_id)
    if not item:
        await cb.answer("❌ Предмет не найден", show_alert=True)
        return
    _, name, chance, file_id, media_type = item
    media_status = f"есть ({media_type})" if file_id else "нет"
    await cb.message.edit_text(
        f"✏️ <b>{name}</b>\n\nШанс: <b>{chance}%</b>\nМедиа: <b>{media_status}</b>\n\nЧто изменить?",
        parse_mode="HTML",
        reply_markup=kb_edit_item_actions(item_id, cat_id, bool(file_id)),
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("editpct:"))
async def cb_editpct(cb: CallbackQuery, state: FSMContext):
    if not await guard_cb(cb):
        return
    parts = cb.data.split(":")
    item_id, cat_id = int(parts[1]), int(parts[2])
    item = db.get_item(item_id)
    if not item:
        await cb.answer("❌ Предмет не найден", show_alert=True)
        return
    all_items = db.get_items(cat_id)
    used_without = sum(i[2] for i in all_items if i[0] != item_id)
    await state.update_data(edit_item_id=item_id, edit_cat_id=cat_id, used_without=used_without)
    await state.set_state(EditItemFSM.waiting_chance)
    await cb.message.edit_text(
        f"✏️ <b>{item[1]}</b> — сейчас <b>{item[2]}%</b>\n\n"
        f"Введите новый шанс (%):\n"
        f"<i>Другие предметы: {used_without:.2f}%  |  Доступно: {100 - used_without:.2f}%</i>",
        parse_mode="HTML", reply_markup=kb_cancel(),
    )
    await cb.answer()

@dp.message(EditItemFSM.waiting_chance)
async def fsm_edit_chance(message: Message, state: FSMContext):
    if not await guard_msg(message):
        return
    raw = message.text.strip().replace(",", ".").replace("%", "")
    try:
        chance = float(raw)
        if chance <= 0 or chance > 100:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное число.", reply_markup=kb_cancel())
        return
    data = await state.get_data()
    item_id = data["edit_item_id"]
    cat_id = data["edit_cat_id"]
    used_without = data["used_without"]
    if used_without + chance > 100.001:
        await message.answer(
            f"❌ Превышает 100%! Максимум: <b>{100 - used_without:.2f}%</b>",
            parse_mode="HTML", reply_markup=kb_cancel(),
        )
        return
    db.update_item_chance(item_id, chance)
    await state.clear()
    await message.answer(
        f"✅ Шанс обновлён!\n\n{cat_info_text(cat_id)}",
        parse_mode="HTML", reply_markup=kb_main(message.from_user.id),
    )

@dp.callback_query(F.data.startswith("editmedia:"))
async def cb_editmedia(cb: CallbackQuery, state: FSMContext):
    if not await guard_cb(cb):
        return
    parts = cb.data.split(":")
    item_id, cat_id = int(parts[1]), int(parts[2])
    item = db.get_item(item_id)
    if not item:
        await cb.answer("❌ Предмет не найден", show_alert=True)
        return
    await state.update_data(edit_item_id=item_id, edit_cat_id=cat_id)
    await state.set_state(EditItemFSM.waiting_media)
    await cb.message.edit_text(
        f"🖼️ <b>{item[1]}</b>\n\nОтправьте новое фото или GIF:",
        parse_mode="HTML", reply_markup=kb_cancel(),
    )
    await cb.answer()

@dp.message(EditItemFSM.waiting_media, F.photo | F.animation)
async def fsm_edit_media(message: Message, state: FSMContext):
    if not await guard_msg(message):
        return
    data = await state.get_data()
    item_id = data["edit_item_id"]
    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = "photo"
    else:
        file_id = message.animation.file_id
        media_type = "animation"
    db.update_item_media(item_id, file_id, media_type)
    await state.clear()
    item = db.get_item(item_id)
    await message.answer(
        f"✅ Медиа для <b>{item[1] if item else '???'}</b> обновлено!",
        parse_mode="HTML", reply_markup=kb_main(message.from_user.id),
    )

@dp.callback_query(F.data.startswith("removemedia:"))
async def cb_removemedia(cb: CallbackQuery):
    if not await guard_cb(cb):
        return
    parts = cb.data.split(":")
    item_id, cat_id = int(parts[1]), int(parts[2])
    item = db.get_item(item_id)
    db.update_item_media(item_id, None, None)
    await cb.message.edit_text(
        f"✅ Медиа удалено у <b>{item[1] if item else '???'}</b>.",
        parse_mode="HTML", reply_markup=kb_main(cb.from_user.id),
    )
    await cb.answer("Медиа удалено")


# ══════════════════════════════════════════════
#  КРУТИТЬ (SPIN)
# ══════════════════════════════════════════════
@dp.callback_query(F.data == "spin_select")
async def cb_spin_select(cb: CallbackQuery):
    if not await guard_cb(cb):
        return
    cats = db.get_categories()
    if not cats:
        await cb.message.edit_text(
            "❌ Нет категорий. Сначала создайте!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать", callback_data="create_cat")],
                [InlineKeyboardButton(text="🔙 Назад",   callback_data="main_menu")],
            ]),
        )
        await cb.answer()
        return
    await cb.message.edit_text(
        "🎲 <b>Выберите категорию:</b>",
        parse_mode="HTML", reply_markup=kb_cats(cats, action="spincat"),
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("spincat:"))
async def cb_spincat(cb: CallbackQuery):
    if not await guard_cb(cb):
        return
    cat_id = int(cb.data.split(":")[1])
    cat = db.get_category(cat_id)
    if not cat:
        await cb.answer("❌ Категория не найдена", show_alert=True)
        return
    if not db.get_items(cat_id):
        await cb.answer("❌ В категории нет предметов!", show_alert=True)
        return
    await cb.message.edit_text(
        f"🎲 <b>{cat[1]}</b> — сколько раз крутить?",
        parse_mode="HTML", reply_markup=kb_spin_count(cat_id),
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("doroll:"))
async def cb_doroll(cb: CallbackQuery):
    if not await guard_cb(cb):
        return
    _, cat_id_s, count_s = cb.data.split(":")
    cat_id = int(cat_id_s)
    count = int(count_s)
    cat = db.get_category(cat_id)
    if not cat:
        await cb.answer("❌ Категория не найдена", show_alert=True)
        return
    user = cb.from_user
    mention = user_mention(user)
    results = []
    for _ in range(count):
        r = db.roll(cat_id)
        if r:
            results.append(r)
            db.save_roll(user.id, user.full_name, cat_id, cat[1], r[0])

    roll_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Крутить снова", callback_data=f"spincat:{cat_id}")],
        [InlineKeyboardButton(text="🔙 Главное меню",  callback_data="main_menu")],
    ])

    lines = [
        f"🎰 <b>{cat[1]}</b>",
        f"👤 <b>Игрок:</b> {mention}",
        "",
        f"<b>Результаты ({count} {plural_rolls(count)}):</b>",
        "",
    ]
    for i, (name, file_id, media_type) in enumerate(results, 1):
        lines.append(f"  {i}. 🎯 <b>{name}</b>")

    text = "\n".join(lines)

    # Один ролл с медиа — показываем медиа сразу
    if count == 1 and results and results[0][1]:
        name, file_id, media_type = results[0]
        try:
            if media_type == "photo":
                await cb.message.answer_photo(file_id, caption=text, parse_mode="HTML", reply_markup=roll_kb)
            else:
                await cb.message.answer_animation(file_id, caption=text, parse_mode="HTML", reply_markup=roll_kb)
            await cb.message.delete()
        except Exception:
            await cb.message.edit_text(text, parse_mode="HTML", reply_markup=roll_kb)
    else:
        # Несколько роллов — текст + медиа отдельными сообщениями
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=roll_kb)
        for name, file_id, media_type in results:
            if file_id:
                try:
                    if media_type == "photo":
                        await cb.message.answer_photo(file_id, caption=f"🎯 <b>{name}</b>", parse_mode="HTML")
                    else:
                        await cb.message.answer_animation(file_id, caption=f"🎯 <b>{name}</b>", parse_mode="HTML")
                except Exception:
                    pass

    await cb.answer("🎲 Готово!")


# ══════════════════════════════════════════════
#  УПРАВЛЕНИЕ КАТЕГОРИЯМИ
# ══════════════════════════════════════════════
@dp.callback_query(F.data == "manage_select")
async def cb_manage_select(cb: CallbackQuery):
    if not await guard_cb(cb):
        return
    cats = db.get_categories()
    if not cats:
        await cb.message.edit_text(
            "⚙️ Категорий нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать", callback_data="create_cat")],
                [InlineKeyboardButton(text="🔙 Назад",   callback_data="main_menu")],
            ]),
        )
        await cb.answer()
        return
    await cb.message.edit_text(
        "⚙️ <b>Управление — выберите категорию:</b>",
        parse_mode="HTML", reply_markup=kb_cats(cats, action="manage"),
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("manage:"))
async def cb_manage_cat(cb: CallbackQuery):
    if not await guard_cb(cb):
        return
    cat_id = int(cb.data.split(":")[1])
    await cb.message.edit_text(
        cat_info_text(cat_id), parse_mode="HTML",
        reply_markup=kb_manage_cat(cat_id),
    )
    await cb.answer()


# ══════════════════════════════════════════════
#  УДАЛЕНИЕ КАТЕГОРИИ
# ══════════════════════════════════════════════
@dp.callback_query(F.data.startswith("delcat:"))
async def cb_delcat(cb: CallbackQuery):
    if not await guard_cb(cb):
        return
    cat_id = int(cb.data.split(":")[1])
    cat = db.get_category(cat_id)
    if not cat:
        await cb.answer("❌ Категория не найдена", show_alert=True)
        return
    requester = cb.from_user
    await bot.send_message(
        SUPER_ADMIN_ID,
        f"⚠️ <b>Запрос на удаление категории</b>\n\n"
        f"👤 {user_mention(requester)} (ID: <code>{requester.id}</code>)\n"
        f"📦 Категория: <b>{cat[1]}</b>\n\nРазрешить?",
        parse_mode="HTML",
        reply_markup=kb_approve_delcat(cat_id, requester.id),
    )
    await cb.message.edit_text("⏳ Запрос отправлен администратору.", reply_markup=kb_back_main())
    await cb.answer()

@dp.callback_query(F.data.startswith("approve_delcat:"))
async def cb_approve_delcat(cb: CallbackQuery):
    if not await guard_super_cb(cb):
        return
    parts = cb.data.split(":")
    cat_id, requester_id = int(parts[1]), int(parts[2])
    cat = db.get_category(cat_id)
    name = cat[1] if cat else "???"
    db.delete_category(cat_id)
    await cb.message.edit_text(f"✅ Категория <b>{name}</b> удалена.", parse_mode="HTML")
    try:
        await bot.send_message(requester_id, f"✅ Удаление категории <b>{name}</b> одобрено.", parse_mode="HTML")
    except Exception:
        pass
    await cb.answer("Удалено!")

@dp.callback_query(F.data.startswith("deny_delcat:"))
async def cb_deny_delcat(cb: CallbackQuery):
    if not await guard_super_cb(cb):
        return
    parts = cb.data.split(":")
    cat_id, requester_id = int(parts[1]), int(parts[2])
    cat = db.get_category(cat_id)
    name = cat[1] if cat else "???"
    await cb.message.edit_text(f"❌ Удаление <b>{name}</b> отклонено.", parse_mode="HTML")
    try:
        await bot.send_message(requester_id, f"❌ Удаление категории <b>{name}</b> отклонено.", parse_mode="HTML")
    except Exception:
        pass
    await cb.answer("Отклонено")


# ══════════════════════════════════════════════
#  УДАЛЕНИЕ ПРЕДМЕТА
# ══════════════════════════════════════════════
@dp.callback_query(F.data.startswith("delitem_list:"))
async def cb_delitem_list(cb: CallbackQuery):
    if not await guard_cb(cb):
        return
    cat_id = int(cb.data.split(":")[1])
    cat = db.get_category(cat_id)
    items = db.get_items(cat_id)
    if not items:
        await cb.answer("❌ Нет предметов!", show_alert=True)
        return
    buttons = [
        [InlineKeyboardButton(text=f"🗑️ {name} ({chance}%)", callback_data=f"delitem:{item_id}:{cat_id}")]
        for item_id, name, chance, _, _ in items
    ]
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage:{cat_id}")])
    await cb.message.edit_text(
        f"🗑️ <b>Удалить предмет из «{cat[1]}»</b>\n\nВыберите:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("delitem:"))
async def cb_delitem(cb: CallbackQuery):
    if not await guard_cb(cb):
        return
    parts = cb.data.split(":")
    item_id, cat_id = int(parts[1]), int(parts[2])
    item = db.get_item(item_id)
    cat = db.get_category(cat_id)
    if not item or not cat:
        await cb.answer("❌ Не найдено", show_alert=True)
        return
    requester = cb.from_user
    await bot.send_message(
        SUPER_ADMIN_ID,
        f"⚠️ <b>Запрос на удаление предмета</b>\n\n"
        f"👤 {user_mention(requester)} (ID: <code>{requester.id}</code>)\n"
        f"📦 Категория: <b>{cat[1]}</b>\n"
        f"🎯 Предмет: <b>{item[1]}</b> ({item[2]}%)\n\nРазрешить?",
        parse_mode="HTML",
        reply_markup=kb_approve_delitem(item_id, cat_id, requester.id),
    )
    await cb.message.edit_text("⏳ Запрос отправлен администратору.", reply_markup=kb_back_main())
    await cb.answer()

@dp.callback_query(F.data.startswith("approve_delitem:"))
async def cb_approve_delitem(cb: CallbackQuery):
    if not await guard_super_cb(cb):
        return
    parts = cb.data.split(":")
    item_id, cat_id, requester_id = int(parts[1]), int(parts[2]), int(parts[3])
    item = db.get_item(item_id)
    item_name = item[1] if item else "???"
    db.delete_item(item_id)
    await cb.message.edit_text(f"✅ Предмет <b>{item_name}</b> удалён.", parse_mode="HTML")
    try:
        await bot.send_message(requester_id, f"✅ Удаление предмета <b>{item_name}</b> одобрено.", parse_mode="HTML")
    except Exception:
        pass
    await cb.answer("Удалено!")

@dp.callback_query(F.data.startswith("deny_delitem:"))
async def cb_deny_delitem(cb: CallbackQuery):
    if not await guard_super_cb(cb):
        return
    parts = cb.data.split(":")
    item_id, cat_id, requester_id = int(parts[1]), int(parts[2]), int(parts[3])
    item = db.get_item(item_id)
    item_name = item[1] if item else "???"
    await cb.message.edit_text(f"❌ Удаление <b>{item_name}</b> отклонено.", parse_mode="HTML")
    try:
        await bot.send_message(requester_id, f"❌ Удаление предмета <b>{item_name}</b> отклонено.", parse_mode="HTML")
    except Exception:
        pass
    await cb.answer("Отклонено")


# ══════════════════════════════════════════════
#  ИСТОРИЯ РОЛЛОВ
# ══════════════════════════════════════════════
@dp.callback_query(F.data == "history")
async def cb_history(cb: CallbackQuery):
    if not await guard_cb(cb):
        return
    rows = db.get_history(limit=20)
    if not rows:
        await cb.message.edit_text("📜 История пуста.", reply_markup=kb_back_main())
        await cb.answer()
        return
    lines = ["📜 <b>Последние 20 роллов:</b>\n"]
    for user_name, cat_name, result, rolled_at in rows:
        dt = rolled_at[:16] if rolled_at else "?"
        lines.append(f"<b>{user_name}</b> — {cat_name} → 🎯 <b>{result}</b>  <i>{dt}</i>")
    await cb.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb_back_main())
    await cb.answer()


# ══════════════════════════════════════════════
#  НЕИЗВЕСТНЫЕ СООБЩЕНИЯ — молчим
# ══════════════════════════════════════════════
@dp.message()
async def unknown_msg(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        return


# ══════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════
async def main():
    logger.info("Bot started.")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
