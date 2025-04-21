import logging
from pathlib import Path
from datetime import datetime
from warnings import filterwarnings
from src.status_control_bot.az_teacher_data_handler import TeacherDataHandler
from src.status_control_bot.utils import get_important_info, write_info
from src.status_control_bot.rate_limiter import RateLimiter
from src.status_control_bot.config import BASE_DIR, DATA_DIR, API_BOT_TOKEN
from src.status_control_bot.ui_text import ui_data as UI_TEXT
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, CallbackQuery
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, \
    CallbackQueryHandler, ConversationHandler
from logging.handlers import RotatingFileHandler
from telegram.warnings import PTBUserWarning


"""
Структура меню.
1. Выбор преподавателя.
    1.1 <TCR_Name1>
        1.1 Просмотр моих студентов. 
        1.2 Выбор студента.
            1.2.1 <SDT_Name1>
                1.2.1.1 Изменить статус 1
                1.2.1.N ...
                1.2.1.N+1 Назад
            1.2.N ...
            1.2.N+1 Назад
    1.N ...
    1.N+1 Назад.
2. Просмотр всех студентов. (B1)
    2.1 Просмотр группы.
        2.1.1 Группа Х
        2.1.2 ...
        2.1.N Назад
    2.2 Просмотр всех (формат csv).
    2.3 Назад
3. Закончить.
</Команды>:
    1 /start
        1.1 /stop Остановка на любом этапе
        1.2 /message Ввод важного сообщения, которое будет показываться всем при начале работы (из главного меню)
"""

# TODO: добавить высчитывание статуса группы
# TODO: добавить фукнцию просмотра работы студента и записи работы студента.
# TODO: поправить лог перед выпуском


# region Инициализация
# Файл с важной информацией для отображения
INFO_FILE = Path.joinpath(DATA_DIR, "important_info.txt")
REG_FILE = Path.joinpath(DATA_DIR, "registration_data.txt")


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            "teacher_bot.log",
            maxBytes=5 * 1024 * 1024,  # максимальный размер 5 Мб
            backupCount=3,  # количество логбэков 3
            encoding="utf-8"
        )
    ]
)


# Отключаем шумные логи httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Отключим логирование и предупреждение о CallbackQueryHandler
filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)

# Состояния, этапы
# Начальный уровень
(
    DUMMY,
    STOPPING,
    SELECTING_ACTION,
    SELECT_TEACHER,
    VIEW_ALL,
    START_OVER,
    AWAIT_IMP_MSG,
    REGISTRATION,
) = map(chr, range(8))

# Меню преподавателя - c возможностью редактирования
(
    TEACHER,
    STUDENT,
    STATUS,
    TEACHER_IS_SET,
    TEACHERS_STUDENTS,
    TEACHERS_STUDENT_SELECT,
    TEACHERS_STUDENT_IS_SET,
    TEACHERS_STUDENT_CHANGE_STATUS,
) = map(chr, range(10, 18))

# Просмотр студентов
(
    VIEW_LIST_STUDENTS,
    VIEW_BY_GROUP,
) = map(chr, range(20, 22))

# Завершение обработчика
END = ConversationHandler.END

# Класс-обработчик данных преподавателей
tcr_handler = TeacherDataHandler(Path.joinpath(BASE_DIR, "data/students/teachers.json"))

# endregion


# region Обработчики
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Все необработанные исключения."""
    logger.error("Необработанная ошибка:", exc_info=context.error)
    
    # Отправка сообщения пользователю
    if update and update.effective_message:
        text = "Произошла ошибка. Попробуйте перезапустить чат /stop -> /start."
        await update.effective_message.reply_text(text)


async def imp_msg_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ввод важного сообщения"""
    await update.message.reply_text("Введите общую важную ❗ информацию для всех:")
    # Меняем состояние
    return AWAIT_IMP_MSG


