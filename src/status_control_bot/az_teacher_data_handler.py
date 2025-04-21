import os
import json
import logging
import transliterate
from pathlib import Path
from src.status_control_bot.config import BASE_DIR, DIFF_SYMBOLS
from src.status_control_bot.utils import convert_to_latin, load_json, save_json


"""
Пример структуры используемого в TeacherDataHandler файла *.json:
{
    "data_path":"data/students",
    "teachers":{
        "Эйлер Л.": {
            "Кромин Денис Артёмьевич": {
                "file":"euler__kromin_artem.json",
                "work":"euler__kromin_artem/work.doc"
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
# TODO: удаление студента, на которого есть дублированный доступ у другого преподавателя

# Настройка логирования
logger = logging.getLogger(__name__)

# region Общие методы
def clean_text(text: str) -> str:
    """Превращает: '  Я   чист ' -> 'Я чист'"""
    return ' '.join(text.strip().split())


def match_two_strings(input_str: str, clean_str: str, max_diffs=1):
    """Поиск совпадений между двумя строковыми значениями с использвованием функции
     расстояния Левенштейна.

    Args:
        input_str: строковое значение.
        clean_str: "чистое" строковое значение с которым сравнивается input_str. 
        max_diffs: количество допустимо различающихся символов.

    Returns:
        bool: True, совпадение, иначе False.
    """

    def levenshtein_distance(s1, s2):
        # Функция расстояния Левенштейна
        if len(s1) < len(s2):
            return levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def compare_fullname(fio, query, max_differences):
        # Сперва сравниваем ФИО
        distance = levenshtein_distance(fio.lower(), query.lower())
        if distance <= max_differences:
            return True, fio

        # Сравнение каждой из трех частей полного ФИО.
        name_parts = fio.split()
        for part in name_parts:
            distance = levenshtein_distance(part.lower(), query.lower())
            if distance <= max_differences:
                return True, part
        return False, None

    flag, part = compare_fullname(
        fio=clean_text(clean_str),
        query=clean_text(input_str),
        max_differences=1
    )
    return flag

# endregion

# ----------------------------------------------------------------------------------------------------------------------
# region Инициализация
class TeacherDataHandler:
    """
    Обработка данных преподавателей, назначенных студентов, и управление 
    файловой структурой. Весь функционал на базе json.
    """

    def __init__(self, file_path=None):
        # инициализация
        self.data = dict()
        self.data_links = dict()
        self.current_file = None

        if file_path is None:
            return
        self.load_data(file_path)

    def load_data(self, file_path):
        self.data = self.load(file_path)
        if self.data is None:
            logging.info(f"Файл '{file_path}' не был загружен.")
            raise ValueError
        self.current_file = file_path

        # Формируем уникальные связи через int, поскольку telegram-bot не поддерживают слишком
        # длинные имена и не получится сделать их с помощью ключей-имён
        teachers = self.get_teachers()
        students_count = 0
        if len(teachers) > 0:
            self.data_links["students"] = {}
            self.data_links["links"] = {}  # id_s: [id_t, ... ]
            self.data_links["teachers"] = {}
            # self.data_links["teachers"] = {i: item for i, item in enumerate(teachers)}
            for i, item in enumerate(teachers):
                self.data_links["teachers"][i] = item  # преподаватели
                students = self.get_teacher_students(item)
                links = []
                for stud in students:
                    self.data_links["students"][students_count] = stud
                    links.append(students_count)
                    # print(stud)
                    students_count += 1
                self.data_links["links"][i] = links
        else:
            print("Input data is empty.")

    @staticmethod
    def load(file_path):
        """Загружает json с логированием ошибок."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # logger.info(f"Файл {file_path} успешно загружен.")
            return data
        except FileNotFoundError:
            logger.error(f"Файл {file_path} не найден.")
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга json в файле {file_path}: {e}")
        except Exception as e:
            logger.error(f"Неизвестная ошибка при загрузке {file_path}: {e}")
        return None
    
    # region Добавление

    def add_teacher(self, name_teacher):
        """Добавление преподавателя."""
        if name_teacher not in self.get_teachers():
            self.data["teachers"][name_teacher] = {}  # пустой, студентов еще нет
            self.write_and_update()
            return True
        else:
            return False

    def add_student(self, teacher_name: str, student_dict: str, save_and_reload:bool=True):
        """
        Добавление студента выбранному преподавателю. 
        Флаг save_and_reload для сохранения и перезагрузки класса.
        Ключи student_dict:
         ["name"] - имя студента
         ["group"] - группа студента
         ["work"] - работа студента
        """
        # Выполняем проверки
        if teacher_name not in self.get_teachers():
            print("Teacher is not registered. Cannot add student.")
            return False
        if student_dict["name"] in self.get_students_list():
            print("Student is already exist. Cannot add student.")
            return False

        # Cоздаем файл статусов
        file_name = self.create_file_for_student(student_dict["name"], teacher_name)
        if file_name is None:
            print("Can't create file for student. Cannot transfer.")
            return False

        # Заполняем структуру...
        self.data["teachers"][teacher_name] = {student_dict["name"]: {
            "file": file_name,
            "group": student_dict.get("group", ""),
            "work": student_dict.get("work", "")}}
        
        if save_and_reload:
            self.write_and_update()

    def create_file_for_student(self, student_name:str, teacher_name:str, data=None):
        """Создание файла для хранения статусов (свойств/параметров) студента."""
        filename = convert_to_latin(teacher_name) + "__" + convert_to_latin(student_name, use_initials=True) + ".json"
        if data is None:
            student_status = {key: "" for key in self.get_statuses().keys()}
        else:
            student_status = data
        file_path = f"{self.data['data_dir']}/{filename}"
        save_json(file_path, student_status)
        if Path(file_path).exists():
            return filename
        else:
            return None

    # region Извлечение
    def get_groups(self):
        return self.data["groups"]

    def get_data_links_relations(self):
        return self.data_links["links"]

    def get_data_link_students(self):
        return self.data_links["students"]

    def get_student_for_group(self, group_name, return_id=True):
        """Перечень id или имен студентов, которые принадлежат группе"""
        result = {}  # { id_s: name}
        for id_s, student_name in self.get_data_link_students().items():
            id_t = self.get_teacher_of_student(id_s)
            if id_t is None:
                continue

            teacher_name = self.get_teacher_by_id(id_t)
            if teacher_name is None:
                continue

            s_data = self.get_student_data_by_name(teacher_name, student_name)
            if s_data["group"] == group_name:
                result[id_s] = student_name

        if return_id:
            return list(result.keys())  # Возвращаем id
        else:
            return list(result.values())  # Возвращаем имена

    def get_teachers(self):
        """Перечень имен преподавателей"""
        return list(self.data["teachers"].keys())

    def get_teachers_id(self):
        """Перечень id преподавателей"""
        return list(self.data_links["teachers"].keys())

    def get_teacher_by_name(self, teacher_name):
        """id преподавателя через его имя"""
        for key, value in self.data_links["teachers"].items():
            if teacher_name == value:
                return key
        return None

    def get_teacher_by_id(self, id_t):
        """Имя преподавателя через id"""
        return self.data_links["teachers"].get(id_t, None)

    def get_teacher_students(self, teacher_name: str):
        """Перечень студентов преподавателя по имени"""
        return list(self.data["teachers"][teacher_name].keys())

    def get_teacher_students_by_id(self, id_t: int):
        """Перечень студентов преподавателя по id"""
        return list(self.data_links["links"].get(id_t, None))

    def get_teacher_of_student(self, id_s: int):
        """id учителя для выбранного id студента"""
        for id_t, ids_s in self.get_data_links_relations().items():
            if id_s in ids_s:
                return id_t
        return None

    def get_student_id_by_name(self, student_name: str):
        """id студента по его имени"""
        for key, value in self.data_links["students"].items():
            if student_name == value:
                return key
        return None

    def get_student_name_by_id(self, id_s: int):
        """Имя студента через id"""
        return self.data_links["students"].get(id_s, None)

    def get_student_data_by_id(self, id_t: int, id_s: int):
        """Данные по конкретному студенту преподавателя через id"""
        teacher_name = self.get_teacher_by_id(id_t)
        student_name = self.get_student_name_by_id(id_s)
        return self.get_student_data_by_name(teacher_name, student_name)

    def get_student_data_by_name(self, teacher_name, student_name):
        """Данные по конкретному студенту преподавателя """
        return self.data["teachers"][teacher_name].get(student_name, None)

    def get_student_file_data(self, teacher_name, student_name):
        # Данные по студенту
        data_s = self.get_student_data_by_name(teacher_name, student_name)
        # Путь к файлу студента
        file_path = Path(BASE_DIR / self.data["data_dir"]) / data_s["file"]
        data_f = self.load(file_path)
        return file_path, data_f

    def get_students_list(self) -> list[str]:
        return list(self.data_links["students"].values())

    def get_statuses(self):
        return self.data["statuses"]
    
    # region Изменение
    def change_student_status(self, teacher_name, student_name, status_key, user_input):
        """Установка нового значения для статуса студента"""
        data_s = self.get_student_data_by_name(teacher_name, student_name)
        if data_s is None:
            return False

        # Извлекаем путь к файлу
        file_path = Path(BASE_DIR / self.data["data_dir"]) / data_s["file"]
        data_f = self.load(file_path)
        if status_key not in self.get_statuses().keys():
            return False

        data_f[status_key] = user_input
        self.save_json(file_path, data_f)
        return True

    def transfer_student(self, student_name, to_teacher, from_teacher=None):
        """
        Перемещение студента выбранному преподавателю. При указанном значении 'from_teacher' 
        перемещение производится от выбранного учителя. Если это 'дублированный' студент, то 
        перемещение будет отменено.
        
        Args:
            student_name: имя студента, который будет перемещен.
            to_teacher: учитель, которому назначается студент.
            from_teacher=None: имя преподавателя, среди которых будет искаться студент для трансфера.

        Returns:
            bool: флаг успеха перемещения студента
        """
        if to_teacher not in self.get_teachers():
            print("Teacher is not registered. Cannot transfer.")
            return False
        if student_name not in self.get_students_list():
            print("Student is not registered. Cannot transfer.")

        # Проверяем аргумент "от учителя"
        if from_teacher is not None:
            if from_teacher not in self.get_teachers():
                print("Teacher is not registered. Cannot transfer.")
                return False
            # Проверяем, что студент в перечне учителя from_teacher
            teacher_of_stud_id = self.get_teacher_of_student(self.get_student_id_by_name(student_name))
            if teacher_of_stud_id != self.get_teacher_by_name(from_teacher):
                print(f"'{student_name}' is not a student of '{from_teacher}', check your query. Cannot transfer.")
                return False

        # Сперва создаем студента, а после его удаляем у преподавателя 'from_teacher'
        # Извлекаем данные 
        teacher_for_fix = None
        if from_teacher:
            for_teacher = self.get_student_data_by_name(from_teacher, student_name)
            teacher_for_fix = from_teacher
        else:
            the_teacher_id = self.get_teacher_of_student(self.get_student_id_by_name(student_name))
            teacher_for_fix = self.get_teacher_by_id(the_teacher_id)
            for_teacher = self.get_student_data_by_name(teacher_for_fix, student_name)
        
        if "duplicate" in for_teacher.keys():
            print(f"Student is 'duplicated'. Transfer canceled.")
            return False

        file_path, data = self.get_student_file_data(from_teacher, student_name)
        # Записываем новый файл с данными
        filename = self.create_file_for_student(student_name, to_teacher, data) 
        if filename is None:
            print(f"Error during write data. Transfer canceled.")
            return False
        
        # Формируем новую запись
        new_data = {key: value for key, value in for_teacher.items() if key != "file"}
        new_data["file"] = filename
        self.data["teachers"][to_teacher][student_name] = new_data
        
        # Теперь удаляем старые файлы и записи
        self.delete_file(file_path)
        self.data["teachers"][teacher_for_fix].pop(student_name)
        self.write_and_update()
        return True


    def duplicate_access(self, to_teacher: str, from_teacher: str, student: str):
        """
        Дублирование доступа к студенту другого уже существующего преподавателя. 

        Args:
            to_teacher: имя учителя для которого дублируется.
            from_teacher: имя учителя который "делится" студентом.
            student: имя студента доступ к которому дублируется.

        Returns:
            bool: флаг успеха дублирования доступа
        """
        teachers = self.get_teachers()
        if any(t not in teachers for t in [to_teacher, from_teacher]):
            print("Teacher(s) is not registered. Cannot duplicate access.")
            return False
        if student not in self.get_students_list():
            print("Student is not registered. Cannot duplicate access.")
            return False
        if student in self.get_teacher_students(to_teacher):
            print(f"Student is already linked to '{to_teacher}'. Duplicate access cancelled.")
            return False
        
        # Извлекаем существущие данные...
        data = {student: self.get_student_data_by_name(from_teacher, student)}
        # Добавляем метку, что это дубликат
        data[student]["duplicate"] = {from_teacher:student}
        self.data["teachers"][to_teacher].update(data)
        if self.get_student_data_by_name(to_teacher, student):
            self.write_and_update()
            return True
        else:
            return False

    
    # region Удаление
    
    def remove_teacher(self, name_teacher):
        if name_teacher in self.get_teachers():
            result = self.data["teachers"].pop(name_teacher)
            self.write_and_update()
            return result

    def remove_student_by_name(self, student_name: str, full_match:bool=False, teacher_name:str=None):
        """
        Удаление студента по заданному имени или части имени. 
        Ищет первые совпадение в ФИО, если не указан флаг full_match. 
        Можно указывать только часть ФИО: имя, фамилию, отчество. 
        Количество допустимых ошибок по умолчанию 1. Также удаляет файл *.json, 
        относящийся к студенту. Если в структуре данных присутствует ключ 
        "duplicate", то сам файл не удаляет, поскольку это дублированный доступ к 
        студенту другого преподавателя.

        Args:
            student_name: запрос - имя, либо часть для удаления.
            full_match: True, если требуется полное совпадение в имени, иначе False.
            teacher_name: (необязательно) удаление студента у конкретного преподавателя.

        Returns:
            dict: словарь удаленных значений по студенту
             {student_name: {teacher's data}, 'file': {file_path: {data}}}
        """
        db_students = self.get_students_list()

        # Поиск студента, без привязки к преподавателю
        if teacher_name is None:
            # Перечень студентов
            match_student = None

            for current_student in db_students:
                # Требуется полное, либо относительное совпадение
                if (full_match and current_student == student_name) or \
                        (not full_match and match_two_strings(student_name, current_student, DIFF_SYMBOLS)):
                    match_student = current_student
                    break

            # Совпадений не найдено
            if match_student is None:
                print("There is no match student. Cannot remove.")
                return None

            # Формируем набор данных имеющих связь с удаляемым значением
            id_s = self.get_student_id_by_name(match_student)
            id_t = self.get_teacher_of_student(id_s)
            if id_t is None:
                print("Cannot find teacher for student id. Cannot remove.")
                return None
            teacher_name = self.get_teacher_by_id(id_t)
        
        else:
            # Удаление конкретного студента у конкретного преподавателя
            # Проверки
            if student_name not in db_students:
                print("There is no input student. Cannot remove student.")
                return None
            else:
                match_student = student_name

            if teacher_name not in self.get_teachers():
                print("There is no input teacher. Cannot remove student.")
                return None
            
            if student_name not in self.get_teacher_students(teacher_name):
                print(f"Cannot find '{student_name}' in '{teacher_name}' students. Cannot remove.")
                return None

        # Особый случай - удаление дублированного доступа.        
        data = self.get_student_data_by_name(teacher_name, match_student)
        if "duplicate" in data.keys():
            print ("SPECIAL CASE!")
            removed_data = {match_student: self.data["teachers"][teacher_name].pop(match_student)}

        else:
            # Классический случай
            file_path, data = self.get_student_file_data(teacher_name, match_student)
            removed_data = {match_student: self.data["teachers"][teacher_name].pop(match_student)}
            removed_data["file"] = {file_path: data}

            # Физически удаляем файл студента
            self.delete_file(file_path)

        self.write_and_update()
        return removed_data

    def remove_student_by_id(self, id_s):
        """Удаление выбранного студента и перезапись данных"""
        student_name = self.get_student_name_by_id(id_s)
        if student_name:
            return self.remove_student_by_name(student_name)
        else:
            print("There is no student with input id. Cannot remove.")
            return

    def delete_statuses(self, status_key):
        """Удаление выбранного статуса и перезапись данных"""
        status = self.data["statuses"].get(status_key, None)
        if status:
            del self.data["statuses"][status_key]
            self.write_and_update()

    def delete_file(self, file_path):
        try:
            file_path.unlink()
        except FileNotFoundError:
            logging.info(f"Файл '{file_path}' не найден.")
        except PermissionError:
            logging.error(f"Недостаточно прав для удаления файла '{file_path}'.")
        except Exception as e:
            logging.error(f"Произошла ошибка: {e} при удалении файла '{file_path}'.")

    # region Запись
    def write_and_update(self):
        self.save_json(self.current_file, self.data)
        self.load_data(self.current_file)

    @staticmethod
    def save_json(json_path, data, mode='w'):
        """Сохранение данных (data) в файл json (json_path)"""
        try:
            with open(json_path, mode) as f:
                json.dump(data, f)
        except Exception as e:
            logging.error(f"Ошибка при сохранении данных в файл {json_path}: {e}")

    def dummy(self, call: str):
        dummy_t = "Заглушка-учитель А.Я."
        dummy_t2 = "Заглушка-учитель2 И.Я."
        dummy_s = {"name": "Заглушка-студент Аякс Яков", "group": "ЗАГЛУШКА-ГРУППА-000", "work": ""}
        match call:
            case "add_s":
                self.add_teacher(dummy_t)
                self.add_student(dummy_t, dummy_s)
                return f"Add dummy student {dummy_s['name']}"
            case "add_t":
                self.add_teacher(dummy_t)
                return f"Add dummy teacher {dummy_t}"
            case "del_t":
                self.remove_teacher(dummy_t)
                return f"Remove dummy teacher {dummy_t}"
            case "del_s":
                self.remove_student_by_name(dummy_s["name"], True)
                return f"Remove dummy student {dummy_s}"
            case "del_all":
                self.remove_teacher(dummy_t)
                self.remove_teacher(dummy_t2)
                self.remove_student_by_name(dummy_s["name"], True)
                return f"Try to remove all"
            case "move_s":
                self.add_teacher(dummy_t)
                self.add_teacher(dummy_t2)
                self.add_student(dummy_t, dummy_s)
                self.transfer_student(dummy_s["name"], dummy_t2, dummy_t)
                return f"Try to transfer student {dummy_s}"
            case "dub_acc":
                self.add_teacher(dummy_t)
                self.add_student(dummy_t, dummy_s)
                print("dummy_t_students:", self.get_teacher_students(dummy_t))
                self.add_teacher(dummy_t2)
                print("dummy_t2_students:", self.get_teacher_students(dummy_t2))
                self.duplicate_access(dummy_t2, dummy_t, dummy_s["name"])
                print("dummy_t2_students_after:", self.get_teacher_students(dummy_t2))
                return f"Try to duplicate access {dummy_s}"
            case "del_dub":
                self.add_teacher(dummy_t)
                self.add_student(dummy_t, dummy_s)
                print("dummy_t_students:", self.get_teacher_students(dummy_t))
                self.add_teacher(dummy_t2)
                print("dummy_t2_students:", self.get_teacher_students(dummy_t2))
                self.duplicate_access(dummy_t2, dummy_t, dummy_s["name"])
                print("dummy_t2_students_after:", self.get_teacher_students(dummy_t2))
                self.remove_student_by_name(dummy_s["name"], full_match=True, teacher_name=dummy_t2 )
                print("dummy_t_students:", self.get_teacher_students(dummy_t))
                print("dummy_t2_students:", self.get_teacher_students(dummy_t2))
                return f"Try to remove duplicate access for student {dummy_s}"


# ----------------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    full_info = True
    th = TeacherDataHandler(Path.joinpath(BASE_DIR, "data/students/teachers.json"))
    list_t = th.get_teachers()  # перечень преподавателей
    select_t = list_t[int('0')]
    students = th.get_teacher_students(select_t)  # перечень студентов преподавателя
    select_s = students[1]
    groups = th.get_groups()  # перечень групп
    data = th.get_statuses()  # перечень статусов
    if full_info:
        print(f"Teacher: {list_t}")
        print(f"Links: {th.data_links}")
        for item in list_t:
            print(f"Teacher: '{item}'\nlist_s: {th.get_teacher_students(item)}")
        for group in groups:
            print(f"В группе {group}: {len(th.get_student_for_group(group, False))}")
    print(f"data dir: {th.data['data_dir']}")
    exit()

    print(f"\nCurrent teacher: {select_t}")
    print(f"Students teacher: {students}")
    print(f"Selected student: {select_s}")
