import asyncio
import logging
from datetime import datetime, time, timedelta
import pytz
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# === НАСТРОЙКИ ===
BOT_TOKEN = "9197077046:AAGATKd-_dp7savLXHc9jNUwxgXEsfOFUcU"
CHANNEL_ID = -1004498116844
CHANNEL_URL = "https://t.me/FreeScriptBB"
DISCORD_URL = "https://discord.gg/w8qBZRH6N"
TIKTOK_URL = "https://www.tiktok.com/@freescriptsfi"

# Список администраторов
ADMIN_IDS = [1969246093, 1902638202]

SUPPORT_USERNAME = "Lizkagerganova"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Черный список заблокированных пользователей (хранит ID)
BLACKLIST = set()

# Словарь для хранения активных задач авто-одобрения по ID пользователя
active_tasks = {}

# Переменные для сбора ежедневной статистики (ТОЛЬКО обычные пользователи)
stats_total_requests = 0
stats_approved = 0
stats_rejected = 0


class QuestState(StatesGroup):
    waiting_for_screenshot = State()


# 1. Главная клавиатура
def get_main_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎁 Получить скрипт", callback_data="select_script"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Техническая поддержка",
                    url=f"https://t.me/{SUPPORT_USERNAME}",
                )
            ],
        ]
    )


# 2. Прямой список доступных скриптов
def get_script_choice_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📜 Kukirin Life (Авто-фарм)",
                    callback_data="script_kukirin_autofarm",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 Kukirin Life (AutoWheelie)",
                    callback_data="script_kukirin_autowheelie",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 Drive A Kukirin", callback_data="script_drive_kukirin"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 Universal Script", callback_data="script_universal"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 Скрипт для RIVALS",
                    callback_data="script_rivals",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Назад в меню", callback_data="back_to_main"
                )
            ],
        ]
    )


# 3. Клавиатура с шагами (подписка, тикток, скрин)
def get_quest_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 1. Подписаться на ТГК", url=CHANNEL_URL
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎵 2. Наш TikTok", url=TIKTOK_URL
                )
            ],
            [
                InlineKeyboardButton(
                    text="📸 Отправить скриншот TikTok",
                    callback_data="upload_screen",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Я всё выполнил", callback_data="check_all"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Назад к списку скриптов",
                    callback_data="select_script",
                )
            ],
        ]
    )


# 4. Финальная клавиатура со ссылкой (только для одобренных)
def get_discord_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Получить скрипт в Discord", url=DISCORD_URL
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Техническая поддержка",
                    url=f"https://t.me/{SUPPORT_USERNAME}",
                )
            ],
        ]
    )


# Функция формирования текста отчета
def generate_stats_report():
    return (
        f"📊 **Статистика запросов от пользователей:**\n\n"
        f"📥 Всего запросов: `{stats_total_requests}`\n"
        f"✅ Принятых отчетов (одобрено): `{stats_approved}`\n"
        f"❌ Отклоненных отчетов: `{stats_rejected}`"
    )


# Фоновая задача отправки отчета в 00:00 по МСК
async def daily_stats_scheduler():
    global stats_total_requests, stats_approved, stats_rejected
    msk_tz = pytz.timezone("Europe/Moscow")

    while True:
        now_msk = datetime.now(msk_tz)
        target_time = msk_tz.localize(
            datetime.combine(now_msk.date(), time(0, 0))
        )
        if now_msk >= target_time:
            target_time += timedelta(days=1)

        wait_seconds = (target_time - now_msk).total_seconds()
        await asyncio.sleep(wait_seconds)

        report = "🌙 **Автоматический ночной отчет за день:**\n\n" + generate_stats_report()

        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=admin_id, text=report, parse_mode="Markdown"
                )
            except Exception as e:
                logging.error(
                    f"Не удалось отправить ежедневный отчет админу {admin_id}: {e}"
                )

        stats_total_requests = 0
        stats_approved = 0
        stats_rejected = 0


# Секретная команда /report для проверки статистики
@dp.message(Command("report"))
async def admin_report_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    report = "📈 **Текущая статистика (с начала дня):**\n\n" + generate_stats_report()
    await message.reply(report, parse_mode="Markdown")


# Секретная команда /ban <ID> для добавления в черный список
@dp.message(Command("ban"))
async def admin_ban_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.reply(
            "⚠️ Используй правильный формат:\n`/ban ID_пользователя`",
            parse_mode="Markdown",
        )
        return

    user_id_to_ban = int(args[1])
    if user_id_to_ban in ADMIN_IDS:
        await message.reply("❌ Нельзя заблокировать администратора!")
        return

    BLACKLIST.add(user_id_to_ban)
    await message.reply(f"✅ Пользователь с ID `{user_id_to_ban}` успешно добавлен в черный список.",
                        parse_mode="Markdown")


