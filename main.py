#!/usr/lib/python3 python
# -*- coding: utf-8 -*-
import os
import random
import sys
import threading
import urllib.request as ur
import telebot
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from PIL import Image  # Для преобразования изображений из webp в PNG

import config


# TODO: проверять, настроены ли тоннели
DEBUG_MODE = config.get_cell('debug_mode')
VK_MARK_AS_READ = config.get_cell('vk_mark_as_read')
TG_SEND_NAME = config.get_cell('telegram_send_name')
VK_STICKER_SCALE_ENABLE = config.get_cell('vk_sticker_scale_enable')

module = sys.modules[__name__]

global bot
global vk_session


#   __      ___
#   \ \    / / |
#    \ \  / /| | __
#     \ \/ / | |/ /
#      \  /  |   <
#       \/   |_|\_\
#


# Обработка двухфакторной аутентификации
def vk_auth_handler():
    key = input("Enter authentication code: ")
    remember_device = True
    return key, remember_device


# Обработка капчи
def vk_captcha_handler(captcha):
    key = input("Enter Captcha {0}: ".format(captcha.get_url())).strip()
    return captcha.try_again(key)


def vk_send_msg(vk_peer_id, text, tg_name=None):
    randid = random.randint(-9223372036854775808, +9223372036854775807)  # int64
    if tg_name:
        text = str(tg_name + ': ' + text)

    try:  # Костыль конечно, надо с ним что-то сделать
        module.vk.messages.send(chat_id=vk_peer_id, message=text, random_id=randid)
    except vk_api.ApiError as error_msg:
        if DEBUG_MODE:
            print("Error while sending message to chat_id, trying user_id")
        module.vk.messages.send(user_id=vk_peer_id, message=text, random_id=randid)


def vk_sticker_send(sticker_path, send_to):
    randid = random.randint(-9223372036854775808, +9223372036854775807)  # int64
    sticker_path = sticker_path + ".png"
    upload = vk_api.VkUpload(vk_session)
    graffiti = upload.graffiti(sticker_path, send_to)

    os.remove(sticker_path)

    try:
        module.vk.messages.send(chat_id=send_to, message="",
                                attachment='doc{owner_id}_{id}'.format(**graffiti['graffiti']), random_id=randid)
    except vk_api.ApiError as error_msg:
        if DEBUG_MODE:
            print("Error while sending message to chat_id, trying user_id")
        module.vk.messages.send(user_id=send_to, message="",
                                attachment='doc{owner_id}_{id}'.format(**graffiti['graffiti']), random_id=randid)


# Подключение api ВК
def vk_init():
    login = config.get_cell('vk_login')
    password = config.get_cell('vk_password')
    app_id = config.get_cell('app_id')

    global vk_session

    vk_session = vk_api.VkApi(login, password, app_id=app_id, auth_handler=vk_auth_handler, captcha_handler=vk_captcha_handler)

    try:
        vk_session.auth()
    except vk_api.AuthError as error_msg:
        print(error_msg)
    else:
        print("Logged in vk as: " + login)

    module.vk = vk_session.get_api()


def vk_handle_msg(event):
    if event.from_chat:
        forward_to = config.get_cell("vk_" + str(event.chat_id))
    elif event.from_user:
        forward_to = config.get_cell("vk_" + str(event.user_id))
    if forward_to and not event.from_me:
        if DEBUG_MODE:
            print("DEBUG: forwarding message from VK")
        dataname = module.vk.users.get(user_ids=event.user_id)
        name = str(dataname[0]['first_name'] + ' ' + dataname[0]['last_name'])
        tg_send_msg(forward_to, name, event.message)
        # Отмечаем диалог прочитанным, если включено
        if VK_MARK_AS_READ:
            module.vk.messages.markAsRead(peer_id=event.peer_id)


def vk_listen():
    longpoll = VkLongPoll(vk_session)
    while True:
        try:
            for event in longpoll.listen():
                if DEBUG_MODE:
                    print("DEBUG: got event", event.type, event.raw[1:])
                if event.type == VkEventType.MESSAGE_NEW:
                    vk_handle_msg(event)
                    module.vk.messages.markAsRead(peer_id=event.peer_id)
        except Exception as error_msg:
            if DEBUG_MODE:
                print(error_msg)
            continue


