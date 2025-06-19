import os
import logging
import requests
import schedule
import time
import telebot
import threading
from dotenv import load_dotenv
from googletrans import Translator
from typing import Dict, Optional

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('weather_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

if not BOT_TOKEN or not WEATHER_API_KEY:
    logger.error("Не заданы необходимые переменные окружения!")
    raise ValueError("Требуется BOT_TOKEN и WEATHER_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)

# Хранение данных пользователей {chat_id: {"city": str, "language": str}}
users: Dict[int, Dict[str, str]] = {}
UPDATE_INTERVAL_MINUTES = 60  # Интервал обновлений в минутах
DEFAULT_LANGUAGE = 'ru'


class WeatherServiceError(Exception):
    pass


class TranslationError(Exception):
    pass


def get_weather(city: str, language: str = DEFAULT_LANGUAGE) -> str:
    """
    Получает данные о погоде для указанного города
    :param city: Название города
    :param language: Язык для описания погоды
    :return: Строка с информацией о погоде
    :raises: WeatherServiceError при ошибках API
    """
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang={language}"
        response = requests.get(url, timeout=10)
        data = response.json()

        if data.get("cod") != 200:
            error_message = data.get("message", "Unknown error")
            raise WeatherServiceError(f"API error: {error_message}")

        temperature = data["main"]["temp"]
        description = data["weather"][0]["description"]
        humidity = data["main"]["humidity"]
        wind_speed = data["wind"]["speed"]

        return (
            f"Погода в городе {city}:\n"
            f"🌡 Температура: {temperature}°C\n"
            f"☁️ Состояние: {description.capitalize()}\n"
            f"💧 Влажность: {humidity}%\n"
            f"💨 Скорость ветра: {wind_speed} м/с"
        )

    except requests.exceptions.RequestException as e:
        raise WeatherServiceError(f"Ошибка соединения: {str(e)}")
    except (KeyError, IndexError) as e:
        raise WeatherServiceError("Ошибка обработки данных погоды")


def translate_text(text: str, dest_language: str = DEFAULT_LANGUAGE) -> str:
    """
    Переводит текст на указанный язык
    :param text: Текст для перевода
    :param dest_language: Целевой язык
    :return: Переведенный текст
    :raises: TranslationError при ошибках перевода
    """
    try:
        translator = Translator()
        translated = translator.translate(text, dest=dest_language)
        return translated.text
    except Exception as e:
        raise TranslationError(f"Ошибка перевода: {str(e)}")


def send_weather_update(chat_id: int, city: str, language: str = DEFAULT_LANGUAGE):
    """
    Отправляет обновление погоды пользователю
    :param chat_id: ID чата пользователя
    :param city: Город для запроса погоды
    :param language: Язык для описания погоды
    """
    try:
        weather = get_weather(city, language)
        bot.send_message(chat_id, weather)
        logger.info(f"Weather update sent to {chat_id} for {city}")
    except WeatherServiceError as e:
        error_msg = f"Не удалось получить погоду для {city}: {str(e)}"
        bot.send_message(chat_id, error_msg)
        logger.error(error_msg)
    except Exception as e:
        logger.error(f"Unexpected error for {chat_id}: {str(e)}")


def send_updates_to_all_users():
    """Отправляет обновления погоды всем подписанным пользователям"""
    logger.info("Starting scheduled weather updates...")
    for chat_id, user_info in users.copy().items():  # Используем копию для безопасности
        try:
            send_weather_update(chat_id, user_info["city"], user_info.get("language", DEFAULT_LANGUAGE))
        except Exception as e:
            logger.error(f"Failed to update for {chat_id}: {str(e)}")
    logger.info("Scheduled updates completed")


def schedule_periodic_updates():
    """Запускает периодические обновления по расписанию"""
    schedule.every(UPDATE_INTERVAL_MINUTES).minutes.do(send_updates_to_all_users)
    logger.info(f"Weather updates scheduled every {UPDATE_INTERVAL_MINUTES} minutes")

    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            logger.error(f"Scheduler error: {str(e)}")
            time.sleep(60)  # Пауза при ошибке


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Обработчик команд /start и /help"""
    welcome_text = (
        "🌤️ Привет! Я бот погоды. Вот что я умею:\n\n"
        "/start - начать получать обновления погоды\n"
        "/stop - остановить обновления\n"
        "/change - изменить город\n"
        "/now - получить текущую погоду\n"
        "/language - изменить язык (ru/en)\n\n"
        "Отправь мне название города, и я начну присылать тебе погоду!"
    )
    bot.send_message(message.chat.id, welcome_text)
    bot.send_message(message.chat.id, "В каком городе ты хочешь получать погоду?")
    bot.register_next_step_handler(message, process_city_input)


def process_city_input(message):
    """Обрабатывает ввод города пользователем"""
    try:
        city = message.text.strip()
        # Проверяем город через тестовый запрос
        test_weather = get_weather(city)

        users[message.chat.id] = {
            "city": city,
            "language": DEFAULT_LANGUAGE
        }

        bot.send_message(
            message.chat.id,
            f"✅ Отлично! Теперь я буду присылать погоду для {city}.\n"
            f"Обновления будут приходить каждые {UPDATE_INTERVAL_MINUTES} минут.\n"
            f"Используй /now чтобы получить текущую погоду."
        )
        # Сразу отправляем первое обновление
        send_weather_update(message.chat.id, city)

    except WeatherServiceError as e:
        bot.send_message(
            message.chat.id,
            f"❌ Не удалось найти город '{message.text}'. Пожалуйста, попробуйте еще раз."
        )
        bot.register_next_step_handler(message, process_city_input)
    except Exception as e:
        logger.error(f"Error processing city input: {str(e)}")
        bot.send_message(
            message.chat.id,
            "⚠️ Произошла ошибка. Пожалуйста, попробуйте позже."
        )


@bot.message_handler(commands=['stop'])
def stop_updates(message):
    """Останавливает обновления для пользователя"""
    if message.chat.id in users:
        del users[message.chat.id]
        bot.send_message(message.chat.id, "🔴 Вы отменили подписку на обновления погоды.")
    else:
        bot.send_message(message.chat.id, "ℹ️ Вы не подписаны на обновления.")


@bot.message_handler(commands=['now'])
def send_current_weather(message):
    """Отправляет текущую погоду по запросу"""
    if message.chat.id not in users:
        bot.send_message(message.chat.id, "Сначала укажите город с помощью /start")
        return

    user_info = users[message.chat.id]
    try:
        bot.send_message(message.chat.id, "⏳ Запрашиваю актуальную погоду...")
        send_weather_update(message.chat.id, user_info["city"], user_info.get("language", DEFAULT_LANGUAGE))
    except Exception as e:
        logger.error(f"Error in /now command: {str(e)}")
        bot.send_message(message.chat.id, "⚠️ Не удалось получить погоду. Попробуйте позже.")


@bot.message_handler(commands=['change'])
def change_city(message):
    """Изменяет город для обновлений"""
    bot.send_message(message.chat.id, "Введите новый город для получения погоды:")
    bot.register_next_step_handler(message, process_city_input)


@bot.message_handler(commands=['language'])
def change_language(message):
    """Изменяет язык описания погоды"""
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True)
    markup.add('Русский', 'English')

    msg = bot.send_message(
        message.chat.id,
        "Выберите язык для описания погоды:",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, process_language_selection)


def process_language_selection(message):
    """Обрабатывает выбор языка пользователем"""
    lang_map = {'русский': 'ru', 'english': 'en'}
    selected = message.text.lower()

    if selected not in lang_map:
        bot.send_message(message.chat.id, "❌ Неверный выбор языка. Используйте кнопки.")
        return

    if message.chat.id not in users:
        users[message.chat.id] = {"city": "", "language": lang_map[selected]}
        bot.send_message(message.chat.id, "Теперь укажите город с помощью /start")
        return

    users[message.chat.id]["language"] = lang_map[selected]
    bot.send_message(
        message.chat.id,
        f"🌍 Язык изменен на {message.text}. Следующее обновление будет на выбранном языке.",
        reply_markup=telebot.types.ReplyKeyboardRemove()
    )


@bot.message_handler(func=lambda message: True)
def handle_unknown(message):
    """Обработчик неизвестных команд"""
    bot.send_message(
        message.chat.id,
        "❌ Неизвестная команда. Используйте /help для списка команд."
    )


def run_bot():
    """Запускает бота с обработкой исключений"""
    while True:
        try:
            logger.info("Starting bot polling...")
            bot.polling(none_stop=True)
        except Exception as e:
            logger.error(f"Bot crashed: {str(e)}")
            time.sleep(10)


if __name__ == '__main__':
    # Запускаем бота и планировщик в отдельных потоках
    threading.Thread(target=schedule_periodic_updates, daemon=True).start()
    threading.Thread(target=run_bot, daemon=True).start()

    # Основной поток просто ждет
    while True:
        time.sleep(1)
