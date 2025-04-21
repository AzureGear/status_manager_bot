import re
import os
import json
import time
import transliterate  # pip install transliterate # конвертация из латиницы
from typing import Optional
from pathlib import Path
from functools import wraps
from collections import defaultdict
from src.status_control_bot.config import DATA_DIR


def write_info(file_path: str, text: str, mode: str = 'w', encoding='utf-8') -> bool:
    """Сохранение данных в формате txt.

    Args:
        file_path: путь сохранения.
        text: данные для записи.
        mode: тип записи, по умолчанию 'w'.

    Returns:
        bool: True, если запись успешна, иначе False.
    """
    try:
        with open(file_path, mode, encoding=encoding) as f:
            f.write(text)
        return True
    except Exception as e:
        print(f"Ошибка при записи файла: {e}")
        return False


def get_important_info(file_path) -> str:
    """Чтение данных c преобразованием в одну строку

    Args:
        file_path: путь к файлу.

    Returns:
        str: результирующая строка.
    """
    lines = read_file(file_path)
    lines = [line.strip() for line in lines]
    result = ''.join(lines)
    if len(result) > 0:
        return result
    else:
        return ""


# ----------------------------------------------------------------------------------------------------------------------
def timing_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        print(f"Функция {func.__name__} выполнилась за {end_time - start_time:.4f} секунд")
        return result
    return wrapper


