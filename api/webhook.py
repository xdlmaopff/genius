import asyncio
import logging
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest
from aiohttp import web

# ────────────────────────────────────────────────
TOKEN = "8486942529:AAGZr9pbzh7b4vM-qs8_zuGzoBt_dLru62E"
ADMIN_CHAT_ID = -5270508762              # чат админов
CHANNEL_ID = -1003665236800              # канал проекта (пока не используем авто-добавление)
PROJECT_LINK = "https://t.me/+7IoWGj4ZCKs2NmRi"

CHECK_SUBSCRIPTION_BEFORE_FORM = True

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
# ────────────────────────────────────────────────


class Form(StatesGroup):
    city = State()
    age = State()
    experience = State()
    photo = State()


WELCOME_TEXT = f"""Привет!
Это проект Могильный долг.
Задания: избиения, поджоги и т.п.
Оплата высокая.

Сначала нужно быть подписанным на канал:

🔗 {PROJECT_LINK}

После подписки жми кнопку ниже ↓"""


async def is_subscribed(user_id: int) -> bool:
    if not CHECK_SUBSCRIPTION_BEFORE_FORM:
        return True
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ("member", "administrator", "creator", "restricted")
    except TelegramBadRequest:
        return False


# ──── Уведомления пользователю ───────────────────────────────────

async def notify_accepted(user_id: int):
    try:
        await bot.send_message(
            user_id,
            "✅ Твоя анкета **принята**!\n\n"
            "С тобой скоро свяжутся по личным сообщениям.\n"
            "Будь на связи и не пропускай сообщения от админов."
        )
    except Exception:
        pass  # если заблокировал бота — ничего страшного


async def send_rejection(user_id: int):
    try:
        await bot.send_message(
            user_id,
            "❌ К сожалению, по данной анкете принято решение **отказать**.\n"
            "Спасибо за отклик!"
        )
    except Exception:
        pass


# ──── Обработчики ─────────────────────────────────────────────────

@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.clear()

    if await is_subscribed(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Я подписался", callback_data="confirmed")]
        ])
        await message.answer(WELCOME_TEXT, reply_markup=kb)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться на канал", url=PROJECT_LINK)],
            [InlineKeyboardButton(text="Проверить подписку", callback_data="check_sub_again")]
        ])
        await message.answer("❗ Сначала подпишись на канал", reply_markup=kb)


@dp.callback_query(lambda c: c.data == "check_sub_again")
async def check_again(callback: types.CallbackQuery):
    if await is_subscribed(callback.from_user.id):
        await callback.message.edit_text(
            WELCOME_TEXT,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Я подписался", callback_data="confirmed")]
            ])
        )
    else:
        await callback.answer("Подписка не найдена 😕", show_alert=True)


@dp.callback_query(lambda c: c.data == "confirmed")
async def confirmed(callback: types.CallbackQuery, state: FSMContext):
    if not await is_subscribed(callback.from_user.id):
        await callback.answer("Сначала подпишись на канал!", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Отлично! Заполняем анкету.\n\nГород?")
    await state.set_state(Form.city)
    await callback.answer()


@dp.message(Form.city)
async def process_city(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await message.answer("Возраст?")
    await state.set_state(Form.age)


@dp.message(Form.age)
async def process_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Нужны только цифры")
        return
    await state.update_data(age=message.text)
    await message.answer("Коротко об опыте (улица/спорт/силовики/другое)")
    await state.set_state(Form.experience)


@dp.message(Form.experience)
async def process_exp(message: types.Message, state: FSMContext):
    await state.update_data(experience=message.text.strip())
    await message.answer("Фото (по желанию). Если нет — пиши «нет»")
    await state.set_state(Form.photo)


@dp.message(Form.photo)
async def process_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    username = message.from_user.username or f"id{user_id}"

    admin_text = (
        f"🆕 <b>НОВАЯ АНКЕТА</b>\n"
        f"От: @{username}  [{user_id}]\n"
        f"Город: {data.get('city', '-')}\n"
        f"Возраст: {data.get('age', '-')}\n"
        f"Опыт: {data.get('experience', '-')}\n"
        f"Фото: {'есть' if message.photo else 'нет'}\n\n"
        f"Решение:"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{user_id}"),
            InlineKeyboardButton(text="❌ Отказать", callback_data=f"reject_{user_id}")
        ]
    ])

    if message.photo:
        await bot.send_photo(
            ADMIN_CHAT_ID,
            message.photo[-1].file_id,
            caption=admin_text,
            reply_markup=kb,
            parse_mode="HTML"
        )
    else:
        await bot.send_message(
            ADMIN_CHAT_ID,
            admin_text,
            reply_markup=kb,
            parse_mode="HTML"
        )

    await message.answer("Анкета отправлена на рассмотрение.\nОжидай решения.")
    await state.clear()


# ──── Решения админов ─────────────────────────────────────────────

@dp.callback_query(lambda c: c.data.startswith("accept_"))
async def process_accept(callback: types.CallbackQuery):
    try:
        user_id = int(callback.data.split("_")[1])

        if callback.message.caption is not None:
            # Есть подпись — добавляем к существующей
            new_caption = callback.message.caption + "\n✅ <b>Принят</b> (свяжутся вручную)"
            await callback.message.edit_caption(
                caption=new_caption,
                reply_markup=None,
                parse_mode="HTML"
            )
        else:
            # Нет подписи — редактируем как обычный текст
            new_text = (callback.message.text or "🆕 НОВАЯ АНКЕТА") + "\n\n✅ <b>Принят</b> (свяжутся вручную)"
            await callback.message.edit_text(
                text=new_text,
                reply_markup=None,
                parse_mode="HTML"
            )

        await notify_accepted(user_id)
        await callback.answer("Принято")

    except Exception as e:
        logging.error(f"Ошибка при принятии: {e}")
        await callback.answer("Ошибка", show_alert=True)


@dp.callback_query(lambda c: c.data.startswith("reject_"))
async def process_reject(callback: types.CallbackQuery):
    try:
        user_id = int(callback.data.split("_")[1])
        await send_rejection(user_id)

        if callback.message.caption is not None:
            new_caption = callback.message.caption + "\n❌ <b>Отказано</b>"
            await callback.message.edit_caption(
                caption=new_caption,
                reply_markup=None,
                parse_mode="HTML"
            )
        else:
            new_text = (callback.message.text or "🆕 НОВАЯ АНКЕТА") + "\n\n❌ <b>Отказано</b>"
            await callback.message.edit_text(
                text=new_text,
                reply_markup=None,
                parse_mode="HTML"
            )

        await callback.answer("Отказано")

    except Exception as e:
        logging.error(f"Ошибка при отказе: {e}")
        await callback.answer("Ошибка", show_alert=True)

app = web.Application()

async def webhook_handler(request):
    data = await request.json()
    update = types.Update(**data)
    await dp.feed_update(bot, update)
    return web.Response(text="OK")

app.router.add_post("/", webhook_handler)

handler = app

async def main():
    import os
    webhook_url = os.environ.get("WEBHOOK_URL")
    if webhook_url:
        await bot.set_webhook(webhook_url)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

if __name__ == "__main__":
    asyncio.run(main())
