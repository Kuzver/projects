import logging
import sys
from datetime import datetime

# Настройка логирования
if getattr(sys, 'frozen', False):
    logging.basicConfig(
        filename='pharmacy_app.log',
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
else:
    logging.basicConfig(level=logging.DEBUG)


def excepthook(exc_type, exc_value, exc_traceback):
    """Глобальный обработчик исключений"""
    logging.critical("Необработанное исключение:", exc_info=(exc_type, exc_value, exc_traceback))

    # Сохраняем в файл
    with open('error.log', 'w') as f:
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)

    QMessageBox.critical(None, "Критическая ошибка",
                         f"Произошла критическая ошибка. Проверьте файл error.log\n{exc_value}")


sys.excepthook = excepthook
import os
import psycopg2
import requests

if getattr(sys, 'frozen', False):
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')

from PyQt6 import uic
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout,
    QLabel, QPushButton, QTableWidgetItem, QLineEdit,
    QComboBox, QHBoxLayout, QMessageBox,
    QSpinBox, QDateEdit, QTableView, QHeaderView, QDialogButtonBox, QInputDialog, QMainWindow, QTextEdit
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QDate
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QFont
from contextlib import contextmanager
import traceback

# ------------------ Менеджер звуков ------------------ #
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtCore import QUrl, QObject, QTimer
import os
import faulthandler

faulthandler.enable()


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def load_ui_from_resource(ui_filename):
    """Загрузка UI из ресурсов"""
    if getattr(sys, 'frozen', False):
        # В собранном приложении
        base_path = sys._MEIPASS
        file_path = os.path.join(base_path, ui_filename)

        if os.path.exists(file_path):
            return file_path

    return ui_filename


class SoundManager(QObject):
    def __init__(self):
        super().__init__()
        self.sounds = {}

    def load_sound(self, name, path):
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            print(f"[SoundManager] Файл не найден: {abs_path}")
            return

        sound = QSoundEffect()
        sound.setSource(QUrl.fromLocalFile(abs_path))
        sound.setVolume(1.0)
        self.sounds[name] = sound
        print(f"[SoundManager] Звук '{name}' загружен")

    def play(self, name):
        sound = self.sounds.get(name)
        if not sound:
            print(f"[SoundManager] Звук '{name}' не найден")
            return
        if sound.isPlaying():
            sound.stop()
        sound.play()


# глобальный объект (один на всё приложение)
sound_manager = SoundManager()

# ------------------ Декоратор ------------------ #
from functools import wraps


def with_sound(sound_name="click"):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            sound_manager.play(sound_name)
            return func(*args, **kwargs)

        return wrapper

    return decorator


# ------------------ Конфигурация ------------------ #
ADMIN_DB_PASSWORD = "akiba1212"  # Пароль администратора PostgreSQL


# ------------------ Транзакции ------------------ #
class PharmacyTransactionManager:
    def __init__(self, conn, cursor):
        self.conn = conn
        self.cursor = cursor
        self.savepoints = []

    @contextmanager
    def transaction(self, operation_name="Операция"):
        """Контекстный менеджер для транзакций PostgreSQL"""
        try:
            self.cursor.execute("BEGIN TRANSACTION;")
            yield self
            self.cursor.execute("COMMIT;")
        except Exception as e:
            self.cursor.execute("ROLLBACK;")
            raise

    def create_savepoint(self, name):
        """Создание точки сохранения в PostgreSQL"""
        savepoint_name = f"sp_{name}_{len(self.savepoints)}"
        self.cursor.execute(f"SAVEPOINT {savepoint_name}")
        self.savepoints.append(savepoint_name)
        return savepoint_name

    def rollback_to_savepoint(self, savepoint_name):
        """Откат к точке сохранения в PostgreSQL"""
        if savepoint_name in self.savepoints:
            self.cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            index = self.savepoints.index(savepoint_name)
            self.savepoints = self.savepoints[:index + 1]

    def release_savepoint(self, savepoint_name):
        """Освобождение точки сохранения в PostgreSQL"""
        if savepoint_name in self.savepoints:
            self.cursor.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            self.savepoints.remove(savepoint_name)


