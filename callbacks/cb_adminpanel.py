from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram import Router, F
from aiogram.fsm.state import State, StatesGroup

from bot_create import api_key
from modules.brevo import get_account_status
from settings import config
from db.create_db import get_all_telegram_ids
from external.messages import send_to_users
from keyboard.mkp_cancel import mkp_cancel

class SetDelay(StatesGroup):
    setdelay = State()

class SetAdmin(StatesGroup):
    setadmin = State()
    
class SetUser(StatesGroup):
    setuser = State()

class SetCountMsg(StatesGroup):
    setcount = State()

class SendMessageAll(StatesGroup):
    text = State()

cb_adminpanel = Router()

@cb_adminpanel.callback_query(F.data.startswith('admin.'))
async def admin_panel(call: CallbackQuery, state: FSMContext):
    if call.data == 'admin.setdelay':
        delay = config.get_delay()
        await call.message.edit_text(f'<b>Текущая задержка: {delay}\n✅ Введите новую задержку между сообщениями: </b>', parse_mode='html')
        await state.set_state(SetDelay.setdelay)
    elif call.data == 'admin.setadmin':
        await call.message.edit_text(f'<b>✅ Введите айди нового администратора: </b>', parse_mode='html')
        await state.set_state(SetAdmin.setadmin)
    elif call.data == 'admin.setcount':
        count_messages = config.get_count_messages()
        await call.message.edit_text(f'<b>Текущее количество на 1 аккаунт: {count_messages}'
                                     '\n✅ Введите количество сообщений на 1 аккаунт: </b>', parse_mode='html')
        await state.set_state(SetCountMsg.setcount)
    elif call.data == 'admin.generation':
        if config.get_generation:
            config.update_generation()
            await call.message.edit_text(f'<b>🤖 Вы успешно {"включили" if config.get_generation() else "отключили"} генерацию</b>', parse_mode='html')
    elif call.data == 'admin.brevoinfo':
        await call.message.edit_text(
            f'<b>{await get_account_status(api_key)}</b>',
            parse_mode='html'
        )
    elif call.data == 'admin.sendall':
        await call.message.edit_text(
            f'<b>📢 Введите текст рассылки: (можно с html-тегами)</b>',
            parse_mode='html',
            reply_markup=mkp_cancel
        )
        await state.set_state(SendMessageAll.text)


@cb_adminpanel.message(SendMessageAll.text)
async def input_text(message: Message, state: FSMContext):
    all_users = await get_all_telegram_ids()
    succesfull_send = await send_to_users(all_users, message.text)
    await message.answer(f'<b>✅ Вы успешно отправили сообщение всем пользователям. Всего было отправлено: {succesfull_send}</b>', parse_mode='html')
    await state.clear()


@cb_adminpanel.message(SetDelay.setdelay)
async def setdelay(message: Message, state: FSMContext):
    try:
        delay = int(message.text)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите корректное целое число.")
        return
    config.update_delay(delay)
    await message.answer(f'<b>✅ Вы успешно установили задержку в {delay} секунд.</b>', parse_mode='html')
    await state.clear()
    

@cb_adminpanel.message(SetAdmin.setadmin)
async def setadmin(message: Message, state: FSMContext):
    try:
        admin = int(message.text)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите корректное целое число.")
        return
    config.set_admin(admin)
    await message.answer(f'<b>✅ Вы успешно добавили нового админа {admin}.</b>', parse_mode='html')
    await state.clear()


@cb_adminpanel.message(SetUser.setuser)
async def setuser(message: Message, state: FSMContext):
    try:
        user = int(message.text)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите корректное целое число.")
        return
    config.set_user(user)
    await message.answer(f'<b>✅ Вы успешно добавили нового пользователя {user}.</b>', parse_mode='html')
    await state.clear()


@cb_adminpanel.message(SetCountMsg.setcount)
async def set_count_msg(message: Message, state: FSMContext):
    try:
        count = int(message.text)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите корректное целое число.")
        return
    config.update_count_messages(count)
    await message.answer(f'<b>✅ Вы успешно установили количество сообщений на 1 аккаунт {count}.</b>', parse_mode='html')
    await state.clear()