async def imp_msg_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Получение и обработка важного сообщения"""
    user_input = update.message.text.strip()  # Получаем текст от пользователя
    success = write_info(INFO_FILE, user_input)  # Пробуем записать сообщение
    text = f"✅ Сообщение обновлено на:\n{user_input}" if success else "❌ Ошибка записи."

    # Отправляем результат
    await update.message.reply_text(text)
    return SELECTING_ACTION


async def reg_in(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Запись в файл регистрационных данных."""
    query = update.callback_query
    user = query.from_user

    if user:
        current_time = datetime.now().strftime("%Y.%m.%d, %H:%M")
        user_data = (f"{current_time}, {user.id}, {user.first_name or ''}, {user.last_name or ''}\n")

        # Добавляем строку в файл
        write_info(REG_FILE, user_data, mode='a')
        text = "Запрос на регистрацию принят."
    else:
        text = "Во время вашей регистрации возникла ошибка. Свяжитесь с Саидовой А.В."

    buttons = [[InlineKeyboardButton(text="ОК", callback_data=str(END))]]
    keyboard = InlineKeyboardMarkup(buttons)

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)

    return REGISTRATION


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Выбрать действие начального уровня ."""
    text = (UI_TEXT["start"])

    buttons = [
        [InlineKeyboardButton(text="Регистрация", callback_data=str(REGISTRATION))],
        [InlineKeyboardButton(text="Выбор преподавателя", callback_data=str(SELECT_TEACHER))],
        [InlineKeyboardButton(text="Просмотр всех студентов", callback_data=str(VIEW_ALL))],
        [InlineKeyboardButton(text="Завершить", callback_data=str(END))],
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    # Если начинаем заново, то нет необходимости отправлять первое сообщение
    if context.user_data.get(START_OVER):
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)
    else:
        await update.message.reply_text(
            f"{get_important_info(INFO_FILE)}"
        )
        await update.message.reply_text(text=text, reply_markup=keyboard)
    context.user_data[START_OVER] = False
    return SELECTING_ACTION


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Завершение чата через команду."""
    await update.message.reply_text("Работа прекращена.")
    return END


async def end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Завершение чата через GUI InlineKeyboardButton."""
    await update.callback_query.answer()
    text = "Вы завершили работу."
    await update.callback_query.edit_message_text(text=text)
    return END


async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Возврат к начальному уровню."""
    if context.user_data:
        context.user_data.clear()
    context.user_data[START_OVER] = True
    await start(update, context)
    return END


async def stop_nested(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Завершение чата из любого статуса."""
    await update.message.reply_text("Работа остановлена.")
    if context.user_data:
        context.user_data.clear()

    return STOPPING
# endregion

# region Преподаватель
# Выбор преподавателя


async def select_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Выбор конкретного преподавателя."""
    # Создаем кнопки с именами преподавателей в две колонки
    teacher_buttons = []
    teachers_id = tcr_handler.get_teachers_id()  # идентификаторы учителей
    teachers_pb = [InlineKeyboardButton(tcr_handler.get_teacher_by_id(
        item), callback_data=f"teacher_{item}") for item in teachers_id]
    # Перегруппируем кнопки попарно
    for i in range(0, len(teachers_pb), 2):
        # Если есть пара, добавляем пару кнопок
        if i + 1 < len(teachers_pb):
            teacher_buttons.append([teachers_pb[i], teachers_pb[i + 1]])
        else:
            # Если нет пары, добавляем одну кнопку
            teacher_buttons.append([teachers_pb[i]])

    teacher_buttons.append([InlineKeyboardButton(text="Назад", callback_data=str(END))])
    keyboard = InlineKeyboardMarkup(teacher_buttons)
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text="Выберите преподавателя:", reply_markup=keyboard)

    return SELECT_TEACHER


def create_teacher_menu(context, add_text=None, with_view_student=False) -> tuple[str, InlineKeyboardMarkup]:
    # Получаем обязательные данные из контекста
    id_t = context.user_data[TEACHER]
    if id_t is None:
        error_text = "Ошибка: отсутствуют данные преподавателя"
        return error_text, InlineKeyboardMarkup([[InlineKeyboardButton(text="Назад", callback_data=str(END))]])

    # Создаем клавиатуру
    buttons = []
    buttons.append([InlineKeyboardButton("Выбор и редактирование студента", callback_data=str(TEACHERS_STUDENT_SELECT))])
    if with_view_student:
        buttons.append([InlineKeyboardButton("Просмотр моих студентов", callback_data=str(TEACHERS_STUDENTS))])
    buttons.append([InlineKeyboardButton("Назад", callback_data=str(END))])

    # Формируем текст
    teacher_name = tcr_handler.get_teacher_by_id(id_t)
    text = f"Преподаватель: {teacher_name}\n"
    if add_text:
        text += add_text

    return text, InlineKeyboardMarkup(buttons)


