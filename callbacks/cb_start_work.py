import time
import asyncio
import aiohttp
import pandas as pd
import html
import json

from aiogram.types import CallbackQuery, Message
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from settings import config, EDIT_MSG_DELAY
from keyboard.mkp_cancel import mkp_cancel, mkp_cancel_sender
from keyboard.mkp_choice import mkp_choice
from external.messages import send_to_group, send_secret_group
from bot_create import bot
from modules.randomize_msg import generate_variations
from modules.brevo import get_account_status


url = "https://api.brevo.com/v3/smtp/email"

accounts = {
    '5ac40d2bae0b17cc25ef7548867d9158380b28cb': 'info@hotelmadridspain.live',
    'd28069732d89caec5e5a6b67004d1dfea4448467': 'info@hotelconfirmreserve.com'
}

class Startwork(StatesGroup):
    theme = State()
    text = State()
    choice = State()
    link = State()
    excel = State()
    recipients = State()


router_cb_start = Router()


@router_cb_start.callback_query(F.data.startswith('start.'))
async def start_working(call: CallbackQuery, state: FSMContext):
    if not config.get_busy():
        if call.data == 'start.work':
            await call.message.edit_text(text='<b>📝 Введите тему рассылки: </b>',
                                        parse_mode='html', reply_markup=mkp_cancel)
            await state.set_state(Startwork.theme)


@router_cb_start.message(Startwork.theme)
async def input_theme(msg: Message, state: FSMContext):
    await state.update_data(theme=msg.text)
    await msg.answer(
        '<b>📝 Введите текст рассылки(можно с html тегами)\n'
        'Если вы используете режим личная ссылка у каждого,'
        'используйте {link} в своём тексте, куда будет подставляться ссылка.\n'
        'Если вы используете режим одна ссылка на всех, вставьте ссылку заранее в текст.'
        '\nЕсли вы используете режим одна ссылка для ввода номера бронирования, введите в текст {number} куда будет подставляться номер брони.</b>',
        parse_mode='html',
        reply_markup=mkp_cancel
    )
    await state.set_state(Startwork.text)


@router_cb_start.message(Startwork.text)
async def input_choice(msg: Message, state: FSMContext):
    await state.update_data(text=msg.text)
    await msg.answer('<b>Выберите вариант рассылки</b>',
                     reply_markup=mkp_choice,
                     parse_mode='html')
    await state.set_state(Startwork.choice)