def read_file(filename: str) -> list[str]:
    """Чтение файла и возврат списка строк."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if not lines:
                raise ValueError(f"Файл '{filename}' пустой.")
            return lines
    except FileNotFoundError:
        raise FileNotFoundError(f"Файл '{filename}' не найден.")


def load_json(file_path):
    """Загрузка данных типа json из файла (file_path)"""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            return data
    except json.JSONDecodeError:
        print(f"Файл {file_path} пустой, либо содержит некорректные данные.")
        return None


def save_json(json_path, data, mode='w'):
    """Сохранение данных (data) в файл json (json_path)"""
    with open(json_path, mode) as f:
        json.dump(data, f)


def get_teachers(filename: str) -> tuple[str, ...]:
    """Получение списка фамилий из файла и превращение их в кортеж."""
    lines = read_file(filename)
    return tuple(line.rstrip() for line in lines)


def make_dict(filename: str, use_short=False) -> dict:
    """Создание структурной связи из файла.
    """
    # Очистка
    lines = read_file(filename)
    lines = [line.strip() for line in lines]
    new_lines = []
    for line in lines:
        parts = line.split('\t')
        clean_row = ""
        for part in parts:
            part = part.rstrip()
            clean_row += part + "\t"
        clean_row = clean_row[:-1]
        new_lines.append(clean_row)

    result = {}
    for line in new_lines:
        parts = line.split('\t')

        # Вариант с сокращением Пушкин Александр Сергеевич -> Пушкин А.С.
        if use_short:
            key = short_name(parts[2])
        else:
            key = parts[2]

        # Ключ уже имеется, значит список следует расширить
        if key in result:
            the_list = result[key]
            the_list.append(parts[0])
            result[key] = the_list

        else:
            result[key] = [parts[0]]
    return result


def short_name(text: str) -> str:
    parts = text.split(" ")
    if len(parts) < 3:
        return text
    else:
        return parts[0] + " " + parts[1][0] + "." + parts[2][0] + "."


def convert_to_latin(name: str, use_initials: bool = False, one_word: bool = False) -> str:
    """Конвертируем фамилию и инициалы в латиницу. 

    Args:
        name: латинизируемое имя.
        use_initials: True, все имена после Фамилии сокращаются до инициалов
        one_word: True, если необходимо вернуть только одно слово

    Returns:
        str: результирующая строка.
    Например  'Ньютон Исаак' будет возвращен как 'nuton_isaak'"""

    parts = name.split()
    if len(parts) < 2:
        raise ValueError("Input data format must have minimum two names like 'Surname N.'")

    # Разделяем фамилию и остальные имена
    surname = parts[0]
    surname_en = transliterate.translit(surname, 'ru', reversed=True).lower().replace('.', '').replace("'", "")
    parts.pop(0)

    if one_word:  # Требуется только имя
        return surname_en

    en = []
    if use_initials:
        parts = [part[:1] for part in parts]

    for part in parts:
        # Важно! Если в имени точка или одиночная кавычка - удаляем её
        en.append(transliterate.translit(part, 'ru', reversed=True)
                  .lower()
                  .replace('.', '')
                  .replace("'", ""))

    # Добавляем инициалы, если требуется
    if use_initials:
        suffix = "_"
        suffix += "".join(en)
    else:
        suffix = "_".join(en)

    return surname_en + suffix


def find_group_for_student(data: str, student_name: str) -> Optional[str]:
    for line in data:
        line.strip()
        parts = line.split('\t')  # Разбиваем по табуляции

        # Проверяем имена на совпадение
        if compare_norm_names(student_name, parts[0]):
            return parts[1]
    return None


def compare_norm_names(name_one, name_another) -> bool:
    # Только буквы кириллицы и латиницы
    return re.sub(r'[^a-zA-Zа-яА-ЯёЁ]', '', name_one) == re.sub(r'[^a-zA-Zа-яА-ЯёЁ]', '', name_another)


def clean_text(text: str) -> str:
    """Превращает: '  Я   чист ' -> 'Я чист'"""
    return ' '.join(text.strip().split())


def find_bad_groups():
    # Поиск и удаление студе
    students = data.students_names
    full_data = read_file("teacher_complex.txt")
    students_with_group = dict()
    for i, student in enumerate(students):
        group = find_group_for_student(full_data, student)
        students_with_group[student] = group
        if group is None:
            print(f"WARNING: {i}. {student}:{group}")
    print(students_with_group)


def make_json_from_parsing(file_path: str, statuses_file: str):
    """
    Создание структуры используемого в TeacherDataHandler файлов *.json
    используя данные о студентах, преподавателях (txt, csv) и набор статусов (контролируемых параметров).
    """
    # Статусы должны быть 'чистыми'
    statuses = read_file(statuses_file)
    statuses_dict = {k: v for line in statuses for k, v in (line.strip().split("\t"),)}
    statuses_dummy = dict.fromkeys(statuses_dict.keys(), "")

    Path.mkdir(Path.joinpath(DATA_DIR, "students"), exist_ok=True)

    # Читаем данные студентов/подчиненных
    lines = read_file(file_path)

    # Создаем словарь с расширенными возможностями Collection
    teachers = defaultdict(lambda: defaultdict(dict))
    groups = set()

    # Разбираем данные
    for line in lines:
        # Разбиваем строку и сразу чистим
        student_name, group, teacher_name = map(str.strip, line.split("\t"))

        filename = create_student_filedata(teacher_name, student_name, statuses_dummy)
        if filename is None:
            print(f"Error during processing student {student_name}.")
            # raise ValueError
            continue

        teachers[teacher_name][student_name] = {
            "file": filename,
            "work": "",
            "group": group
        }

        groups.add(group)

    # Преобразуем defaultdict обратно в обычный dict для вывода
    teachers = {k: dict(v) for k, v in teachers.items()}

    final = {}
    final["data_dir"] = "data/students"
    final["teachers"] = teachers
    final["statuses"] = statuses_dict
    final["groups"] = list(groups)
    save_json("data/students/teachers.json", final)


def create_student_filedata(teacher_name: str, student_name: str, statuses: dict) -> str:
    """Создание файла данных для студента

    Args:
        teacher_name (str): имя преподавателя.
        student_name (str): имя студента.
        statuses (dict): перечень статусов.

    Returns:
        filename: при успешной записи данных json, возвращает относительное имя файла иначе None
    """

    t_name = convert_to_latin(clean_text(teacher_name), one_word=True)  # Транслитация имени преподавателя
    s_name = convert_to_latin(clean_text(student_name), use_initials=True)  # Транслитация имени студента
    filename = t_name + "__" + s_name + ".json"
    file_path = Path.joinpath(DATA_DIR, "students", filename)
    save_json(file_path, statuses)
    if Path.exists(file_path):
        return filename
    else:
        return None


def make_jsons_from_data():
    """
    Пример структуры используемого в TeacherDataHandler файла *.json:
    {
        "data_path":"data/students",
        "teachers":{
            "Эйлер Л.": {
                "Кромин Денис Артёмьевич": {
                    "file":"euler__kromin_artem.json",
                    "work":"euler__kromin_artem/work.pdf"
                    "group": "ПГС-701"
                },
                "Чаплин Чарльз Спенсер": {...},
            }
        },
        "statuses":{
            "ready_0105": "Готовность ВКР на 01.05.2025",
            "ready_1505": "Готовность ВКР на 15.05.2025",
            "check_plag": "Отметка о допуске ВКР к проверке на плагиат",
            "check_norma": "Отметка о допуске ВКР к нормоконтролю",
            "plag_date": "Дата прохождения проверки на плагиат",
            "norma_date": "Дата прохождения нормоконтроля",
            "final_date": "Дата сдачи ВКР в ЭБС",
        }
        "groups":[
            "ВГ-814-З", 
            "ПС-007", 
            "ВГ-915-З", 
            "ПС-009", 
            "ПС-010", 
            "ПС-910", 
            "ВП-916-З"
        ]
    }
    """
    final = dict()
    teachers = dict()

    # Статусы
    statuses = data.status

    # Текстовые данные
    full_data = read_file(Path.joinpath(DATA_DIR, "parsing", "teacher_complex.txt"))

    # Создаем каталоги
    Path.mkdir(Path.joinpath(DATA_DIR, "students"), exist_ok=True)

    # Имена преподавателей
    teacher_names = data.teachers_complex_short.keys()
    for name in teacher_names:
        the_teacher = dict()
        t_name = convert_to_latin(name)  # Транслитация имени преподавателя
        students = data.teachers_complex_short[name]  # Перечень студентов

        for student in students:
            clean_name = clean_text(student)
            the_student = dict()
            s_name = convert_to_latin(clean_name, use_initials=True)  # Транслитация имени студента
            filename = t_name + "__" + s_name + ".json"
            s_data = {key: "" for key in statuses}
            save_json(Path.joinpath(DATA_DIR, "students", filename), s_data)
            the_student["file"] = filename
            the_student["work"] = ""
            the_student["group"] = find_group_for_student(full_data, clean_name)
            the_teacher[clean_name] = the_student
        teachers[name] = the_teacher

    # Каталог где расположены данные
    final["data_dir"] = "data/students"
    final["teachers"] = teachers
    final["statuses"] = statuses
    final["groups"] = data.groups
    save_json(Path.joinpath(DATA_DIR, "students/teachers.json"), final)


if __name__ == "__main__":
    make_json_from_parsing(Path.joinpath(DATA_DIR, "parsing", "raw_data.txt"),
                           Path.joinpath(DATA_DIR, "parsing", "raw_statuses.txt"))
    data = load_json(os.path.join(DATA_DIR, "students", "teachers.json"))
    print(data)
    # c_teachers = make_dict("teacher_complex.txt", use_short=True)
    # uniq = set([val for val in my_dict.values()])