async def teacher_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Меню преподавателя, после выбора конретного учителя."""
    query = update.callback_query
    # Нажали на кнопку с выбором преподавателя
    if query.data.startswith("teacher_"):
        # Определяем кнопку, на которую нажали
        id_t = int(query.data.replace("teacher_", ""))  # конвертируем в int
        context.user_data[TEACHER] = id_t  # Сохраняем id преподавателя в user_data

    else:  # Нажали на кнопку назад из следующего меню
        id_t = context.user_data[TEACHER]
        if id_t is None:
            await query.edit_message_text("Ошибка: преподаватель не выбран.")
            return STOPPING

    text, keyboard = create_teacher_menu(context, add_text="Выберите действие:", with_view_student=True)
    await query.answer()
    await query.edit_message_text(text=text, reply_markup=keyboard)

    return TEACHER_IS_SET


async def select_teach_std(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Выбор студента преподавателя."""
    id_t = context.user_data[TEACHER]
    teacher_name = tcr_handler.get_teacher_by_id(id_t)  # имя учителя
    ids_s = tcr_handler.get_teacher_students_by_id(id_t)  # ids студентов

    # Создаем кнопки с именами студентов
    buttons = [[InlineKeyboardButton(tcr_handler.get_student_name_by_id(
        id_s), callback_data=f"student_{id_s}")] for id_s in ids_s]

    # Добавляем кнопку "Назад"
    buttons.append([InlineKeyboardButton(text="Назад", callback_data=str(TEACHER_IS_SET))])
    keyboard = InlineKeyboardMarkup(buttons)

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        text=f"Преподаватель: {teacher_name}\nВыберите студента:",
        reply_markup=keyboard
    )

    return TEACHERS_STUDENT_SELECT


async def view_teach_std(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Просмотр студентов преподавателя."""
    query = update.callback_query
    await query.answer()

    id_t = context.user_data[TEACHER]
    # Проверка
    if id_t is None:
        await query.edit_message_text("Ошибка: преподаватель не выбран.")
        return STOPPING
    ids_s = tcr_handler.get_teacher_students_by_id(id_t)

    students_list = "\n".join(
        f"• {tcr_handler.get_student_name_by_id(id_s)}" for id_s in ids_s) if ids_s else "У вас нет студентов😎"
    add_info = f"Мои студенты:\n{students_list}\nВыберите действие:"

    text, keyboard = create_teacher_menu(context, add_text=add_info)
    await query.edit_message_text(text=text, reply_markup=keyboard)
    return TEACHER_IS_SET


async def student_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    query = update.callback_query
    await query.answer()

    # Обрабатываем только если нажата кнопка выбора студента
    if query.data.startswith("student_"):
        student_id = int(query.data.replace("student_", ""))
        context.user_data[STUDENT] = student_id
    else:
        # Нажата "назад" либо после редактирования
        if context.user_data[STUDENT] is None:
            await query.edit_message_text("Ошибка: студент не найден")
            return STOPPING

    # Генерируем меню используя context
    text, keyboard = create_student_menu(context)

    try:
        await query.edit_message_text(
            text=text,
            reply_markup=keyboard
        )
    except Exception as e:
        logging.error(f"Ошибка обновления сообщения: {e}")
        await query.message.reply_text("Ошибка: обновления интерфейса")
        return STOPPING

    return TEACHERS_STUDENT_IS_SET
# endregion


async def student_status_change(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Изменения выбранного статуса."""
    query = update.callback_query
    await query.answer()

    # Проверяем наличие базовых данных
    if context.user_data[STUDENT] is None:
        await query.edit_message_text("Ошибка: студент не найден")
        return STOPPING

    # Сохраняем message_id перед любыми действиями
    context.user_data['last_message_id'] = query.message.message_id

    # Извлекаем выбранный статус
    status_key = query.data.replace("status_", "")
    context.user_data[STATUS] = status_key

    # Смотрим какое у него название
    headers = tcr_handler.get_statuses()
    status_name = headers.get(status_key, None)
    if status_name is None:
        await query.edit_message_text("Ошибка: статус не найден.")
        return STOPPING

    await query.edit_message_text(
        text=f"Введите новое значение для параметра '{status_name[0].lower() + status_name[1:]}':\nИли отправьте '/no' для отмены."
    )
    return TEACHERS_STUDENT_CHANGE_STATUS


async def input_status_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    # Ввод пользователя
    user_input = update.message.text.strip()

    # ID предыдущего сообщения для редактирования
    chat_id = update.effective_chat.id
    message_id = context.user_data.get('last_message_id')

    # Извлекаем данные
    teacher_id = context.user_data[TEACHER]
    student_id = context.user_data[STUDENT]
    status_key = context.user_data[STATUS]

    # Проверка данных
    if None in [teacher_id, student_id, status_key]:
        await update.message.reply_text("Ошибка: потерян контекст сессии")
        return STOPPING

    teacher_name = tcr_handler.get_teacher_by_id(teacher_id)
    student_name = tcr_handler.get_student_name_by_id(student_id)

    # Отмена
    if user_input.lower() == '/no':
        status_message = "❌ Изменение отменено"
    else:
        # Изменение данных
        success = tcr_handler.change_student_status(teacher_name, student_name, status_key, user_input)
        status_message = "✅ Статус обновлен" if success else "❌ Ошибка обновления"

    # Удаляем сообщение с вводом пользователя для очистки чата
    try:
        await context.bot.delete_message(chat_id, update.message.message_id)
    except Exception as e:
        logging.error(f"Ошибка удаления сообщения: {e}")

    # Заново создаем меню "Выбора студента"
    text, keyboard = create_student_menu(context)
    full_text = f"{status_message}\n{text}"

    # Редактируем исходное сообщение с новым меню
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=full_text,
        reply_markup=keyboard
    )

    # Удаляем статус из Context
    context.user_data[STATUS] = None

    # Возвращаем состояние TCR_SDT_IS_SET
    return TEACHERS_STUDENT_IS_SET


