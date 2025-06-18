import requests
import schedule
import time
import telebot
import threading
from googletrans import Translator

BOT_TOKEN = "BOT_TOKEN"
WEATHER_API_KEY = "API"

bot = telebot.TeleBot(BOT_TOKEN)

users = {}
UPDATE_INTERVAL_HOURS = 1  # Интервал обновлений в часах

def get_weather(city):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
    response = requests.get(url)
    data = response.json()
    if data.get("cod") == 200:
        temperature = data["main"]["temp"]
        description = data["weather"][0]["description"]
        translator = Translator()
        translated_description = translator.translate(description, src='en', dest='ru').text
        return f"Погода в городе {city}: {temperature}°C, {translated_description}"
    else:
        return "Не удалось получить погоду."

def send_weather_update(chat_id, city):
    weather = get_weather(city)
    bot.send_message(chat_id, weather)

def send_updates_to_all_users():
    for chat_id, user_info in users.items():
        send_weather_update(chat_id, user_info["city"])

def schedule_hourly_updates():
    schedule.every(UPDATE_INTERVAL_HOURS).hours.do(send_updates_to_all_users)
    while True:
        schedule.run_pending()
        time.sleep(1)

@bot.message_handler(commands=['start'])
def start(message):
    commands_message = (
        "Привет! Я могу присылать тебе погоду. Вот доступные команды:\n"
        "/start - начать получать обновления погоды.\n"
        "/stop - остановить обновления погоды."
    )
    bot.send_message(message.chat.id, commands_message)
    bot.send_message(message.chat.id, "В каком городе ты находишься?")
    bot.register_next_step_handler(message, get_city)

def get_city(message):
    city = message.text.strip()
    bot.send_message(message.chat.id, f"Отлично! Теперь я буду присылать погоду для города {city} каждый час.")
    users[message.chat.id] = {"city": city}

@bot.message_handler(commands=['stop'])
def stop(message):
    if message.chat.id in users:
        del users[message.chat.id]
        bot.send_message(message.chat.id, "Вы отменили подписку на обновления погоды.")
    else:
        bot.send_message(message.chat.id, "Вы не подписаны на обновления.")

if __name__ == '__main__':
    threading.Thread(target=schedule_hourly_updates).start()  # Запуск планировщика в отдельном потоке
    bot.polling(none_stop=True)