# ------------------ Менеджер БД ------------------ #
class DatabaseManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.connection = None
            cls._instance.cursor = None
        return cls._instance

    def connect(self, dbname='pharmacydb'):
        try:
            self.connection = psycopg2.connect(
                dbname=dbname,
                user='postgres',
                password='akiba1212',
                host='localhost',
                port=5432
            )
            self.cursor = self.connection.cursor()
            self._create_tables(self.cursor)
            self.connection.commit()
            return True
        except Exception as e:
            print(f"Ошибка подключения: {e}")
            return False

    def get_cursor(self):
        return self.cursor

    def get_connection(self):
        return self.connection

    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()

    def _create_tables(self, cursor):
        """Создание таблиц с CHECK constraints вместо триггеров для простой валидации"""
        tables_sql = """
            -- Таблица пользователей с проверкой email и пароля
            CREATE TABLE IF NOT EXISTS public.dbusers (
                ID_User INT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                user_email VARCHAR(255) UNIQUE NOT NULL 
                    CHECK (user_email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'),
                user_password VARCHAR(255) NOT NULL CHECK (length(user_password) >= 6),
                user_role VARCHAR(50) DEFAULT 'pharmacy_user' 
                    CHECK (user_role IN ('admin', 'manager', 'pharmacist', 'pharmacy_user')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Таблица поставщиков с проверками
            CREATE TABLE IF NOT EXISTS public.Supplier (
                ID_Supplier INT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                SupplierName VARCHAR(255) NOT NULL CHECK (length(SupplierName) >= 2),
                ContactPerson VARCHAR(255),
                Phone VARCHAR(50) CHECK (Phone IS NULL OR Phone ~ '^[0-9\\+\\(\\)\\- ]+$'),
                Email VARCHAR(255) CHECK (Email IS NULL OR Email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'),
                Address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Таблица лекарств с проверками
            CREATE TABLE IF NOT EXISTS public.Medicine (
                ID_Medicine INT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                MedicineName VARCHAR(255) NOT NULL CHECK (length(MedicineName) >= 2),
                ActiveSubstance VARCHAR(255),
                Dosage VARCHAR(100),
                Form VARCHAR(100),
                PrescriptionRequired BOOLEAN DEFAULT FALSE,
                Price DECIMAL(10,2) NOT NULL CHECK (Price >= 0),
                ID_Supplier INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ID_Supplier) REFERENCES Supplier(ID_Supplier) ON DELETE SET NULL
            );

            -- Таблица инвентаря с проверкой срока годности и количества
            CREATE TABLE IF NOT EXISTS public.Inventory (
                ID_Inventory INT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                ID_Medicine INT NOT NULL,
                BatchNumber VARCHAR(100) NOT NULL,
                Quantity INT NOT NULL DEFAULT 0 CHECK (Quantity >= 0),
                ExpiryDate DATE NOT NULL CHECK (ExpiryDate >= CURRENT_DATE),
                PurchasePrice DECIMAL(10,2) CHECK (PurchasePrice >= 0),
                PurchaseDate DATE DEFAULT CURRENT_DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ID_Medicine) REFERENCES Medicine(ID_Medicine) ON DELETE CASCADE,
                UNIQUE(ID_Medicine, BatchNumber)
            );

            -- Таблица продаж с проверками
            CREATE TABLE IF NOT EXISTS public.Sales (
                ID_Sale INT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                SaleDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CustomerName VARCHAR(255) NOT NULL CHECK (length(CustomerName) >= 2),
                CustomerPhone VARCHAR(50),
                TotalAmount DECIMAL(10,2) NOT NULL CHECK (TotalAmount >= 0),
                PaymentMethod VARCHAR(50) DEFAULT 'cash' 
                    CHECK (PaymentMethod IN ('cash', 'card', 'transfer')),
                ID_User INT,
                FOREIGN KEY (ID_User) REFERENCES dbusers(ID_User) ON DELETE SET NULL
            );

            -- Таблица позиций продаж
            CREATE TABLE IF NOT EXISTS public.SaleItems (
                ID_SaleItem INT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                ID_Sale INT NOT NULL,
                ID_Medicine INT NOT NULL,
                Quantity INT NOT NULL CHECK (Quantity > 0),
                UnitPrice DECIMAL(10,2) NOT NULL CHECK (UnitPrice >= 0),
                TotalPrice DECIMAL(10,2) NOT NULL CHECK (TotalPrice >= 0),
                FOREIGN KEY (ID_Sale) REFERENCES Sales(ID_Sale) ON DELETE CASCADE,
                FOREIGN KEY (ID_Medicine) REFERENCES Medicine(ID_Medicine) ON DELETE CASCADE
            );

            -- Таблица для архива удаленных лекарств
            CREATE TABLE IF NOT EXISTS public.Medicine_archive (
                ID_Medicine INT PRIMARY KEY,
                MedicineName VARCHAR(255) NOT NULL,
                ActiveSubstance VARCHAR(255),
                Dosage VARCHAR(100),
                Form VARCHAR(100),
                PrescriptionRequired BOOLEAN,
                Price DECIMAL(10,2),
                ID_Supplier INT,
                created_at TIMESTAMP,
                modified_at TIMESTAMP,
                deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Таблица уведомлений о низких остатках
            CREATE TABLE IF NOT EXISTS public.low_stock_notifications (
                ID_Notification INT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                ID_Medicine INT NOT NULL,
                CurrentQuantity INT NOT NULL,
                NotificationDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                IsResolved BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (ID_Medicine) REFERENCES Medicine(ID_Medicine) ON DELETE CASCADE
            );
        """
        cursor.execute(tables_sql)
        self._install_triggers(cursor)

    def _install_triggers(self, cursor):
        try:
            self._create_triggers_directly(cursor)
        except Exception as e:
            print(f"Ошибка установки триггеров: {e}")
            self._create_triggers_directly(cursor)

    def _create_triggers_directly(self, cursor):
        triggers_sql = [
            # Триггер для автоматического обновления времени модификации
            """
            CREATE OR REPLACE FUNCTION update_modified_time()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.modified_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS tr_medicine_modified ON Medicine;
            CREATE TRIGGER tr_medicine_modified
                BEFORE UPDATE ON Medicine
                FOR EACH ROW
                EXECUTE FUNCTION update_modified_time();

            DROP TRIGGER IF EXISTS tr_users_modified ON dbusers;
            CREATE TRIGGER tr_users_modified
                BEFORE UPDATE ON dbusers
                FOR EACH ROW
                EXECUTE FUNCTION update_modified_time();
            """,

            # Триггер для проверки остатков при продаже (сложная бизнес-логика)
            """
            CREATE OR REPLACE FUNCTION check_inventory_quantity()
            RETURNS TRIGGER AS $$
            DECLARE
                available_quantity INTEGER;
            BEGIN
                -- Получаем доступное количество (только с нормальным сроком годности)
                SELECT COALESCE(SUM(Quantity), 0) INTO available_quantity 
                FROM Inventory 
                WHERE ID_Medicine = NEW.ID_Medicine
                AND ExpiryDate > CURRENT_DATE;

                IF available_quantity < NEW.Quantity THEN
                    RAISE EXCEPTION 'Недостаточно товара на складе. Доступно: %, запрошено: %', 
                                    available_quantity, NEW.Quantity;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS tr_check_quantity_before_sale ON SaleItems;
            CREATE TRIGGER tr_check_quantity_before_sale
                BEFORE INSERT ON SaleItems
                FOR EACH ROW
                EXECUTE FUNCTION check_inventory_quantity();
            """,

            # Триггер для архивации удаленных лекарств
            """
            CREATE OR REPLACE FUNCTION archive_deleted_medicine()
            RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO Medicine_archive 
                VALUES (OLD.ID_Medicine, OLD.MedicineName, OLD.ActiveSubstance, 
                       OLD.Dosage, OLD.Form, OLD.PrescriptionRequired, OLD.Price,
                       OLD.ID_Supplier, OLD.created_at, OLD.modified_at, CURRENT_TIMESTAMP);
                RETURN OLD;
            END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS tr_archive_medicine ON Medicine;
            CREATE TRIGGER tr_archive_medicine
                AFTER DELETE ON Medicine
                FOR EACH ROW
                EXECUTE FUNCTION archive_deleted_medicine();
            """,

            # Триггер для уведомлений о низких остатках
            """
            CREATE OR REPLACE FUNCTION check_low_stock()
            RETURNS TRIGGER AS $$
            BEGIN
                -- Если остаток меньше 10 и уведомление еще не создано
                IF NEW.Quantity < 10 AND NOT EXISTS (
                    SELECT 1 FROM low_stock_notifications 
                    WHERE ID_Medicine = NEW.ID_Medicine AND IsResolved = FALSE
                ) THEN
                    INSERT INTO low_stock_notifications (ID_Medicine, CurrentQuantity)
                    VALUES (NEW.ID_Medicine, NEW.Quantity);
                END IF;

                -- Если остаток восстановлен до нормального уровня
                IF NEW.Quantity >= 10 THEN
                    UPDATE low_stock_notifications 
                    SET IsResolved = TRUE 
                    WHERE ID_Medicine = NEW.ID_Medicine AND IsResolved = FALSE;
                END IF;

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS tr_check_low_stock ON Inventory;
            CREATE TRIGGER tr_check_low_stock
                AFTER INSERT OR UPDATE ON Inventory
                FOR EACH ROW
                EXECUTE FUNCTION check_low_stock();
            """
        ]

        for sql in triggers_sql:
            try:
                cursor.execute(sql)
            except Exception as e:
                print(f"Ошибка создания триггера: {e}")

    def get_all_medicines(self):
        self.cursor.execute("""
            SELECT m.ID_Medicine, m.MedicineName, m.ActiveSubstance, m.Dosage, m.Form, m.Price,
                   COALESCE(SUM(i.Quantity),0)
            FROM Medicine m
            LEFT JOIN Inventory i ON m.ID_Medicine = i.ID_Medicine
            GROUP BY m.ID_Medicine
        """)
        rows = self.cursor.fetchall()
        return [
            {"id": r[0], "name": r[1], "ingredient": r[2], "dosage": r[3], "form": r[4], "price": float(r[5]),
             "quantity": r[6]}
            for r in rows
        ]

    def get_new_sale_id(self):
        self.cursor.execute("SELECT COALESCE(MAX(ID_Sale), 0) + 1 FROM Sales")
        return self.cursor.fetchone()[0]

    def get_all_sales(self):
        self.cursor.execute("""
            SELECT s.ID_Sale, s.SaleDate, s.TotalAmount, 0 as Discount, s.TotalAmount as FinalTotal
            FROM Sales s
            ORDER BY s.SaleDate DESC
        """)
        rows = self.cursor.fetchall()
        return [
            {
                "id": r[0],
                "date": r[1],
                "total": float(r[2]),
                "discount": float(r[3]),
                "final_total": float(r[4])
            }
            for r in rows
        ]

    def get_inventory(self):
        self.cursor.execute("""
            SELECT i.ID_Inventory, m.MedicineName, i.Quantity, i.ExpiryDate, s.SupplierName
            FROM Inventory i
            LEFT JOIN Medicine m ON i.ID_Medicine = m.ID_Medicine
            LEFT JOIN Supplier s ON m.ID_Supplier = s.ID_Supplier
            WHERE i.ExpiryDate >= CURRENT_DATE  -- Только с нормальным сроком годности
            ORDER BY i.ID_Inventory
        """)
        rows = self.cursor.fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "quantity": r[2],
                "expiry_date": r[3],
                "supplier": r[4] or ""
            }
            for r in rows
        ]

    def get_expiring_medicines(self, days=30):
        self.cursor.execute("""
            SELECT m.ID_Medicine, m.MedicineName, i.ExpiryDate, i.Quantity
            FROM Inventory i
            JOIN Medicine m ON i.ID_Medicine = m.ID_Medicine
            WHERE i.ExpiryDate BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '%s days'
            ORDER BY i.ExpiryDate
        """, (days,))
        rows = self.cursor.fetchall()
        return [
            {"id": r[0], "name": r[1], "expiry_date": r[2], "quantity": r[3]}
            for r in rows
        ]

    def get_all_suppliers(self):
        self.cursor.execute("""
            SELECT ID_Supplier, SupplierName
            FROM Supplier
            ORDER BY SupplierName
        """)
        rows = self.cursor.fetchall()
        return [{"id": r[0], "name": r[1]} for r in rows]

    def search_inventory(self, medicine=None, supplier=None, expiry_date=None):
        query = """
            SELECT i.ID_Inventory, m.MedicineName, i.Quantity, i.ExpiryDate, s.SupplierName
            FROM Inventory i
            LEFT JOIN Medicine m ON i.ID_Medicine = m.ID_Medicine
            LEFT JOIN Supplier s ON m.ID_Supplier = s.ID_Supplier
            WHERE 1=1
        """
        params = []
        if medicine:
            query += " AND m.MedicineName ILIKE %s"
            params.append(f"%{medicine}%")
        if supplier:
            query += " AND s.SupplierName ILIKE %s"
            params.append(f"%{supplier}%")
        if expiry_date:
            query += " AND i.ExpiryDate <= %s"
            params.append(expiry_date)

        query += " ORDER BY i.ExpiryDate"
        self.cursor.execute(query, tuple(params))
        rows = self.cursor.fetchall()
        return [
            {"id": r[0], "name": r[1], "quantity": r[2], "expiry_date": r[3], "supplier": r[4] or ""}
            for r in rows
        ]

    def get_low_stock_notifications(self):
        """Получить уведомления о низких остатках"""
        self.cursor.execute("""
            SELECT n.ID_Notification, m.MedicineName, n.CurrentQuantity, n.NotificationDate
            FROM low_stock_notifications n
            JOIN Medicine m ON n.ID_Medicine = m.ID_Medicine
            WHERE n.IsResolved = FALSE
            ORDER BY n.NotificationDate DESC
        """)
        rows = self.cursor.fetchall()
        return [
            {
                "id": r[0],
                "medicine_name": r[1],
                "quantity": r[2],
                "date": r[3]
            }
            for r in rows
        ]

    def get_medicine_history(self, medicine_id):
        """Получить историю изменений лекарства"""
        self.cursor.execute("""
            SELECT MedicineName, ActiveSubstance, Dosage, Form, Price, modified_at
            FROM Medicine
            WHERE ID_Medicine = %s
            UNION ALL
            SELECT MedicineName, ActiveSubstance, Dosage, Form, Price, deleted_at as modified_at
            FROM Medicine_archive
            WHERE ID_Medicine = %s
            ORDER BY modified_at DESC
        """, (medicine_id, medicine_id))
        return self.cursor.fetchall()