#    _______   _
#   |__   __| | |
#      | | ___| | ___  __ _ _ __ __ _ _ __ ___
#      | |/ _ \ |/ _ \/ _` | '__/ _` | '_ ` _ \
#      | |  __/ |  __/ (_| | | | (_| | | | | | |
#      |_|\___|_|\___|\__, |_|  \__,_|_| |_| |_|
#                      __/ |
#                     |___/

# TODO: в описание чата записывать список пользователей чата ВК (сверка при запуске, обновление при изменении списка)

def tg_send_msg(tg_chat_id, vk_name, text):
    formatted_text = str(vk_name + ': ' + text)
    bot.send_message(tg_chat_id, formatted_text)


def tg_sticker_download(sticker_url, path):
    dir_path = path.split('/')[0] + '/'
    full_path = dir_path + path.split('/')[1]

    content = ur.urlopen(sticker_url).read()

    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    # Перекодирование из webp в png
    image_webp = full_path

    with open(image_webp, 'wb') as out:
        out.write(content)

    img = Image.open(image_webp)

    if VK_STICKER_SCALE_ENABLE:
        scale = config.get_cell('vk_sticker_size')
        img.thumbnail((scale, scale))
    img.save(image_webp + ".png", "PNG")
    os.remove(image_webp)

    return full_path

# Разработчикам на заметку:
# Telegram та ещё поехавшая вещь, иногда аттачменты идут с расширением файла, иногда - без него
# Из-за этого я долго не мог понять, почему одни стикеры отправляются нормально, а другие - выдают ошибку при отправке


def tg_init():
    global bot
    bot = telebot.TeleBot(config.get_cell('telegram_token'))
    print("Logged in telegram")
    if config.get_cell('telegram_use_proxy'):
        proxy_type = str(config.get_cell('p_type'))
        proxy_user_info = str(config.get_cell('p_user') + ':' + config.get_cell('p_password'))
        proxy_data = str(config.get_cell('p_host') + ':' + config.get_cell('p_port'))
        telebot.apihelper.proxy = {
            'http': '%s://%s@%s' % (proxy_type, proxy_user_info, proxy_data),
            'https': '%s://%s@%s' % (proxy_type, proxy_user_info, proxy_data)
        }

    @bot.message_handler(commands=['chat_id'])
    def command_chat_id(m):
        bot.send_message(m.chat.id, str(m.chat.id))

    @bot.message_handler(func=lambda message: True, content_types=['text'])
    def tg_handle_msg(m):
        forward_to = config.get_cell('t_' + str(m.chat.id))
        if forward_to:
            if DEBUG_MODE:
                print("DEBUG: forwarding message from Telegram")
            if TG_SEND_NAME:
                if m.from_user.last_name:
                    vk_send_msg(forward_to, m.text, m.from_user.first_name + " " + m.from_user.last_name)
                else:
                    vk_send_msg(forward_to, m.text, m.from_user.first_name)
            else:
                vk_send_msg(forward_to, m.text)

    @bot.message_handler(func=lambda message: True, content_types=['sticker'])
    def tg_handle_sticker(m):
        if config.get_cell('vk_stickers_enable'):
            file_path = bot.get_file(m.sticker.file_id).file_path
            forward_to = config.get_cell('t_' + str(m.chat.id))
            if forward_to:
                if DEBUG_MODE:
                    print("DEBUG: forwarding sticker from Telegram")

                sticker_url = 'https://api.telegram.org/file/bot{0}/{1}'.format(config.get_cell('telegram_token'),
                                                                                file_path)
                sticker_path = tg_sticker_download(sticker_url, file_path)
                vk_sticker_send(sticker_path, forward_to)


def tg_listen():
    while True:
        try:
            bot.polling(none_stop=False)
        except Exception as error_msg:
            if DEBUG_MODE:
                print(error_msg)
            continue


vk_init()
tg_init()

thread1 = threading.Thread(target=vk_listen)
thread2 = threading.Thread(target=tg_listen)
thread1.start()
thread2.start()
thread1.join()
thread2.join()