# Секретная команда /unban <ID> для удаления из черного списка
@dp.message(Command("unban"))
async def admin_unban_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.reply(
            "⚠️ Используй правильный формат:\n`/unban ID_пользователя`",
            parse_mode="Markdown",
        )
        return

    user_id_to_unban = int(args[1])
    if user_id_to_unban in BLACKLIST:
        BLACKLIST.remove(user_id_to_unban)
        await message.reply(f"✅ Пользователь с ID `{user_id_to_unban}` удален из черного списка.",
                            parse_mode="Markdown")
    else:
        await message.reply("⚠️ Этот пользователь не найден в черном списке.")


# Старт — Главное меню
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    # Проверка на бан
    if message.from_user.id in BLACKLIST:
        await message.answer("❌ Вы заблокированы и не можете использовать этого бота.")
        return

    text = (
        f"👋 **Привет, {message.from_user.first_name}!**\n\n"
        "🔥 Добро пожаловать! Здесь ты можешь получить эксклюзивные **скрипты для Roblox**.\n\n"
        "Выбери нужный пункт в меню ниже:"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_kb())


# Возврат в главное меню
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id in BLACKLIST:
        await callback.answer("❌ Вы заблокированы!", show_alert=True)
        return

    await state.clear()
    text = (
        f"👋 **Привет, {callback.from_user.first_name}!**\n\n"
        "🔥 Добро пожаловать! Здесь ты можешь получить эксклюзивные **скрипты для Roblox**.\n\n"
        "Выбери нужный пункт в меню ниже:"
    )
    await callback.message.edit_text(
        text, parse_mode="Markdown", reply_markup=get_main_kb()
    )


# Прямой показ списка скриптов
@dp.callback_query(F.data == "select_script")
async def choose_script(callback: types.CallbackQuery):
    if callback.from_user.id in BLACKLIST:
        await callback.answer("❌ Вы заблокированы и не можете использовать этого бота.", show_alert=True)
        return

    text = "🎮 **Выбери нужный скрипт из списка:**"
    await callback.message.edit_text(
        text, parse_mode="Markdown", reply_markup=get_script_choice_kb()
    )


# Обработчики выбора скриптов
@dp.callback_query(F.data.startswith("script_"))
async def select_script_handler(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id in BLACKLIST:
        await callback.answer("❌ Вы заблокированы!", show_alert=True)
        return

    script_data = callback.data
    script_names = {
        "script_kukirin_autofarm": "Kukirin Life (Авто-фарм)",
        "script_kukirin_autowheelie": "Kukirin Life (AutoWheelie)",
        "script_drive_kukirin": "Drive A Kukirin",
        "script_universal": "Universal Script",
        "script_rivals": "RIVALS"
    }

    selected_name = script_names.get(script_data, "Скрипт")
    await state.update_data(selected_script=selected_name)
    await show_instruction_steps(callback)


# Общая функция для показа инструкции
async def show_instruction_steps(callback: types.CallbackQuery):
    text = (
        "📌 **Инструкция по получению скрипта:**\n\n"
        "1️⃣ Подпишись на наш **Telegram-канал**.\n"
        "2️⃣ Поставь реакции на последние посты в канале.\n"
        "3️⃣ Подпишись на наш **TikTok** и просто отправь сюда скриншот подписки.\n\n"
        "После отправки скриншота нажми кнопку **«Я всё выполнил»**."
    )
    await callback.message.edit_text(
        text, parse_mode="Markdown", reply_markup=get_quest_kb()
    )


# Запрос скриншота
@dp.callback_query(F.data == "upload_screen")
async def ask_screenshot(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id in BLACKLIST:
        await callback.answer("❌ Вы заблокированы!", show_alert=True)
        return

    await state.set_state(QuestState.waiting_for_screenshot)
    await callback.message.answer(
        "📸 **Отправь скриншот** подписки на TikTok прямо в этот чат:"
    )
    await callback.answer()


# Автоматическое считывание скриншота
@dp.message(QuestState.waiting_for_screenshot, F.photo)
async def receive_screenshot(message: types.Message, state: FSMContext):
    if message.from_user.id in BLACKLIST:
        await message.answer("❌ Вы заблокированы.")
        return

    photo_id = message.photo[-1].file_id
    await state.update_data(screenshot_id=photo_id)
    await state.set_state(None)
    await message.answer(
        "✅ **Скриншот успешно принят и сохранен!**\nТеперь нажми кнопку **«Я всё выполнил»**.",
        reply_markup=get_quest_kb(),
    )


# Фоновая задача: авто-одобрение за 15 секунд
async def auto_approve_task(
        user_id: int,
        admin_msg_ids: list,
        selected_script: str,
        user_first_name: str,
        username_str: str,
):
    global stats_approved
    try:
        await asyncio.sleep(15)
    except asyncio.CancelledError:
        return

    active_tasks.pop(user_id, None)

    if user_id not in ADMIN_IDS:
        stats_approved += 1

    for admin_id, msg_id in admin_msg_ids:
        try:
            current_caption = (
                "🚨 **Запрос на получение скрипта!**\n\n"
                f"📜 **Выбранный скрипт:** {selected_script}\n"
                f"👤 **Имя:** {user_first_name}\n"
                f"🔗 **Юзернейм:** {username_str}\n"
                f"🆔 ID пользователя: `{user_id}`\n\n"
                "🟢 **СТАТУС: Автоматически одобрено ✅**"
            )
            await bot.edit_message_caption(
                chat_id=admin_id,
                message_id=msg_id,
                caption=current_caption,
                parse_mode="Markdown",
                reply_markup=None,
            )
        except Exception:
            pass

    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                "🎉 **Администратор подтвердил твой запрос!**\n\n"
                "Забирай свою ссылку на Discord-сервер со скриптом:"
            ),
            parse_mode="Markdown",
            reply_markup=get_discord_kb(),
        )
    except Exception as e:
        logging.error(f"Не удалось отправить сообщение авто-одобрения пользователю: {e}")