class DatabaseInitializerThread(QThread):
    finished = pyqtSignal(bool)
    progress = pyqtSignal(str)

    def __init__(self, connection_params):
        super().__init__()
        self.connection_params = connection_params

    def run(self):
        try:
            self.progress.emit("Подключение к PostgreSQL...")
            conn = psycopg2.connect(**self.connection_params)
            conn.autocommit = True
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM pg_database WHERE datname='pharmacydb';")
            if not cursor.fetchone():
                self.progress.emit("Создание базы pharmacydb...")
                cursor.execute("CREATE DATABASE pharmacydb ENCODING 'UTF8';")
            cursor.close()
            conn.close()
            self.progress.emit("База данных готова")
            self.finished.emit(True)
        except Exception as e:
            print(f"Ошибка инициализации: {e}")
            traceback.print_exc()
            self.finished.emit(False)


class RegistrationDialog(QDialog):
    def __init__(self, db_manager):
        super().__init__()
        self.db_manager = db_manager
        self.setWindowTitle("Регистрация")
        self.setGeometry(300, 300, 400, 350)
        self.setStyleSheet("background-color: rgb(240, 248, 255);")
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("Email (например: user@example.com)")
        layout.addWidget(self.email_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Пароль (минимум 6 символов)")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password_edit)

        self.repeat_edit = QLineEdit()
        self.repeat_edit.setPlaceholderText("Повторите пароль")
        self.repeat_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.repeat_edit)

        role_layout = QHBoxLayout()
        role_label = QLabel("Роль:")
        self.role_combo = QComboBox()
        self.role_combo.addItem("Пользователь", "pharmacy_user")
        self.role_combo.addItem("Администратор", "admin")
        self.role_combo.addItem("Фармацевт", "pharmacist")
        self.role_combo.addItem("Менеджер", "manager")
        role_layout.addWidget(role_label)
        role_layout.addWidget(self.role_combo)
        layout.addLayout(role_layout)

        # Поле для пароля администратора БД
        self.admin_password_layout = QVBoxLayout()
        self.admin_password_label = QLabel("Пароль администратора БД:")
        self.admin_password_edit = QLineEdit()
        self.admin_password_edit.setPlaceholderText("Введите пароль администратора PostgreSQL")
        self.admin_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.admin_password_layout.addWidget(self.admin_password_label)
        self.admin_password_layout.addWidget(self.admin_password_edit)
        layout.addLayout(self.admin_password_layout)

        # Скрываем поле пароля админа по умолчанию
        self.admin_password_label.setVisible(False)
        self.admin_password_edit.setVisible(False)

        self.register_btn = QPushButton("Зарегистрироваться")
        layout.addWidget(self.register_btn)
        self.register_btn.clicked.connect(self.register_user)

        # Отслеживаем изменение роли
        self.role_combo.currentTextChanged.connect(self.on_role_changed)

    def on_role_changed(self, role_text):
        """Показываем поле пароля админа только при выборе роли Администратор"""
        is_admin = role_text == "Администратор"
        self.admin_password_label.setVisible(is_admin)
        self.admin_password_edit.setVisible(is_admin)

    @with_sound("click")
    def register_user(self, checked=False):
        email = self.email_edit.text().strip()
        password = self.password_edit.text().strip()
        repeat = self.repeat_edit.text().strip()
        role = self.role_combo.currentData()
        admin_password = self.admin_password_edit.text().strip()

        # Базовые проверки
        if not email or not password:
            QMessageBox.warning(self, "Ошибка", "Введите email и пароль")
            return

        if len(password) < 6:
            QMessageBox.warning(self, "Ошибка", "Пароль должен содержать минимум 6 символов")
            return

        if password != repeat:
            QMessageBox.warning(self, "Ошибка", "Пароли не совпадают")
            return

        # Проверка email через CHECK constraint в БД (не дублируем логику)

        # Проверка пароля администратора для роли admin
        if role == "admin":
            if not admin_password:
                QMessageBox.warning(self, "Ошибка", "Для регистрации администратора требуется пароль администратора БД")
                return
            if admin_password != ADMIN_DB_PASSWORD:
                QMessageBox.warning(self, "Ошибка", "Неверный пароль администратора БД")
                return

        cursor = self.db_manager.get_cursor()
        try:
            cursor.execute("INSERT INTO dbusers(user_email,user_password,user_role) VALUES(%s,%s,%s)",
                           (email, password, role))
            self.db_manager.get_connection().commit()
            QMessageBox.information(self, "Успешно", f"Пользователь {email} зарегистрирован как {role}")
            self.accept()
        except psycopg2.errors.UniqueViolation:
            self.db_manager.get_connection().rollback()
            QMessageBox.warning(self, "Ошибка", "Пользователь с таким email уже существует")
        except psycopg2.errors.CheckViolation as e:
            self.db_manager.get_connection().rollback()
            if "user_email" in str(e):
                QMessageBox.warning(self, "Ошибка", "Некорректный формат email")
            elif "user_password" in str(e):
                QMessageBox.warning(self, "Ошибка", "Пароль должен содержать минимум 6 символов")
            else:
                QMessageBox.warning(self, "Ошибка", f"Ошибка валидации: {e}")
        except Exception as e:
            self.db_manager.get_connection().rollback()
            QMessageBox.warning(self, "Ошибка", f"Ошибка регистрации: {e}")


