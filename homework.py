import logging
import os
import sys
import time
from http import HTTPStatus

from dotenv import load_dotenv
import requests
import telegram

from exceptions import ListNone, StatusCodeError, HomeworkKeyError


load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


logger = logging.getLogger(__name__)


def check_tokens():
    """Проверяется доступность локальных переменных."""
    token_dict = {
        PRACTICUM_TOKEN: 'PRACTICUM_TOKEN',
        TELEGRAM_TOKEN: 'TELEGRAM_TOKEN',
        TELEGRAM_CHAT_ID: 'TELEGRAM_CHAT_ID'
    }
    for token in token_dict.keys():
        if not token:
            logger.critical('Отсусттвует переменная окружения'
                            f' {token_dict[token]}')
            return False
    logger.debug('Переменные окружения проверенны')
    return True


def send_message(bot, message):
    """Отправление сообщений в чат телеграма."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Отправлено сообщение.')
    except telegram.TelegramError as error:
        logger.error(f'Не удалось отправить сообщение. Ошибка: {error}')


def get_api_answer(timestamp):
    """Get запрос к API практикум.
    Приводит ответ к данным питон.
    """
    payload = {'from_date': timestamp}
    try:
        logger.debug('Запрос к API')
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except requests.RequestException as exception:
        logger.error(exception)
    if response.status_code != HTTPStatus.OK:
        raise StatusCodeError(f'Ошибка при запросе к {ENDPOINT}, '
                              f'статус {response.status_code}, '
                              f'параметры запроса timastamp={timestamp}, '
                              f'ответ сервера: {response.text}')
    logger.debug('Получен ответ от API')
    return response.json()


def check_response(response):
    """Проверяет полученный ответ от API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError('Полученные данные не являются словарем')
    elif not ('current_date' and 'homeworks' in response):
        raise KeyError('Отсутствуют ожидаемые ключи')
    elif not isinstance(response['homeworks'], list):
        raise TypeError('Данные homeworks не являются list')
    elif response['homeworks'] == []:
        raise ListNone('Отсутствует информация о домашнем задании')
    return response['homeworks']


def parse_status(homework):
    """Извлечение из домашней работы статуса ревью."""
    if 'homework_name' not in homework:
        raise HomeworkKeyError('В ответе API отсутствует ключ homework_name')
    homework_name = homework['homework_name']
    if homework['status'] == []:
        raise ListNone('Cтатус домашней работы пуст')
    if not homework['status'] in HOMEWORK_VERDICTS:
        raise KeyError('Ошибка: незадокументированный статус домашней работы')
    else:
        logger.debug('Полученные данные с API соответствуют документации')
        verdict = HOMEWORK_VERDICTS[homework['status']]
        return ('Изменился статус проверки работы'
                f' "{homework_name}". {verdict}')


def send_error_message(bot, old_mes, new_mes):
    """Регулирует и фильтрует отправку сообщений об ошибках в телеграм."""
    if old_mes != new_mes:
        send_message(bot, new_mes)
        return new_mes


def main():
    """Основная логика работы бота."""
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(stream=sys.stdout)
    formater = logging.Formatter(
        '%(asctime)s, %(levelname)s, %(funcName)s, %(message)s'
    )
    handler.setFormatter(formater)
    logger.addHandler(handler)
    if not check_tokens():
        logger.critical('Программа принудительно остановлена')
        sys.exit()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    message = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            check = check_response(response)
            timestamp = response['current_date']
            message = parse_status(check[0])
            send_message(bot, message)
        except StatusCodeError as error:
            logger.error(error)
            message = send_error_message(bot, message, str(error))
        except TypeError as type:
            logger.error(type)
            message = send_error_message(bot, message, str(type))
        except ListNone as list:
            logger.error(list)
            message = send_error_message(bot, message, str(list))
        except KeyError as key:
            logger.error(key)
            message = send_error_message(bot, message, str(key))
        except HomeworkKeyError as home_key:
            logger.error(home_key)
            message = send_error_message(bot, message, str(home_key))
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