# Проверка условий и отправка запроса всем админам
@dp.callback_query(F.data == "check_all")
async def check_conditions(callback: types.CallbackQuery, state: FSMContext):
    global stats_total_requests
    user = callback.from_user

    if user.id in BLACKLIST:
        await callback.answer("❌ Вы заблокированы и не можете использовать этого бота.", show_alert=True)
        return

    data = await state.get_data()
    screenshot_id = data.get("screenshot_id")
    selected_script = data.get("selected_script", "Kukirin Life")

    if user.id not in ADMIN_IDS:
        stats_total_requests += 1

    if user.id in active_tasks:
        active_tasks[user.id].cancel()

    is_tg_subscribed = False
    try:
        member = await bot.get_chat_member(
            chat_id=CHANNEL_ID, user_id=user.id
        )
        if member.status in ["member", "administrator", "creator"]:
            is_tg_subscribed = True
    except Exception as e:
        logging.error(f"Ошибка проверки ТГ: {e}")

    if not is_tg_subscribed:
        await callback.answer(
            "❌ Вы не подписаны на наш Telegram-канал!", show_alert=True
        )
        return

    if not screenshot_id:
        await callback.answer(
            "❌ Вы не отправили скриншот подписки на TikTok!", show_alert=True
        )
        return

    admin_action_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить", callback_data=f"approve_{user.id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить", callback_data=f"reject_{user.id}"
                ),
            ]
        ]
    )

    username_str = f"@{user.username}" if user.username else "отсутствует"
    report_text = (
        "🚨 **Запрос на получение скрипта!**\n\n"
        f"📜 **Выбранный скрипт:** {selected_script}\n"
        f"👤 **Имя:** {user.first_name}\n"
        f"🔗 **Юзернейм:** {username_str}\n"
        f"🆔 **ID:** `{user.id}`\n"
        f"📢 **Подписка на ТГК:** ✅ Подтверждена\n"
        f"🎵 **TikTok:** ✅ Скриншот приложен ниже\n\n"
        "⏳ *Если не ответить за 15 сек, запрос одобрится сам.*"
    )

    admin_msg_ids = []

    for admin_id in ADMIN_IDS:
        try:
            sent_message = await bot.send_photo(
                chat_id=admin_id,
                photo=screenshot_id,
                caption=report_text,
                parse_mode="Markdown",
                reply_markup=admin_action_kb,
            )
            admin_msg_ids.append((admin_id, sent_message.message_id))
        except Exception as e:
            logging.error(f"Не удалось отправить отчет админу {admin_id}: {e}")

    if admin_msg_ids:
        task = asyncio.create_task(
            auto_approve_task(
                user.id,
                admin_msg_ids,
                selected_script,
                user.first_name,
                username_str,
            )
        )
        active_tasks[user.id] = task

    text = (
        "⏳ **Запрос отправлен администратору!**\n\n"
        "Подожди немного, скоро администратор проверит твой скриншот и выдаст ссылку."
    )
    await callback.message.edit_text(text, parse_mode="Markdown")