# ------------------ Диалог входа ------------------ #
class LoginDialog(QDialog):
    def __init__(self, db_manager):
        super().__init__()
        self.db_manager = db_manager
        self.setWindowTitle("Вход")
        self.setGeometry(300, 300, 400, 300)
        self.setStyleSheet("background-color: rgb(240, 248, 255);")
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("Email")
        layout.addWidget(self.email_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Пароль")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password_edit)

        # Поле для пароля администратора БД (будет показано после проверки пользователя)
        self.admin_password_layout = QVBoxLayout()
        self.admin_password_label = QLabel("Пароль администратора БД:")
        self.admin_password_edit = QLineEdit()
        self.admin_password_edit.setPlaceholderText("Введите пароль администратора PostgreSQL")
        self.admin_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.admin_password_layout.addWidget(self.admin_password_label)
        self.admin_password_layout.addWidget(self.admin_password_edit)
        layout.addLayout(self.admin_password_layout)

        # Скрываем поле пароля админа по умолчанию
        self.admin_password_label.setVisible(False)
        self.admin_password_edit.setVisible(False)

        self.login_btn = QPushButton("Войти")
        self.register_btn = QPushButton("Регистрация")
        layout.addWidget(self.login_btn)
        layout.addWidget(self.register_btn)

        self.login_btn.clicked.connect(self.login)
        self.register_btn.clicked.connect(self.open_registration)

        # Переменная для хранения информации о пользователе
        self.current_user_role = None

    @with_sound("click")
    def login(self, checked=False):
        email = self.email_edit.text().strip()
        password = self.password_edit.text().strip()
        admin_password = self.admin_password_edit.text().strip()

        if not email or not password:
            QMessageBox.warning(self, "Ошибка", "Введите email и пароль")
            return

        cursor = self.db_manager.get_cursor()
        try:
            sql = "SELECT id_user, user_password, user_role FROM dbusers WHERE user_email=%s"
            cursor.execute(sql, (email,))
            result = cursor.fetchone()
            if not result:
                QMessageBox.warning(self, "Ошибка", "Пользователь не найден")
                return

            user_id, db_pass, db_role = result

            # Проверка пароля пользователя
            if password != db_pass:
                QMessageBox.warning(self, "Ошибка", "Неверный пароль")
                return

            # Если пользователь администратор, показываем поле для пароля администратора БД
            if db_role == "admin":
                if not self.admin_password_label.isVisible():
                    # Показываем поле для пароля администратора
                    self.admin_password_label.setVisible(True)
                    self.admin_password_edit.setVisible(True)
                    self.current_user_role = db_role
                    QMessageBox.information(self, "Требуется подтверждение",
                                            "Для входа как администратор введите пароль администратора БД")
                    return  # Прерываем вход, ждем ввод пароля админа

                # Проверяем пароль администратора БД
                if not admin_password:
                    QMessageBox.warning(self, "Ошибка",
                                        "Для входа как администратор требуется пароль администратора БД")
                    return
                if admin_password != ADMIN_DB_PASSWORD:
                    QMessageBox.warning(self, "Ошибка", "Неверный пароль администратора БД")
                    return

            # Если дошли сюда - вход успешен
            self.user_id = user_id
            self.user_role = db_role
            QMessageBox.information(self, "Успешно", f"Вход выполнен как {db_role}")
            self.accept()

        except Exception as e:
            traceback.print_exc()
            QMessageBox.warning(self, "Ошибка", f"Ошибка входа: {e}")

    def open_registration(self):
        dlg = RegistrationDialog(self.db_manager)
        dlg.exec()

class ManageMedicinesDialog(QDialog):
    def __init__(self, db_manager):
        super().__init__()
        uic.loadUi(load_ui_from_resource("manage_medicines.ui"), self)  # загружаем интерфейс

        self.db_manager = db_manager

        # Подключаем кнопки
        self.pushButton_add_medicine.clicked.connect(self.add_medicine)
        self.pushButton_add_inventory.clicked.connect(self.add_inventory)
        self.pushButton_edit.clicked.connect(self.edit_medicine)
        self.pushButton_delete.clicked.connect(self.delete_medicine)
        self.pushButton_refresh.clicked.connect(self.load_all)
        self.pushButton_close.clicked.connect(self.close)

        # Загружаем таблицы
        self.load_all()

    def load_all(self):
        self.load_medicines()
        self.load_inventory()
        self.load_suppliers()

    def populate_table(self, table: QTableView, data: list[tuple], headers: list[str]):
        """Универсальная функция для заполнения QTableView"""
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(headers)
        for row_data in data:
            row = []
            for item in row_data:
                row.append(QStandardItem(str(item)))
            model.appendRow(row)
        table.setModel(model)
        table.resizeColumnsToContents()

    def load_medicines(self):
        cursor = self.db_manager.get_cursor()
        cursor.execute("""
            SELECT m.ID_Medicine, m.MedicineName, m.ActiveSubstance, m.Dosage, m.Form, m.Price,
                   COALESCE(SUM(i.Quantity),0)
            FROM Medicine m
            LEFT JOIN Inventory i ON m.ID_Medicine = i.ID_Medicine
            GROUP BY m.ID_Medicine
            ORDER BY m.ID_Medicine
        """)
        data = cursor.fetchall()
        headers = ["ID", "Название", "Действующее вещество", "Дозировка", "Форма", "Цена", "Количество на складе"]
        self.populate_table(self.tableView_medicines, data, headers)

    def load_inventory(self):
        cursor = self.db_manager.get_cursor()
        cursor.execute("""
            SELECT i.ID_Inventory, m.MedicineName, i.BatchNumber, i.Quantity, i.PurchasePrice, i.ExpiryDate
            FROM Inventory i
            LEFT JOIN Medicine m ON i.ID_Medicine = m.ID_Medicine
            ORDER BY i.ID_Inventory
        """)
        data = cursor.fetchall()
        headers = ["ID", "Название лекарства", "Номер партии", "Количество", "Цена закупки", "Срок годности"]
        self.populate_table(self.tableView_inventory, data, headers)

    def load_suppliers(self):
        cursor = self.db_manager.get_cursor()
        cursor.execute("""
            SELECT ID_Supplier, SupplierName, ContactPerson, Phone, Email, Address
            FROM Supplier
            ORDER BY ID_Supplier
        """)
        data = cursor.fetchall()
        headers = ["ID", "Поставщик", "Контактное лицо", "Телефон", "Email", "Адрес"]
        self.populate_table(self.tableView_suppliers, data, headers)

    # ------------------ Заглушки для кнопок ------------------ #
    def add_medicine(self):
        dlg = MedicineFormDialog(self.db_manager)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.load_medicines()

    def edit_medicine(self):
        index = self.tableView_medicines.selectionModel().currentIndex()
        if not index.isValid():
            QMessageBox.warning(self, "Внимание", "Выберите лекарство для редактирования")
            return
        med_id = self.tableView_medicines.model().index(index.row(), 0).data()
        dlg = MedicineFormDialog(self.db_manager, med_id)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.load_medicines()

    def delete_medicine(self):
        index = self.tableView_medicines.selectionModel().currentIndex()
        if not index.isValid():
            QMessageBox.warning(self, "Внимание", "Выберите лекарство для удаления")
            return
        med_id = self.tableView_medicines.model().index(index.row(), 0).data()
        reply = QMessageBox.question(self, "Удаление", f"Удалить лекарство ID {med_id}?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            cursor = self.db_manager.get_cursor()
            try:
                cursor.execute("DELETE FROM Medicine WHERE ID_Medicine=%s", (med_id,))
                self.db_manager.get_connection().commit()
                self.load_all()
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить лекарство:\n{e}")

    def add_inventory(self):
        index = self.tableView_medicines.selectionModel().currentIndex()
        if not index.isValid():
            QMessageBox.warning(self, "Внимание", "Выберите лекарство для пополнения склада")
            return
        med_id = self.tableView_medicines.model().index(index.row(), 0).data()
        dlg = InventoryFormDialog(self.db_manager, med_id)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.load_inventory()


class MedicineFormDialog(QDialog):
    def __init__(self, db_manager, med_id=None):
        super().__init__()
        self.db_manager = db_manager
        self.med_id = med_id
        self.setWindowTitle("Лекарство")
        self.setGeometry(400, 200, 400, 300)

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Название лекарства")
        layout.addWidget(self.name_edit)

        self.substance_edit = QLineEdit()
        self.substance_edit.setPlaceholderText("Действующее вещество")
        layout.addWidget(self.substance_edit)

        self.dosage_edit = QLineEdit()
        self.dosage_edit.setPlaceholderText("Дозировка")
        layout.addWidget(self.dosage_edit)

        self.form_edit = QLineEdit()
        self.form_edit.setPlaceholderText("Форма выпуска")
        layout.addWidget(self.form_edit)

        self.price_edit = QLineEdit()
        self.price_edit.setPlaceholderText("Цена")
        layout.addWidget(self.price_edit)

        self.supplier_combo = QComboBox()
        layout.addWidget(self.supplier_combo)
        self.load_suppliers()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)

        if med_id:
            self.load_data()

    def load_suppliers(self):
        cursor = self.db_manager.get_cursor()
        cursor.execute("SELECT ID_Supplier, SupplierName FROM Supplier")
        suppliers = cursor.fetchall()
        self.supplier_combo.clear()
        for sup in suppliers:
            self.supplier_combo.addItem(sup[1], sup[0])

    def load_data(self):
        cursor = self.db_manager.get_cursor()
        cursor.execute(
            "SELECT MedicineName, ActiveSubstance, Dosage, Form, Price, ID_Supplier FROM Medicine WHERE ID_Medicine=%s",
            (self.med_id,))
        data = cursor.fetchone()
        if data:
            self.name_edit.setText(data[0])
            self.substance_edit.setText(data[1])
            self.dosage_edit.setText(data[2])
            self.form_edit.setText(data[3])
            self.price_edit.setText(str(data[4]))
            index = self.supplier_combo.findData(data[5])
            if index >= 0:
                self.supplier_combo.setCurrentIndex(index)

    def save(self):
        name = self.name_edit.text()
        substance = self.substance_edit.text()
        dosage = self.dosage_edit.text()
        form = self.form_edit.text()
        price = self.price_edit.text()
        supplier_id = self.supplier_combo.currentData()

        if not name or not price:
            QMessageBox.warning(self, "Ошибка", "Название и цена обязательны")
            return

        try:
            price_val = float(price)
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "Цена должна быть числом")
            return

        cursor = self.db_manager.get_cursor()
        try:
            if self.med_id:
                cursor.execute("""
                    UPDATE Medicine
                    SET MedicineName=%s, ActiveSubstance=%s, Dosage=%s, Form=%s, Price=%s, ID_Supplier=%s
                    WHERE ID_Medicine=%s
                """, (name, substance, dosage, form, price_val, supplier_id, self.med_id))
            else:
                cursor.execute("""
                    INSERT INTO Medicine (MedicineName, ActiveSubstance, Dosage, Form, Price, ID_Supplier)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (name, substance, dosage, form, price_val, supplier_id))
            self.db_manager.get_connection().commit()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить данные:\n{e}")


class InventoryFormDialog(QDialog):
    def __init__(self, db_manager, med_id):
        super().__init__()
        self.db_manager = db_manager
        self.med_id = med_id
        self.setWindowTitle("Пополнение склада")
        self.setGeometry(450, 250, 300, 250)

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.batch_edit = QLineEdit()
        self.batch_edit.setPlaceholderText("Номер партии")
        layout.addWidget(self.batch_edit)

        self.quantity_spin = QSpinBox()
        self.quantity_spin.setMinimum(1)
        self.quantity_spin.setMaximum(10000)
        self.quantity_spin.setValue(1)
        layout.addWidget(self.quantity_spin)

        self.expiry_date = QDateEdit()
        self.expiry_date.setDate(QDate.currentDate())
        self.expiry_date.setCalendarPopup(True)
        layout.addWidget(self.expiry_date)

        self.price_edit = QLineEdit()
        self.price_edit.setPlaceholderText("Цена закупки")
        layout.addWidget(self.price_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)

    def save(self):
        batch = self.batch_edit.text()
        qty = self.quantity_spin.value()
        expiry = self.expiry_date.date().toPyDate()
        try:
            purchase_price = float(self.price_edit.text())
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "Цена закупки должна быть числом")
            return

        try:
            conn = psycopg2.connect(
                dbname='pharmacydb',
                user='postgres',
                password='akiba1212',
                host='localhost',
                port=5432
            )
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO Inventory (ID_Medicine, BatchNumber, Quantity, ExpiryDate, PurchasePrice)
                VALUES (%s, %s, %s, %s, %s)
            """, (self.med_id, batch, qty, expiry, purchase_price))

            conn.commit()
            cursor.close()
            conn.close()

            QMessageBox.information(self, "Успех", "Товар успешно добавлен на склад")
            self.accept()

        except psycopg2.Error as e:
            # Специфичная обработка ошибок PostgreSQL
            error_msg = str(e)
            if "просроченное лекарство" in error_msg:
                QMessageBox.critical(self, "Ошибка", "Нельзя добавить просроченное лекарство")
            elif "Партия с номером" in error_msg:
                QMessageBox.critical(self, "Ошибка", "Партия с таким номером уже существует для этого лекарства")
            else:
                QMessageBox.critical(self, "Ошибка", f"Не удалось добавить на склад:\n{error_msg}")

            try:
                if 'conn' in locals():
                    conn.rollback()
                    conn.close()
            except:
                pass