def create_student_menu(context) -> tuple[str, InlineKeyboardMarkup]:
    # Получаем обязательные данные из контекста
    teacher_id = context.user_data[TEACHER]
    student_id = context.user_data[STUDENT]

    # Проверка данных
    if any(val is None for val in [teacher_id, student_id]):
        error_text = "Ошибка: отсутствуют данные преподавателя или студента"
        return error_text, InlineKeyboardMarkup([[InlineKeyboardButton(text="Назад", callback_data=str(TEACHERS_STUDENT_SELECT))]])

    # Извлекаем данные
    teacher_name = tcr_handler.get_teacher_by_id(teacher_id)
    student_name = tcr_handler.get_student_name_by_id(student_id)
    _, data_s = tcr_handler.get_student_file_data(teacher_name, student_name)

    if any(val is None for val in [teacher_name, student_name, data_s]):
        error_text = "Ошибка получения данных"
        return error_text, InlineKeyboardMarkup([[InlineKeyboardButton(text="Назад", callback_data=str(TEACHERS_STUDENT_SELECT))]])

    # Формируем текст сообщения
    text = (
        f"Преподаватель: {teacher_name}\n"
        f"Выбранный студент: {student_name}\n"
        "---\n"
    )

    # Добавляем статусы
    headers = tcr_handler.get_statuses()
    buttons = []
    for key, value in data_s.items():
        if key in headers:
            h_key = headers[key]
            text += f"{h_key}: {value}\n"
            buttons.append([
                InlineKeyboardButton(
                    f"✍ {h_key[0].lower() + h_key[1:]}",
                    callback_data=f"status_{key}"
                )
            ])

    # Добавляем кнопку "Назад"
    text += "---\nВыберите параметр для изменения:"
    buttons.append([InlineKeyboardButton("Назад", callback_data=str(TEACHERS_STUDENT_SELECT))])

    return text, InlineKeyboardMarkup(buttons)


# ----------------------------------------------------------------------------------------------------------------------
# region Просмотр всех
async def view_students(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Просмотр студентов (диалог 'B')"""
    text = "Просмотр студентов. "
    buttons = [
        [InlineKeyboardButton(text="Просмотр всех", callback_data=str(VIEW_LIST_STUDENTS))],
        [InlineKeyboardButton(text="Просмотр по группам", callback_data=str(VIEW_BY_GROUP))],
        [InlineKeyboardButton(text="Назад", callback_data=str(END))],
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)

    return VIEW_ALL


async def list_all_students(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Просмотр всех студентов (диалог 'B')"""
    query = update.callback_query
    await query.answer("Заглушка", show_alert=True)

    return VIEW_LIST_STUDENTS


async def list_by_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Просмотр студентов по группам (диалог 'B')"""
    query = update.callback_query
    await query.answer("Заглушка", show_alert=True)

    return VIEW_BY_GROUP


async def select_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Выбор конкретного преподавателя."""
    # Создаем кнопки с именами преподавателей в две колонки
    teacher_buttons = []
    teachers_id = tcr_handler.get_teachers_id()  # идентификаторы учителей
    teachers_pb = [InlineKeyboardButton(tcr_handler.get_teacher_by_id(
        item), callback_data=f"teacher_{item}") for item in teachers_id]
    # Перегруппируем кнопки попарно
    for i in range(0, len(teachers_pb), 2):
        if i + 1 < len(teachers_pb):
            # Если есть пара, добавляем пару кнопок
            teacher_buttons.append([teachers_pb[i], teachers_pb[i + 1]])
        else:
            # Если нет пары, добавляем одну кнопку
            teacher_buttons.append([teachers_pb[i]])

    teacher_buttons.append([InlineKeyboardButton(text="Назад", callback_data=str(END))])
    keyboard = InlineKeyboardMarkup(teacher_buttons)
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text="Выберите преподавателя:", reply_markup=keyboard)

    return SELECT_TEACHER


