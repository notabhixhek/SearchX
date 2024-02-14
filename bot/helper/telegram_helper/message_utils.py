import time
import threading

from telegram.error import RetryAfter

from bot import bot, LOGGER, Interval, STATUS_UPDATE_INTERVAL, \
    status_reply_dict, status_reply_dict_lock
from bot.helper.ext_utils.bot_utils import SetInterval, get_readable_message


def delete_user_message(bot, message, delay):
    """
    Delete user's message after a specified delay.
    """
    time.sleep(delay)
    deleteMessage(bot, message)

def delete_bot_message(bot, sent_message, delay):
    """
    Delete bot's message after a specified delay.
    """
    time.sleep(delay)
    deleteMessage(bot, sent_message)

def sendMessage(text, bot, message, reply_markup=None, user_delete_delay=60, bot_delete_delay=120):
    """
    Send a message and schedule deletion of user's and bot's messages based on the chat type.
    """
    try:
        if message.chat.type == "private":
            # For direct messages to the bot, do not schedule message deletions
            return bot.sendMessage(chat_id=message.chat_id,
                                    reply_to_message_id=message.message_id,
                                    text=text, reply_markup=reply_markup)

        # For group messages, schedule deletion of user's message
        user_delete_thread = threading.Thread(target=delete_user_message, args=(bot, message, user_delete_delay))
        user_delete_thread.start()

        sent_message = bot.sendMessage(chat_id=message.chat_id,
                                       reply_to_message_id=message.message_id,
                                       text=text, reply_markup=reply_markup)

        # Schedule deletion of bot's message
        bot_delete_thread = threading.Thread(target=delete_bot_message, args=(bot, sent_message, bot_delete_delay))
        bot_delete_thread.start()

        return sent_message
    except RetryAfter as r:
        LOGGER.warning(f"RetryAfter exception: {r}")
        time.sleep(r.retry_after * 1.5)
        return sendMessage(text, bot, message, reply_markup)
    except Exception as err:
        LOGGER.error(f"Error sending message: {err}")
        return

def editMessage(text, message, reply_markup=None):
    """
    Edit an existing message.
    """
    try:
        bot.editMessageText(chat_id=message.chat.id,
                            message_id=message.message_id,
                            text=text, reply_markup=reply_markup)
    except RetryAfter as r:
        LOGGER.warning(f"RetryAfter exception: {r}")
        time.sleep(r.retry_after * 1.5)
        return editMessage(text, message, reply_markup)
    except Exception as err:
        LOGGER.error(f"Error editing message: {err}")
        return

def deleteMessage(bot, message):
    """
    Delete a message.
    """
    try:
        bot.deleteMessage(chat_id=message.chat.id,
                          message_id=message.message_id)
    except Exception as e:
        LOGGER.error(f"Error deleting message: {e}")

def sendLogFile(bot, message):
    with open('log.txt', 'rb') as f:
        bot.sendDocument(document=f, filename=f.name,
                         chat_id=message.chat_id,
                         reply_to_message_id=message.message_id)

def delete_all_messages():
    with status_reply_dict_lock:
        for data in list(status_reply_dict.values()):
            try:
                deleteMessage(bot, data[0])
                del status_reply_dict[data[0].chat.id]
            except Exception as err:
                LOGGER.error(str(err))

def update_all_messages(force=False):
    with status_reply_dict_lock:
        if not status_reply_dict or not Interval or (not force and time.time() - list(status_reply_dict.values())[0][1] < 3):
            return
        for chat_id in status_reply_dict:
            status_reply_dict[chat_id][1] = time.time()
    msg = get_readable_message()
    if msg is None:
        return
    with status_reply_dict_lock:
        for chat_id in status_reply_dict:
            if status_reply_dict[chat_id] and msg != status_reply_dict[chat_id][0].text:
                rmsg = editMessage(msg, status_reply_dict[chat_id][0])
                if rmsg == "Message to edit not found":
                    del status_reply_dict[chat_id]
                    return
                status_reply_dict[chat_id][0].text = msg
                status_reply_dict[chat_id][1] = time.time()

def sendStatusMessage(msg, bot):
    progress = get_readable_message()
    if progress is None:
        return
    with status_reply_dict_lock:
        if msg.chat.id in status_reply_dict:
            message = status_reply_dict[msg.chat.id][0]
            deleteMessage(bot, message)
            del status_reply_dict[msg.chat.id]
        message = sendMessage(progress, bot, msg)
        status_reply_dict[msg.chat.id] = [message, time.time()]
        if not Interval:
            Interval.append(SetInterval(STATUS_UPDATE_INTERVAL, update_all_messages))