class AddSaleDialog(QDialog):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        uic.loadUi(load_ui_from_resource("add_sale.ui"), self) # загружаем новый UI файл

        self.db_manager = db_manager
        self.items = []
        self.current_medicines = []

        # Подключаем кнопки
        self.pushButton_add_item.clicked.connect(self.add_item_to_table)
        self.pushButton_save.clicked.connect(self.save_sale)
        self.pushButton_cancel.clicked.connect(self.reject)

        # Подключаем сигналы
        self.comboBox_medicine.currentIndexChanged.connect(self.on_medicine_changed)
        self.spinBox_quantity.valueChanged.connect(self.update_total)

        # Загружаем данные
        self.load_medicines()
        self.setup_table()

    def load_medicines(self):
        """Загружаем список лекарств в комбобокс"""
        try:
            self.current_medicines = self.db_manager.get_all_medicines()
            self.comboBox_medicine.clear()

            for med in self.current_medicines:
                if med["quantity"] > 0:  # Показываем только те, что есть в наличии
                    self.comboBox_medicine.addItem(
                        f"{med['name']} ({med['quantity']} шт.)",
                        med["id"]
                    )
        except Exception as e:
            print(f"Ошибка загрузки лекарств: {e}")

    def setup_table(self):
        """Настраиваем таблицу товаров"""
        self.tableWidget_items.setColumnCount(5)
        self.tableWidget_items.setHorizontalHeaderLabels([
            "Лекарство", "Количество", "Цена за ед.", "Сумма", "Действие"
        ])
        self.tableWidget_items.horizontalHeader().setStretchLastSection(True)

    def on_medicine_changed(self, index):
        """Обновляем цену при выборе лекарства"""
        if index >= 0:
            med_id = self.comboBox_medicine.currentData()
            selected_med = next((med for med in self.current_medicines if med["id"] == med_id), None)
            if selected_med:
                self.lineEdit_price.setText(f"{selected_med['price']:.2f}")
                # Устанавливаем максимальное количество доступное на складе
                self.spinBox_quantity.setMaximum(selected_med["quantity"])
                self.update_total()

    def update_total(self):
        """Обновляем общую сумму при изменении количества"""
        try:
            price_text = self.lineEdit_price.text().replace(' руб.', '')
            price = float(price_text) if price_text else 0
            quantity = self.spinBox_quantity.value()
            total = price * quantity
            # Обновляем общую сумму в интерфейсе
            self.update_final_total()
        except ValueError:
            pass

    def add_item_to_table(self):
        """Добавляем выбранный товар в таблицу"""
        if self.comboBox_medicine.currentIndex() < 0:
            QMessageBox.warning(self, "Ошибка", "Выберите лекарство")
            return

        med_id = self.comboBox_medicine.currentData()
        selected_med = next((med for med in self.current_medicines if med["id"] == med_id), None)

        if not selected_med:
            return

        medicine_name = selected_med["name"]
        quantity = self.spinBox_quantity.value()
        price = selected_med["price"]
        total = price * quantity

        # Проверяем, есть ли уже это лекарство в таблице
        for row in range(self.tableWidget_items.rowCount()):
            if self.tableWidget_items.item(row, 0).text() == medicine_name:
                # Обновляем количество
                current_qty = int(self.tableWidget_items.item(row, 1).text())
                new_qty = current_qty + quantity
                self.tableWidget_items.item(row, 1).setText(str(new_qty))
                new_total = new_qty * price
                self.tableWidget_items.item(row, 3).setText(f"{new_total:.2f}")
                self.update_final_total()
                return

        row_position = self.tableWidget_items.rowCount()
        self.tableWidget_items.insertRow(row_position)

        # Заполняем данные
        self.tableWidget_items.setItem(row_position, 0, QTableWidgetItem(medicine_name))
        self.tableWidget_items.setItem(row_position, 1, QTableWidgetItem(str(quantity)))
        self.tableWidget_items.setItem(row_position, 2, QTableWidgetItem(f"{price:.2f}"))
        self.tableWidget_items.setItem(row_position, 3, QTableWidgetItem(f"{total:.2f}"))

        delete_btn = QPushButton("Удалить")
        delete_btn.clicked.connect(lambda: self.remove_item(row_position))
        self.tableWidget_items.setCellWidget(row_position, 4, delete_btn)

        # Сохраняем данные
        self.items.append({
            "medicine_id": med_id,
            "name": medicine_name,
            "quantity": quantity,
            "price": price,
            "total": total
        })

        self.update_final_total()

    def remove_item(self, row):
        """Удаляем товар из таблицы"""
        if 0 <= row < self.tableWidget_items.rowCount():
            self.tableWidget_items.removeRow(row)
            if row < len(self.items):
                self.items.pop(row)
            self.update_final_total()

    def update_final_total(self):
        """Обновляем общую сумму заказа"""
        total_amount = sum(item["total"] for item in self.items)
        self.label_total_value.setText(f"{total_amount:.2f} руб.")

    def save_sale(self):
        """Сохраняем продажу в базу данных"""
        if not self.items:
            QMessageBox.warning(self, "Ошибка", "Добавьте хотя бы один товар")
            return

        customer_name = self.lineEdit_customer_name.text().strip()
        if not customer_name:
            QMessageBox.warning(self, "Ошибка", "Введите имя покупателя")
            return

        try:
            cursor = self.db_manager.get_cursor()
            total_amount = sum(item["total"] for item in self.items)

            # Сохраняем продажу
            cursor.execute("""
                INSERT INTO Sales (CustomerName, CustomerPhone, TotalAmount, PaymentMethod)
                VALUES (%s, %s, %s, %s) RETURNING ID_Sale
            """, (
                customer_name,
                self.lineEdit_customer_phone.text(),
                total_amount,
                self.comboBox_payment_method.currentText()
            ))

            sale_id = cursor.fetchone()[0]

            # Сохраняем товары продажи
            for item in self.items:
                cursor.execute("""
                    INSERT INTO SaleItems (ID_Sale, ID_Medicine, Quantity, UnitPrice, TotalPrice)
                    VALUES (%s, %s, %s, %s, %s)
                """, (sale_id, item["medicine_id"], item["quantity"], item["price"], item["total"]))

                # Обновляем количество на складе
                cursor.execute("""
                    UPDATE Inventory 
                    SET Quantity = Quantity - %s 
                    WHERE ID_Medicine = %s
                """, (item["quantity"], item["medicine_id"]))

            self.db_manager.get_connection().commit()
            QMessageBox.information(self, "Успех", f"Продажа #{sale_id} успешно сохранена")
            self.accept()

        except Exception as e:
            self.db_manager.get_connection().rollback()
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить продажу: {e}")