# ----------------------------------------------------------------------------------------------------------------------
# region Main()
def create_bot_app() -> Application:
    """Создание приложения бота"""
    app = Application.builder().token(API_BOT_TOKEN).build()
    
    # Регистрация обработчиков
    # Регистрация
    registration_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(reg_in, pattern=f"^{str(REGISTRATION)}$")],
        states={
            REGISTRATION: [
                CallbackQueryHandler(back_to_start, pattern=f"^{str(END)}$"),
            ]
        },
        fallbacks=[
            CallbackQueryHandler(back_to_start, pattern=f"^{str(END)}$"),
            CommandHandler("stop", stop_nested),
        ],
        map_to_parent={
            # Вернуться в начальное меню
            END: SELECTING_ACTION,
            # Завершить чат
            STOPPING: END,
        }
    )

    # Просмотр студентов
    view_all_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(view_students, pattern=f"^{str(VIEW_ALL)}$")],
        states={
            VIEW_ALL: [
                CallbackQueryHandler(list_all_students, pattern=f"^{str(VIEW_LIST_STUDENTS)}$"),
                CallbackQueryHandler(list_by_group, pattern=f"^{str(VIEW_BY_GROUP)}$"),
                CallbackQueryHandler(back_to_start, pattern=f"^{str(END)}$"),
            ]
        },
        fallbacks=[
            CallbackQueryHandler(back_to_start, pattern=f"^{str(END)}$"),
            CommandHandler("stop", stop_nested),
        ],
        map_to_parent={
            # Вернуться в начальное меню
            END: SELECTING_ACTION,
            # Завершить чат
            STOPPING: END,
        },
    )

    # Выбор учителя и последующие действия
    select_teacher_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(select_teacher, pattern=f"^{str(SELECT_TEACHER)}$")],
        states={
            SELECT_TEACHER: [
                CallbackQueryHandler(teacher_selected, pattern="^teacher_.+$"),
                CallbackQueryHandler(back_to_start, pattern=f"^{str(END)}$"),
            ],
            TEACHER_IS_SET: [
                CallbackQueryHandler(view_teach_std, pattern=f"^{str(TEACHERS_STUDENTS)}$"),
                CallbackQueryHandler(select_teach_std, pattern=f"^{str(TEACHERS_STUDENT_SELECT)}$"),
                CallbackQueryHandler(back_to_start,  pattern=f"^{str(END)}$"),
            ],
            TEACHERS_STUDENT_SELECT: [
                CallbackQueryHandler(student_selected, pattern="^student_.+$"),
                CallbackQueryHandler(teacher_selected, pattern=f"^{str(TEACHER_IS_SET)}$")
            ],
            TEACHERS_STUDENT_IS_SET: [
                CallbackQueryHandler(student_status_change, pattern="^status_.+$"),
                CallbackQueryHandler(select_teach_std, pattern=f"^{str(TEACHERS_STUDENT_SELECT)}$"),
            ],
            TEACHERS_STUDENT_CHANGE_STATUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, input_status_value),
                CommandHandler("no", input_status_value),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(back_to_start, pattern=f"^{str(END)}$"),
            CommandHandler("stop", stop_nested),
        ],
        map_to_parent={
            # Вернуться в начальное меню
            END: SELECTING_ACTION,
            # Завершить чат
            STOPPING: END,
        },
    )

    # Первый уровень (selecting action)
    selection_handlers = [
        registration_conv,
        select_teacher_conv,
        view_all_conv,  # todo
        CallbackQueryHandler(end, pattern=f"^{str(END)}$"),
    ]
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_ACTION: selection_handlers,  # type: ignore[dict-item]
            STOPPING: [CommandHandler("start", start)],
            AWAIT_IMP_MSG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, imp_msg_input),
            ]

        },
        fallbacks=[
            CommandHandler("stop", stop),
            CommandHandler("message", imp_msg_start),
        ],
    )
    
    app.add_handler(conv_handler)

    # Добавляем глобальный обработчик ошибок для контроля всех необработанных исключений
    app.add_error_handler(error_handler)
    
    # Обработчик ошибок
    app.add_error_handler(error_handler)
    
    return app

def run_bot():
    """Запуск бота"""
    app = create_bot_app()
    print("Запуск бота")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    run_bot()
# endregion


if __name__ == '__main__':
    main()