# Реакция админа на кнопку «Одобрить»
@dp.callback_query(F.data.startswith("approve_"))
async def admin_approve(callback: types.CallbackQuery):
    global stats_approved
    target_user_id = int(callback.data.split("_")[1])

    if target_user_id in active_tasks:
        active_tasks[target_user_id].cancel()
        active_tasks.pop(target_user_id, None)

    if target_user_id not in ADMIN_IDS:
        stats_approved += 1

    try:
        await bot.send_message(
            chat_id=target_user_id,
            text=(
                "🎉 **Администратор подтвердил твой запрос!**\n\n"
                "Забирай свою ссылку на Discord-сервер со скриптом:"
            ),
            parse_mode="Markdown",
            reply_markup=get_discord_kb(),
        )
    except Exception as e:
        logging.error(f"Не удалось отправить сообщение пользователю: {e}")

    original_caption = callback.message.caption or ""
    selected_script = "Не указан"
    user_first_name = "Неизвестно"
    username_str = "отсутствует"

    for line in original_caption.split("\n"):
        if "Выбранный скрипт:" in line and "📜" in line:
            selected_script = line.split("Выбранный скрипт:")[-1].strip()
        elif "Имя:" in line and "👤" in line:
            user_first_name = line.split("Имя:")[-1].strip()
        elif "Юзернейм:" in line and "🔗" in line:
            username_str = line.split("Юзернейм:")[-1].strip()

    updated_caption = (
        "🚨 **Запрос на получение скрипта!**\n\n"
        f"📜 **Выбранный скрипт:** {selected_script}\n"
        f"👤 **Имя:** {user_first_name}\n"
        f"🔗 **Юзернейм:** {username_str}\n"
        f"🆔 ID пользователя: `{target_user_id}`\n\n"
        "🟢 **СТАТУС: Одобрено администратором ✅**"
    )

    await callback.message.edit_caption(
        caption=updated_caption,
        parse_mode="Markdown",
        reply_markup=None,
    )
    await callback.answer("Запрос успешно одобрен!", show_alert=True)


# Реакция админа на кнопку «Отклонить»
@dp.callback_query(F.data.startswith("reject_"))
async def admin_reject(callback: types.CallbackQuery):
    global stats_rejected
    target_user_id = int(callback.data.split("_")[1])

    if target_user_id in active_tasks:
        active_tasks[target_user_id].cancel()
        active_tasks.pop(target_user_id, None)

    if target_user_id not in ADMIN_IDS:
        stats_rejected += 1

    try:
        await bot.send_message(
            chat_id=target_user_id,
            text=(
                "❌ **К сожалению, твой запрос был отклонен администратором.**\n\n"
                "Убедись, что ты правильно выполнил все условия, или попробуй снова."
            ),
            parse_mode="Markdown",
            reply_markup=get_main_kb(),
        )
    except Exception as e:
        logging.error(f"Не удалось отправить сообщение пользователю: {e}")

    original_caption = callback.message.caption or ""
    selected_script = "Не указан"
    user_first_name = "Неизвестно"
    username_str = "отсутствует"

    for line in original_caption.split("\n"):
        if "Выбранный скрипт:" in line and "📜" in line:
            selected_script = line.split("Выбранный скрипт:")[-1].strip()
        elif "Имя:" in line and "👤" in line:
            user_first_name = line.split("Имя:")[-1].strip()
        elif "Юзернейм:" in line and "🔗" in line:
            username_str = line.split("Юзернейм:")[-1].strip()

    updated_caption = (
        "🚨 **Запрос на получение скрипта!**\n\n"
        f"📜 **Выбранный скрипт:** {selected_script}\n"
        f"👤 **Имя:** {user_first_name}\n"
        f"🔗 **Юзернейм:** {username_str}\n"
        f"🆔 ID пользователя: `{target_user_id}`\n\n"
        "🔴 **СТАТУС: Отклонено ❌**"
    )

    await callback.message.edit_caption(
        caption=updated_caption,
        parse_mode="Markdown",
        reply_markup=None,
    )
    await callback.answer("Запрос отклонен.", show_alert=True)


async def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.create_task(daily_stats_scheduler())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())