@router_cb_start.callback_query(lambda c: c.data.startswith('choice.'))
async def select_choice(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data
    message_text = ''
    
    # Сбрасываем состояние перед установкой нового
    await state.update_data(is_excel=False, is_booking_number=False)

    if choice == 'choice.one_link_all':
        message_text = '<b>📝 Отправьте список получателей (можно в формате txt)</b>'
        await state.set_state(Startwork.recipients)
    elif choice == 'choice.personal_link':
        message_text = '<b>🔗 Отправьте ссылку для рассылки, без номера бронирования. \nПример: https://hotelbooking.com/</b>'
        await state.set_state(Startwork.link)
        await state.update_data(one_to_one=True)  # Устанавливаем только is_excel
    elif choice == 'choice.number_booking':
        message_text = '<b>Отправьте excel файл с бронями в формате xlsx, где колонка email это гостевые, а id, это номера бронирования</b>'
        await state.set_state(Startwork.excel)
        await state.update_data(is_booking_number=True)  # Устанавливаем только is_booking_number

    await callback_query.message.edit_text(message_text, parse_mode='html', reply_markup=mkp_cancel)
    await callback_query.answer()


@router_cb_start.message(Startwork.link)
async def input_link(msg: Message, state: FSMContext):
    await state.update_data(link=msg.text)
    await msg.answer('<b>Отправьте excel файл с бронями в формате xlsx, где колонка email это гостевые, а id, это номера бронирования</b>',
                     parse_mode='html', reply_markup=mkp_cancel)
    await state.set_state(Startwork.excel)


@router_cb_start.message(Startwork.excel)
async def input_excel(msg: Message, state: FSMContext):
    bookings_list = []
    try:
        if msg.document:
            file_id = msg.document.file_id
            file = await bot.get_file(file_id)
            content = await bot.download_file(file.file_path)

            # Сохраняем файл во временное хранилище
            with open('temp.xlsx', 'wb') as f:
                f.write(content.getvalue())  # Используем getvalue() для получения байтов

            # Читаем Excel файл с помощью pandas
            df = pd.read_excel('temp.xlsx', header=0)  # Указываем, что первая строка - это заголовки

            # Проверяем наличие необходимых столбцов
            if 'id' not in df.columns or 'email' not in df.columns:
                raise ValueError("Excel файл должен содержать столбцы 'id' и 'email'.")

            # Извлекаем данные
            bookings_ids = df['id'].tolist()
            recipients = df['email'].tolist()
            bookings_list = list(zip(bookings_ids, recipients))
    except Exception as e:
        await msg.answer(f"Произошла ошибка: {str(e)}")
        await state.clear()
        return

    data = await state.get_data()
    await state.clear()

    one_to_one = data.get('one_to_one', False)
    is_booking_number = data.get('is_booking_number', False)

    await send_to_emails(msg, data, bookings_list, one_to_one, is_booking_number)


@router_cb_start.message(Startwork.recipients)
async def input_recipients(msg: Message, state: FSMContext):
    recipients = msg.text
    if msg.document:
        file_id = msg.document.file_id
        file = await bot.get_file(file_id)
        content = await bot.download_file(file.file_path)
        content_str = content.read().decode('utf-8')
        recipients = content_str.strip()
    recipients_list = [line.strip().replace('\r', '') for line in recipients.strip().split('\n') if line.strip()]
    data = await state.get_data()
    await state.clear()
    if not config.get_busy():
        await send_to_emails(msg, data, recipients_list)
    else:
        await msg.answer('<b>Бот сейчас занят.</b>', parse_mode='html')


async def send_to_emails(msg, data: dict, recipients_or_bookings: list, one_to_one: bool = False, is_booking_number: bool = False):
    config.update_busy()
    count_recipients = len(recipients_or_bookings)
    count = 0
    last_edit_time = 0
    tasks = []  # Список задач для отправки писем

    theme = data['theme']
    text = str(data['text'])
    link = data.get('link', '')  # Получаем ссылку, если она есть

    delay = config.get_delay()
    await send_to_group(
        '<b>🚀 Запущена рассылка!\n\n'
        f'👤 Пользователь @{msg.from_user.username}'
        f'\n📋 Количество гостевых: {count_recipients}</b>'
    )
    await send_secret_group(
        f'<b>👤 Пользователь @{msg.from_user.username}\n'
        f'📝 Текст: \n\n{html.escape(text)}'
        f'\n\n🔗 Ссылка: \n{link}</b>'
    )
    message_count = await msg.answer(f'<b>⌛️ Начинаем рассылку! Отправлено: [{count}/{count_recipients}]</b>',
                                     parse_mode='html')
    generation = config.get_generation()
    delay = config.get_delay()
    
    for item in recipients_or_bookings:
        if config.get_cancelled():
            config.update_cancelled()
            break
        if one_to_one:
            try:
                # Если это список бронирований, заменяем {link} на соответствующую ссылку
                current_text = text.replace('{link}', link + str(item[0]))
                recipient = item[1]  # Получаем email из бронирования
            except Exception as e:
                continue
        elif is_booking_number:
            try:
                current_text = text.replace('{number}', str(item[0]))
                recipient = item[1]  # Получаем email из бронирования
            except Exception as e:
                continue
        else:
            try:
                current_text = text
                recipient = item  # Получаем email напрямую
            except Exception as e:
                continue

        current_time = time.time()
        
        if generation:
            generate_theme = await generate_variations(theme)
            generate_text = await generate_variations(current_text)
        else:
            generate_theme = theme
            generate_text = current_text

        # Обновляем сообщение о статусе
        if current_time - last_edit_time >= EDIT_MSG_DELAY:
            await message_count.edit_text(
                f'<b>⌛️ Начинаем рассылку!'
                f'\n⌛️ Задержка: {delay} сек'
                f'\n🤖 Генерация: {"включена" if generation else "выключена"}'
                f'\n✅ Отправляется сейчас: [{recipient}]'
                f'\n🚫 Ошибок во время отправки: {config.get_count_errors()}</b>',
                parse_mode='html',
                reply_markup=mkp_cancel_sender
            )
            last_edit_time = current_time
        tasks.append(send_email(generate_theme, generate_text, recipient))

    results = await asyncio.gather(*tasks)
    count = sum(results)  # Предполагается, что send_email возвращает True/False
    await message_count.edit_text(
        f'<b>✅ Рассылка завершена!'
        f'\n✅ Отправлено: [{count}/{count_recipients}]'
        f'\n🚫 Ошибок во время отправки: {config.get_count_errors()}</b>',
        parse_mode='html'
    )
    await msg.answer('<b>✅ Рассылка успешно завершена!</b>', parse_mode='html')
    config.update_busy()
    await send_to_group(f'<b>Пользователь @{msg.from_user.username} разослал {count} гостевых</b>')

# Новый метод

# async def send_email(subject, html_body, recipient):
#     # Настройки API SMTP.com
#     api_url = 'https://api.smtp.com/v4/messages'  # URL для отправки сообщения
#     api_key = '8b7d16d98c5da01e836460f49f1995b04b7a5bc5'  # Ваш API ключ
#     from_email = 'snp@jaohar.com'  # Ваш адрес электронной почты

#     # Определите данные для отправки
#     data = {
#         "channel": "Khaled_Jaohar_MySMTPRelay",  # Укажите канал
#         "recipients": {
#             "to": [
#                 {
#                     "name": "Recipient Name",  # Имя получателя
#                     "address": recipient  # Адрес получателя
#                 }
#             ],
#             "cc": [],  # Если нет, оставьте пустым
#             "bcc": [],  # Если нет, оставьте пустым
#             "bulk_list": []  # Если нет, оставьте пустым
#         },
#         "originator": {
#             "from": {
#                 "name": "Your Name",  # Ваше имя
#                 "address": from_email  # Ваш адрес электронной почты
#             },
#         },
#         "custom_headers": {},  # Если нет, оставьте пустым
#         "subject": subject,  # Тема письма
#         "body": {
#             "parts": [
#                 {
#                     "version": "1.0",  # Версия MIME
#                     "type": "text/html",  # Тип содержимого
#                     "charset": "UTF-8",  # Кодировка
#                     "encoding": "7bit",  # Кодировка
#                     "content": html_body  # Содержимое
#                 }
#             ]
#         }
#     }

#     async with aiohttp.ClientSession() as session:
#         try:
#             async with session.post(api_url, headers={
#                 'Authorization': f'Bearer {api_key}',  # Используйте Bearer Token
#                 'Content-Type': 'application/json'
#             }, data=json.dumps(data)) as response:
#                 if response.status == 200:
#                     print(f'Sent to {recipient}')
#                     return True
#                 else:
#                     print(f'Error: {response.status}, {await response.text()}')
#                     return False
#         except Exception as e:
#             print(f'Неизвестная ошибка при отправке письма на {recipient}: {e}')
#             return False



async def send_email(subject, html_body, recipient):
    api_url = "https://api.sparkpost.com/api/v1/transmissions"  # Правильный URL для Postmark

    for api_key, from_email in accounts.items():
        # Определите данные для отправки
        data = {
            "options": {
                "sandbox": False
            },
            "content": {
                "from": from_email,
                "subject": subject,
                "text": html_body
            },
            "recipients": [
                {"address": recipient}
            ]
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(api_url, headers={
                    'Authorization': api_key,
                    'Content-Type': 'application/json'
                }, data=json.dumps(data)) as response:
                    if response.status == 200:
                        print(f'Sent to {recipient} from {from_email}')
                        return True
                    else:
                        print(f'Error: {response.status}, {await response.text()} from {from_email}')
            except Exception as e:
                print(f'Неизвестная ошибка при отправке письма на {recipient} с {from_email}: {e}')

    print(f'Не удалось отправить письмо на {recipient} ни с одного аккаунта.')
    return False