class PharmacyMainWindow(QMainWindow):
    def __init__(self, db_manager, user_role):
        super().__init__()
        uic.loadUi(load_ui_from_resource("pharmacy_main.ui"), self)

        self.db_manager = db_manager
        self.user_role = user_role
        self.cart = []

        # Подключаем кнопки
        if hasattr(self, 'pushButton_add_to_cart'):
            self.pushButton_add_to_cart.clicked.connect(self.add_to_cart)

        if hasattr(self, 'pushButton_checkout'):
            self.pushButton_checkout.clicked.connect(self.checkout)

        if hasattr(self, 'pushButton_manage_medicines'):
            self.pushButton_manage_medicines.clicked.connect(self.open_manage_medicines)

        if hasattr(self, 'pushButton_search'):
            self.pushButton_search.clicked.connect(self.apply_filters)

        # Кнопка "Добавить продажу"
        if hasattr(self, 'pushButton_add_sale'):
            self.pushButton_add_sale.clicked.connect(self.open_add_sale)
        elif hasattr(self, 'pushButton_sale_details'):  # альтернативное название
            self.pushButton_sale_details.clicked.connect(self.open_add_sale)

        # Ограничения по ролям
        if hasattr(self, 'pushButton_manage_medicines'):
            self.pushButton_manage_medicines.setEnabled(self.user_role in ("admin", "manager"))

        if hasattr(self, 'pushButton_add_sale') or hasattr(self, 'pushButton_sale_details'):
            # Добавлять продажи могут админ, менеджер и фармацевт
            btn = getattr(self, 'pushButton_add_sale', getattr(self, 'pushButton_sale_details', None))
            if btn:
                btn.setEnabled(self.user_role in ("admin", "manager", "pharmacist"))

        if hasattr(self, 'pushButton_checkout'):
            # Или разрешить всем ролям
            self.pushButton_checkout.setEnabled(True)


        # Загружаем данные
        self.load_medicines()
        self.load_sales()
        self.load_inventory()
        self.load_expiring()
        self.load_combo_boxes()
        self.setup_notifications()

        # Подключаем двойной клик для AI информации
        self.tableView_medicines.doubleClicked.connect(self.show_medicine_info)

        # Тестовая кнопка скорости Ollama - только для админа
        if self.user_role == "admin":
            test_btn = QPushButton("Тест скорости Ollama", self)
            test_btn.move(10, 10)
            test_btn.clicked.connect(self.test_ollama_speed)
            test_btn.show()

        # Кнопка AI-справки
        self.pushButton_ai_info = QPushButton("AI-справка о лекарстве")
        self.pushButton_ai_info.clicked.connect(self.open_ai_info_dialog)
        self.pushButton_ai_info.setStyleSheet("""
            QPushButton {
                background-color: #6f42c1;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #563d7c;
            }
        """)

        # Добавляем кнопку в layout
        if hasattr(self, 'verticalLayout_buttons'):
            self.verticalLayout_buttons.addWidget(self.pushButton_ai_info)
        elif hasattr(self, 'horizontalLayout_buttons'):
            self.horizontalLayout_buttons.addWidget(self.pushButton_ai_info)
        else:
            button_layout = QHBoxLayout()
            button_layout.addWidget(self.pushButton_ai_info)
            button_layout.addStretch()

            if hasattr(self, 'centralWidget') and self.centralWidget().layout():
                main_layout = self.centralWidget().layout()
                main_layout.insertLayout(0, button_layout)

    def setup_notifications(self):
        """Настройка системы уведомлений"""
        # Создаем таймер для проверки уведомлений каждые 30 секунд
        self.notification_timer = QTimer()
        self.notification_timer.timeout.connect(self.check_notifications)
        self.notification_timer.start(30000)  # 30 секунд

        # Первоначальная проверка
        self.check_notifications()

    def check_notifications(self):
        """Проверка уведомлений о низких остатках"""
        try:
            notifications = self.db_manager.get_low_stock_notifications()
            if notifications:
                self.show_notification_banner(f"Внимание: {len(notifications)} лекарств с низким запасом")
        except Exception as e:
            print(f"Ошибка проверки уведомлений: {e}")

    def show_notification_banner(self, message):
        """Показать баннер с уведомлением"""
        # Можно реализовать всплывающее уведомление
        print(f"УВЕДОМЛЕНИЕ: {message}")

    # В метод load_medicines добавляем подсветку низких остатков
    def load_medicines(self):
        """Загрузка лекарств с подсветкой низких остатков"""
        try:
            medicines = self.db_manager.get_all_medicines()
            model = QStandardItemModel()
            headers = ["ID", "Название", "Действующее вещество", "Дозировка", "Форма", "Цена", "Количество"]
            model.setHorizontalHeaderLabels(headers)

            for med in medicines:
                row = [
                    QStandardItem(str(med["id"])),
                    QStandardItem(med["name"]),
                    QStandardItem(med.get("ingredient", "")),
                    QStandardItem(med.get("dosage", "")),
                    QStandardItem(med.get("form", "")),
                    QStandardItem(f'{med["price"]:.2f}'),
                    QStandardItem(str(med["quantity"]))
                ]

                # Подсветка низких остатков
                if med["quantity"] < 10:
                    for item in row:
                        item.setBackground(Qt.GlobalColor.yellow)
                elif med["quantity"] == 0:
                    for item in row:
                        item.setBackground(Qt.GlobalColor.red)

                model.appendRow(row)

            self.tableView_medicines.setModel(model)
            self.tableView_medicines.resizeColumnsToContents()
        except Exception as e:
            print(f"Ошибка загрузки лекарств: {e}")

    def show_medicine_info(self, index):
        """Показывает информацию о лекарстве при двойном клике"""
        if not index.isValid():
            return

        try:
            model = self.tableView_medicines.model()
            med_name = model.index(index.row(), 1).data()

            if med_name:
                print(f"Запрос информации: {med_name}")
                dlg = MedicineInfoDialogPro(med_name, self)
                dlg.exec()
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось получить название лекарства")
        except Exception as e:
            print(f"Ошибка: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть информацию: {e}")

    def open_ai_info_dialog(self):
        """Открывает улучшенный AI-диалог по выбранному лекарству"""
        selection = self.tableView_medicines.selectionModel()
        if not selection.hasSelection():
            QMessageBox.warning(self, "Внимание", "Выберите лекарство из списка")
            return

        model = self.tableView_medicines.model()
        med_name = model.index(selection.currentIndex().row(), 1).data()

        dlg = MedicineInfoDialogPro(med_name, self)
        dlg.exec()

    def open_add_sale(self):
        """Открывает диалог добавления продажи"""
        dlg = AddSaleDialog(self.db_manager, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.load_sales()      # Обновляем таблицу продаж
            self.load_medicines()  # Обновляем количество товаров
            self.load_inventory()  # Обновляем инвентарь

    def open_sale_detail(self):
        """Открывает диалог с деталями покупки (окно купить)"""
        if not self.cart:
            QMessageBox.warning(self, "Корзина пуста", "Добавьте товары в корзину перед покупкой")
            return

        dlg = SaleDetailsDialog(selected_items=self.cart, discount_percent=0, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Если покупка завершена, очищаем корзину
            self.cart.clear()
            QMessageBox.information(self, "Успех", "Покупка завершена успешно!")

    def load_medicines(self):
        """Загрузка лекарств"""
        try:
            medicines = self.db_manager.get_all_medicines()
            model = QStandardItemModel()
            headers = ["ID", "Название", "Действующее вещество", "Дозировка", "Форма", "Цена", "Количество"]
            model.setHorizontalHeaderLabels(headers)

            for med in medicines:
                row = [
                    QStandardItem(str(med["id"])),
                    QStandardItem(med["name"]),
                    QStandardItem(med.get("ingredient", "")),
                    QStandardItem(med.get("dosage", "")),
                    QStandardItem(med.get("form", "")),
                    QStandardItem(f'{med["price"]:.2f}'),
                    QStandardItem(str(med["quantity"]))
                ]
                model.appendRow(row)

            self.tableView_medicines.setModel(model)
            self.tableView_medicines.resizeColumnsToContents()
            self.tableView_medicines.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        except Exception as e:
            print(f"Ошибка загрузки лекарств: {e}")

    def load_sales(self):
        """Загрузка продаж"""
        try:
            sales = self.db_manager.get_all_sales()
            model = QStandardItemModel()
            headers = ["ID продажи", "Дата", "Сумма", "Скидка", "Итог"]
            model.setHorizontalHeaderLabels(headers)

            for sale in sales:
                # Форматируем дату продажи
                sale_date = sale["date"]
                if isinstance(sale_date, str):
                    try:
                        sale_date = datetime.strptime(sale_date, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
                    except:
                        pass
                elif hasattr(sale_date, 'strftime'):
                    sale_date = sale_date.strftime("%d.%m.%Y %H:%M")

                row = [
                    QStandardItem(str(sale["id"])),
                    QStandardItem(str(sale_date)),  # Используем отформатированную дату
                    QStandardItem(f'{sale["total"]:.2f}'),
                    QStandardItem(f'{sale["discount"]:.2f}'),
                    QStandardItem(f'{sale["final_total"]:.2f}')
                ]
                model.appendRow(row)

            self.tableView_sales.setModel(model)
            self.tableView_sales.resizeColumnsToContents()
        except Exception as e:
            print(f"Ошибка загрузки продаж: {e}")

    def load_inventory(self):
        """Загрузка инвентаря"""
        try:
            inventory = self.db_manager.get_inventory()
            model = QStandardItemModel()
            headers = ["ID", "Название", "Количество", "Срок годности", "Поставщик"]
            model.setHorizontalHeaderLabels(headers)

            for item in inventory:
                # Преобразуем дату в русский формат
                expiry_date = item["expiry_date"]
                if isinstance(expiry_date, str):
                    try:
                        # Если дата в строковом формате, преобразуем в datetime
                        expiry_date = datetime.strptime(expiry_date, "%Y-%m-%d").strftime("%d.%m.%Y")
                    except:
                        pass
                elif hasattr(expiry_date, 'strftime'):
                    # Если это объект даты, форматируем
                    expiry_date = expiry_date.strftime("%d.%m.%Y")

                row = [
                    QStandardItem(str(item["id"])),
                    QStandardItem(item["name"]),
                    QStandardItem(str(item["quantity"])),
                    QStandardItem(str(expiry_date)),  # Используем отформатированную дату
                    QStandardItem(item.get("supplier", ""))
                ]
                model.appendRow(row)

            self.tableView_inventory.setModel(model)
            self.tableView_inventory.resizeColumnsToContents()
        except Exception as e:
            print(f"Ошибка загрузки инвентаря: {e}")

    def load_expiring(self):
        """Загрузка лекарств с истекающим сроком"""
        try:
            expiring = self.db_manager.get_expiring_medicines()
            model = QStandardItemModel()
            headers = ["ID", "Название", "Срок годности", "Остаток"]
            model.setHorizontalHeaderLabels(headers)

            for med in expiring:
                # Форматируем дату
                expiry_date = med["expiry_date"]
                if isinstance(expiry_date, str):
                    try:
                        expiry_date = datetime.strptime(expiry_date, "%Y-%m-%d").strftime("%d.%m.%Y")
                    except:
                        pass
                elif hasattr(expiry_date, 'strftime'):
                    expiry_date = expiry_date.strftime("%d.%m.%Y")

                row = [
                    QStandardItem(str(med["id"])),
                    QStandardItem(med["name"]),
                    QStandardItem(str(expiry_date)),  # Используем отформатированную дату
                    QStandardItem(str(med["quantity"]))
                ]
                model.appendRow(row)

            self.tableView_expiring.setModel(model)
            self.tableView_expiring.resizeColumnsToContents()
        except Exception as e:
            print(f"Ошибка загрузки истекающих лекарств: {e}")

    def load_combo_boxes(self):
        """Заполнение выпадающих списков"""
        try:
            medicines = self.db_manager.get_all_medicines()
            self.comboBox_medicine.clear()
            self.comboBox_medicine.addItems([m["name"] for m in medicines])

            suppliers = self.db_manager.get_all_suppliers()
            self.comboBox_supplier.clear()
            self.comboBox_supplier.addItems([s["name"] for s in suppliers])
        except Exception as e:
            print(f"Ошибка загрузки данных в comboBox: {e}")

    def add_to_cart(self):
        index = self.tableView_medicines.selectionModel().currentIndex()
        if not index.isValid():
            QMessageBox.warning(self, "Внимание", "Выберите лекарство для добавления в корзину")
            return

        model = self.tableView_medicines.model()
        med_id = int(model.index(index.row(), 0).data())
        name = model.index(index.row(), 1).data()
        price = float(model.index(index.row(), 5).data())
        quantity_in_stock = int(model.index(index.row(), 6).data())

        qty, ok = QInputDialog.getInt(self, "Количество", f"Введите количество для '{name}':", 1, 1, quantity_in_stock)
        if not ok:
            return

        if qty > quantity_in_stock:
            QMessageBox.warning(self, "Ошибка", f"В наличии только {quantity_in_stock} шт.")
            return

        for item in self.cart:
            if item["id"] == med_id:
                item["quantity"] += qty
                break
        else:
            self.cart.append({"id": med_id, "name": name, "quantity": qty, "price": price})

        QMessageBox.information(self, "Добавлено", f"{qty} шт. '{name}' добавлено в корзину")

    def add_sale(self, customer_name, customer_phone, payment_method, items):
        """Сохраняет продажу и позиции продажи, возвращает (sale_id, sale_date)"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    total_amount = sum(item["price"] * item["quantity"] for item in items)

                    # Добавляем запись в Sales
                    cur.execute("""
                        INSERT INTO Sales (CustomerName, CustomerPhone, TotalAmount, PaymentMethod)
                        VALUES (%s, %s, %s, %s)
                        RETURNING ID_Sale, SaleDate;
                    """, (customer_name, customer_phone, total_amount, payment_method))

                    sale_id, sale_date = cur.fetchone()

                    # Добавляем позиции продажи
                    for item in items:
                        cur.execute("""
                            INSERT INTO SaleItems (ID_Sale, ID_Medicine, Quantity, UnitPrice, TotalPrice)
                            VALUES (%s, %s, %s, %s, %s);
                        """, (
                            sale_id,
                            item["id"],
                            item["quantity"],
                            item["price"],
                            item["quantity"] * item["price"]
                        ))

            return sale_id, sale_date

        except Exception as e:
            raise e

    def open_manage_medicines(self):
        dlg = ManageMedicinesDialog(self.db_manager)
        dlg.exec()

    def apply_filters(self):
        """Фильтрация (пример)"""
        med_filter = self.comboBox_medicine.currentText() if self.checkBox_medicine.isChecked() else None
        supplier_filter = self.comboBox_supplier.currentText() if self.checkBox_supplier.isChecked() else None
        date_filter = self.dateEdit.date().toString("dd-MM-yyyy") if self.checkBox_date.isChecked() else None

        results = self.db_manager.search_inventory(med_filter, supplier_filter, date_filter)

        model = QStandardItemModel()
        headers = ["ID", "Название", "Количество", "Срок годности", "Поставщик"]
        model.setHorizontalHeaderLabels(headers)

        for item in results:
            row = [
                QStandardItem(str(item["id"])),
                QStandardItem(item["name"]),
                QStandardItem(str(item["quantity"])),
                QStandardItem(str(item["expiry_date"])),
                QStandardItem(item.get("supplier", ""))
            ]
            model.appendRow(row)

        self.tableView_inventory.setModel(model)
        self.tableView_inventory.resizeColumnsToContents()

    def show_selected_medicine_info(self):
        """Показывает информацию о выбранном лекарстве по кнопке"""
        selection = self.tableView_medicines.selectionModel()
        if not selection.hasSelection():
            QMessageBox.warning(self, "Внимание", "Выберите лекарство из таблицы")
            return

        index = selection.currentIndex()
        self.show_medicine_info(index)

    def test_ollama_speed(self):
        """Тестирует скорость отклика Ollama"""
        from time import perf_counter
        import requests

        start = perf_counter()
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=5)
            elapsed = perf_counter() - start

            if r.status_code == 200:
                QMessageBox.information(
                    self,
                    "Тест Ollama",
                    f"Ollama отвечает за {elapsed:.2f} сек"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Тест Ollama",
                    f"Ollama ответил с кодом {r.status_code}"
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Тест Ollama",
                f"Ошибка подключения: {e}"
            )

    def checkout(self):
        """Обработка оформления заказа - открывает диалог с деталями продажи"""
        try:
            if not self.cart:
                QMessageBox.warning(self, "Корзина пуста", "Добавьте товары в корзину перед оформлением заказа")
                return

            # Получаем дополнительную информацию о товарах из базы данных
            enriched_cart = []
            for item in self.cart:
                # Получаем полную информацию о лекарстве из базы
                cursor = self.db_manager.get_cursor()
                cursor.execute("""
                    SELECT MedicineName, ActiveSubstance, Dosage, Form, Price 
                    FROM Medicine WHERE ID_Medicine = %s
                """, (item["id"],))
                med_data = cursor.fetchone()

                if med_data:
                    enriched_item = {
                        "id": item["id"],
                        "name": med_data[0],
                        "active_substance": med_data[1] or "",
                        "dosage": med_data[2] or "",
                        "form": med_data[3] or "",
                        "quantity": item["quantity"],
                        "price": float(med_data[4])
                    }
                    enriched_cart.append(enriched_item)

            # Создаем данные для продажи
            sale_data = {
                "customer": "Покупатель",  # Можно запросить у пользователя
                "phone": "",  # Можно запросить у пользователя
                "payment": "Наличные"  # Можно выбрать в диалоге
            }

            # Открываем диалог с деталями продажи
            dlg = SaleDetailsDialog(
                sale_data=sale_data,
                selected_items=enriched_cart,
                discount_percent=0,
                parent=self
            )

            if dlg.exec() == QDialog.DialogCode.Accepted:
                # Сохраняем продажу в базу данных
                self.save_sale_to_database(enriched_cart, sale_data)

        except Exception as e:
            print(f"Ошибка при оформлении заказа: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось оформить заказ: {e}")

    def save_sale_to_database(self, items, sale_data):
        """Сохраняет продажу в базу данных"""
        try:
            cursor = self.db_manager.get_cursor()

            # Вычисляем общую сумму
            total_amount = sum(item["quantity"] * item["price"] for item in items)

            # Сохраняем продажу
            cursor.execute("""
                INSERT INTO Sales (CustomerName, CustomerPhone, TotalAmount, PaymentMethod)
                VALUES (%s, %s, %s, %s) RETURNING ID_Sale
            """, (
                sale_data.get("customer", "Покупатель"),
                sale_data.get("phone", ""),
                total_amount,
                sale_data.get("payment", "Наличные")
            ))

            sale_id = cursor.fetchone()[0]

            # Сохраняем товары продажи
            for item in items:
                cursor.execute("""
                    INSERT INTO SaleItems (ID_Sale, ID_Medicine, Quantity, UnitPrice, TotalPrice)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    sale_id,
                    item["id"],
                    item["quantity"],
                    item["price"],
                    item["quantity"] * item["price"]
                ))

                # Обновляем количество на складе
                cursor.execute("""
                    UPDATE Inventory 
                    SET Quantity = Quantity - %s 
                    WHERE ID_Medicine = %s AND Quantity >= %s
                """, (item["quantity"], item["id"], item["quantity"]))

            self.db_manager.get_connection().commit()

            # Очищаем корзину
            self.cart.clear()

            # Обновляем данные в интерфейсе
            self.load_medicines()
            self.load_sales()
            self.load_inventory()

            QMessageBox.information(self, "Успех", f"Продажа #{sale_id} успешно сохранена!")

        except Exception as e:
            self.db_manager.get_connection().rollback()
            print(f"Ошибка сохранения продажи: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить продажу: {e}")

class SaleDetailsDialog(QDialog):
    def __init__(self, sale_data=None, selected_items=None, discount_percent=0, parent=None):
        super().__init__(parent)
        uic.loadUi(load_ui_from_resource("sale_details.ui"), self)

        self.discount_percent = discount_percent
        self.selected_items = selected_items or []
        self.sale_data = sale_data or {}

        # Проверяем элементы
        required_widgets = [
            "tableWidget_items",
            "label_total_amount_value",
            "pushButton_close",
            "pushButton_print",
            "label_sale_id_value",
            "label_sale_date_value",
            "lineEdit_customer_name",
            "lineEdit_customer_phone",
            "comboBox_payment_method"
        ]
        for w in required_widgets:
            if not hasattr(self, w):
                raise AttributeError(f"В sale_details.ui не найден элемент '{w}'")

        # Заполняем варианты оплаты
        self.comboBox_payment_method.addItems(["Наличные", "Карта", "Безналичные"])

        # Кнопки
        self.pushButton_close.clicked.connect(self.close)
        self.pushButton_print.clicked.connect(self.print_receipt)

        # Заполняем данные
        self.load_sale_info()
        self.load_items()
        self.update_totals()

    def load_sale_info(self):
        """Заполняем заголовочные данные"""
        # ID и дата (если уже сохранены)
        self.label_sale_id_value.setText(str(self.sale_data.get("id", "-")))

        # Форматируем дату продажи
        sale_date = self.sale_data.get("date", "-")
        if sale_date != "-" and hasattr(sale_date, 'strftime'):
            sale_date = sale_date.strftime("%d.%m.%Y %H:%M:%S")

        self.label_sale_date_value.setText(str(sale_date))

        # Имя и телефон покупателя
        self.lineEdit_customer_name.setText(self.sale_data.get("customer", ""))
        self.lineEdit_customer_phone.setText(self.sale_data.get("phone", ""))

        # Способ оплаты
        payment = self.sale_data.get("payment", "Наличные")
        index = self.comboBox_payment_method.findText(payment)
        if index >= 0:
            self.comboBox_payment_method.setCurrentIndex(index)

    def load_items(self):
        """Заполняем таблицу выбранными товарами"""
        self.tableWidget_items.setRowCount(len(self.selected_items))
        self.tableWidget_items.setColumnCount(6)
        self.tableWidget_items.setHorizontalHeaderLabels([
            "Лекарство", "Действующее вещество", "Дозировка",
            "Количество", "Цена за ед.", "Сумма"
        ])

        for row, item in enumerate(self.selected_items):
            self.tableWidget_items.setItem(row, 0, QTableWidgetItem(item.get("name", "")))
            self.tableWidget_items.setItem(row, 1, QTableWidgetItem(item.get("active_substance", "")))
            self.tableWidget_items.setItem(row, 2, QTableWidgetItem(item.get("dosage", "")))
            self.tableWidget_items.setItem(row, 3, QTableWidgetItem(str(item.get("quantity", 0))))
            self.tableWidget_items.setItem(row, 4, QTableWidgetItem(f'{item.get("price", 0):.2f}'))

            total = item.get("quantity", 0) * item.get("price", 0)
            self.tableWidget_items.setItem(row, 5, QTableWidgetItem(f'{total:.2f}'))

        self.tableWidget_items.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def update_totals(self):
        """Пересчёт общей суммы"""
        total = sum(item.get("quantity", 0) * item.get("price", 0.0) for item in self.selected_items)
        if self.discount_percent > 0:
            total -= total * (self.discount_percent / 100)
        self.label_total_amount_value.setText(f"{total:.2f} руб.")

    def print_receipt(self):
        """Сохраняем продажу в БД и печатаем чек"""
        customer_name = self.lineEdit_customer_name.text().strip()
        customer_phone = self.lineEdit_customer_phone.text().strip()
        payment_method = self.comboBox_payment_method.currentText()

        if not customer_name:
            QMessageBox.warning(self, "Ошибка", "Введите имя покупателя")
            return

        try:
            cursor = self.parent().db_manager.get_cursor()

            total_amount = sum(item["quantity"] * item["price"] for item in self.selected_items)

            # Сохраняем продажу
            cursor.execute("""
                INSERT INTO Sales (CustomerName, CustomerPhone, TotalAmount, PaymentMethod)
                VALUES (%s, %s, %s, %s)
                RETURNING ID_Sale, SaleDate
            """, (customer_name, customer_phone, total_amount, payment_method))

            sale_id, sale_date = cursor.fetchone()

            # Сохраняем позиции
            for item in self.selected_items:
                cursor.execute("""
                    INSERT INTO SaleItems (ID_Sale, ID_Medicine, Quantity, UnitPrice, TotalPrice)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    sale_id,
                    item["id"],
                    item["quantity"],
                    item["price"],
                    item["quantity"] * item["price"]
                ))

            self.parent().db_manager.get_connection().commit()

            # Обновляем интерфейс
            self.label_sale_id_value.setText(str(sale_id))
            self.label_sale_date_value.setText(str(sale_date))

            QMessageBox.information(self, "Успех", f"Чек #{sale_id} успешно сохранён и напечатан!")

            self.label_sale_date_value.setText(sale_date.strftime("%d.%m.%Y %H:%M:%S"))
        # Закрываем диалог
        except Exception as e:
            self.parent().db_manager.get_connection().rollback()
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить чек: {e}")


import subprocess

# полный путь к ollama.exe на ПК
OLLAMA_PATH = r"C:\Users\Xazor\AppData\Local\Programs\Ollama\ollama app.exe"

def get_medicine_info_ollama(name: str) -> str:
    prompt = f"Дай краткую информацию о лекарстве: {name}"
    try:
        result = subprocess.run(
            [OLLAMA_PATH, "chat", "--model", "llama2", "--input", prompt],
            capture_output=True,
            text=True,
            timeout=20
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return f"Ошибка Ollama: {result.stderr.strip()}"
    except FileNotFoundError:
        return f"Не найден файл ollama.exe по пути: {OLLAMA_PATH}"
    except subprocess.TimeoutExpired:
        return "Превышено время ожидания ответа от Ollama"
    except Exception as e:
        return f"Ошибка при получении информации: {e}"


def check_ollama_status():
    """Проверяет статус Ollama сервера"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            if any(model.get('name', '').startswith('llama2') for model in models):
                return True, "Ollama запущен, модель llama2 доступна"
            else:
                return False, "Ollama запущен, но модель llama2 не найдена"
        return False, "Ollama не отвечает"
    except requests.exceptions.ConnectionError:
        return False, "Ollama не запущен"
    except Exception as e:
        return False, f"Ошибка проверки Ollama: {e}"


class FastOllamaMedicineThread(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, medicine_name):
        super().__init__()
        self.medicine_name = medicine_name

    def run(self):
        try:
            # Улучшенный запрос к Ollama
            prompt = f"Дай краткую медицинскую информацию о лекарственном препарате '{self.medicine_name}': основное применение, дозировка, противопоказания. Ответь на русском языке."

            data = {
                "model": "llama2",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 150,
                    "temperature": 0.3,
                    "top_p": 0.9
                }
            }

            print(f"🔄 Запрос к Ollama: {self.medicine_name}")

            response = requests.post(
                "http://localhost:11434/api/generate",
                json=data,
                timeout=15
            )

            if response.status_code == 200:
                result = response.json()
                info = result.get('response', '').strip()

                if info and len(info) > 10:  # Проверяем что ответ не пустой
                    # Очистка и форматирование ответа
                    info = self.clean_response(info)
                    self.finished.emit(info)
                else:
                    self.error.emit("Не удалось получить информацию о лекарстве")
            else:
                self.error.emit(f"Ошибка API Ollama: {response.status_code}")

        except requests.exceptions.ConnectionError:
            self.error.emit("Не удалось подключиться к Ollama. Убедитесь, что сервер запущен.")
        except requests.exceptions.Timeout:
            self.error.emit("Превышено время ожидания ответа от Ollama")
        except Exception as e:
            self.error.emit(f"Ошибка: {str(e)}")

    def clean_response(self, text):
        """Очистка ответа от лишних символов"""
        # Убираем повторяющиеся фразы
        phrases_to_remove = [
            "Конечно!",
            "Вот информация:",
            "Лекарственный препарат",
            "Краткая информация:"
        ]

        for phrase in phrases_to_remove:
            text = text.replace(phrase, "")

        # Ограничиваем длину
        if len(text) > 400:
            text = text[:400] + "..."

        return text.strip()


class MedicineInfoDialogPro(QDialog):
    def __init__(self, medicine_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f" {medicine_name}")
        self.setGeometry(400, 300, 650, 500)
        self.medicine_name = medicine_name

        layout = QVBoxLayout()
        self.setLayout(layout)

        # Заголовок
        title_label = QLabel(f"<h2> {medicine_name}</h2>")
        title_label.setStyleSheet("color: #2c3e50; margin: 10px;")
        layout.addWidget(title_label)

        # Статус
        self.status_label = QLabel("Запрашиваем информацию...")
        self.status_label.setStyleSheet("color: #7f8c8d; padding: 5px;")
        layout.addWidget(self.status_label)

        # Текстовая область
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        font = QFont("Arial", 10)
        self.text_edit.setFont(font)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        layout.addWidget(self.text_edit)

        # Кнопки
        button_layout = QHBoxLayout()
        self.retry_btn = QPushButton("Обновить")
        self.retry_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.retry_btn.clicked.connect(self.start_request)

        close_btn = QPushButton("Закрыть")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        close_btn.clicked.connect(self.close)

        button_layout.addWidget(self.retry_btn)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

        self.start_request()

    def start_request(self):
        self.status_label.setText("Запрашиваем информацию у AI...")
        self.text_edit.setPlainText("")
        self.retry_btn.setEnabled(False)

        # Используем уже готовый поток из проекта
        self.thread = FastOllamaMedicineThread(self.medicine_name)
        self.thread.finished.connect(self.on_info_received)
        self.thread.error.connect(self.on_error)
        self.thread.start()

    def on_info_received(self, info):
        self.text_edit.setPlainText(info)
        self.status_label.setText("Информация получена")
        self.retry_btn.setEnabled(True)

    def on_error(self, error_msg):
        self.text_edit.setPlainText(f"{error_msg}\n\n"
                                    "Попробуйте:\n"
                                    "• Проверить Ollama\n"
                                    "• Перезапустить сервер\n"
                                    "• Попробовать позже")
        self.status_label.setText("Ошибка")
        self.retry_btn.setEnabled(True)


def main():
    app = QApplication(sys.argv)

    # Splash
    splash = QDialog()
    splash.setWindowTitle("Инициализация")
    splash.setGeometry(300, 300, 400, 150)
    layout = QVBoxLayout()
    status_label = QLabel("Подготовка базы данных...")
    layout.addWidget(status_label)
    splash.setLayout(layout)
    splash.show()
    QApplication.processEvents()

    # Параметры подключения
    connection_params = {
        'dbname': 'postgres',
        'user': 'postgres',
        'password': 'akiba1212',
        'host': 'localhost',
        'port': 5432
    }

    # Поток инициализации базы
    init_thread = DatabaseInitializerThread(connection_params)

    def on_progress(msg):
        status_label.setText(msg)
        QApplication.processEvents()

    def on_finished(success):
        splash.close()
        if not success:
            QMessageBox.critical(None, "Ошибка", "Не удалось инициализировать базу")
            app.quit()
            return

        db_manager = DatabaseManager()
        if not db_manager.connect('pharmacydb'):
            QMessageBox.critical(None, "Ошибка", "Не удалось подключиться к базе pharmacydb")
            app.quit()
            return

        login_dialog = LoginDialog(db_manager)
        if login_dialog.exec() == QDialog.DialogCode.Accepted:
            main_window = PharmacyMainWindow(db_manager, login_dialog.user_role)
            main_window.show()
            app.main_window = main_window
        else:
            db_manager.close()
            app.quit()

    # Инициализация звуков
    sound_manager.load_sound("click", load_ui_from_resource("click.wav"))

    init_thread.progress.connect(on_progress)
    init_thread.finished.connect(on_finished)
    init_thread.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()