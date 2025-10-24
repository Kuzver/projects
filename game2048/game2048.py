import sys
import random
import numpy as np
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QGridLayout, QPushButton, QMessageBox, QVBoxLayout
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QKeyEvent, QFont
import functools

import os
import sqlite3
import appdirs
import logging


class GameCell(QLabel):
    """
    Представляет собой отдельную ячейку в сетке игры 2048. Наследуется от QLabel для отображения значения ячейки.
    """
    def __init__(self, value=0, parent=None):
        """
        Инициализирует игровую ячейку необязательным начальным значением.

 Args:
 value (int): Начальное значение ячейки (по умолчанию равно 0).
 parent (QWidget): Родительский виджет (необязательно).
        """
        super().__init__(parent)  # Call the QLabel constructor
        self.value = value
        self.setFixedSize(QSize(100, 100)) #Sets the fixed size of the cell.
        self.setAlignment(Qt.AlignmentFlag.AlignCenter) # Aligns text to the center of the cell.
        self.setStyleSheet(self.get_style()) # Applies initial styling based on the value.
        self.setFont(QFont("Arial", 28)) # Sets the font of the text within the cell.


    def set_value(self, value):
        """
        Обновляет значение ячейки и перерисовывает его.

 Аргументы:
 значение (int): новое значение для ячейки.
        """
        self.value = value
        self.setText(str(value) if value else "") # Sets text to the value if it's not 0, otherwise sets it to an empty string.
        self.setStyleSheet(self.get_style()) #Updates the styling based on the new value.


    def get_style(self):
        """
        Возвращает строку стиля CSS для ячейки на основе ее значения.

 Возвращается:
 str: Строка в стиле CSS.
        """
        if self.value == 0:
            return "background-color: #ccc; border: 1px solid #999;" #Style for empty cells.
        color = self.get_color(self.value) #Gets the background color based on the value.
        return f"background-color: {color}; border: 1px solid #999; color: white;" #Style for cells with values.


    def get_color(self, value):
        """
        Возвращает цвет фона для ячейки на основе ее значения.

 Аргументы:
 значение (int): значение ячейки.

 Возвращается:
 str: Цветовая строка CSS.
        """
        colors = {2: "#eee4da", 4: "#ede0c8", 8: "#f2b179", 16: "#f59563", 32: "#f67c5f", 64: "#f65e3b", 128: "#edcf72", 256: "#edcc61", 512: "#edc850", 1024: "#edc53f", 2048: "#edc22e"}
        return colors.get(value, "#3c3a32")

class DifficultySelectionWindow(QWidget):
    """
    Окно, позволяющее пользователю выбрать сложность (условие победы) игры 2048.
 Отображает последний результат и рекордное количество очков.
    """
    def __init__(self, game_window):
        """
        Инициализирует окно выбора сложности.

 Аргументы:
 game_window (Игровое окно): Ссылка на главное игровое окно.

        """
        super().__init__()
        self.game_window = game_window
        self.setWindowTitle("Select Difficulty")
        layout = QVBoxLayout()
        layout.setSpacing(20)  # Add spacing between widgets
        self.setLayout(layout)
        self.setMinimumSize(400, 300)  # Adjust size if needed
        self.setStyleSheet("background-color: #f0f0f0;")  # Set background color
        self.high_score = self.load_high_score() #Loads high score from database on initialization.

        # Close button
        close_button = QPushButton("X")
        close_button.setFixedSize(20, 20)  # Small size
        close_button.setStyleSheet("background-color: red; color: white; border: none;")
        close_button.clicked.connect(self.close)  # Closes the window
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

        #Labels for last score and high score.
        self.last_score_label = QLabel(f"Last Score: {self.game_window.score}")
        self.last_score_label.setStyleSheet("font-size: 16px;")
        self.high_score_label = QLabel(f"High Score: {self.high_score}")
        self.high_score_label.setStyleSheet("font-size: 16px;")
        layout.addWidget(self.last_score_label)
        layout.addWidget(self.high_score_label)

        #Difficulty buttons
        button_styles = {
            2048: "background-color: #4CAF50; color: white; padding: 10px; font-size: 16px;",
            256: "background-color: #FF9800; color: white; padding: 10px; font-size: 16px;",
            512: "background-color: #2196F3; color: white; padding: 10px; font-size: 16px;",
            1024: "background-color: #9C27B0; color: white; padding: 10px; font-size: 16px;",
        }
        for difficulty, style in button_styles.items():
            button = QPushButton(str(difficulty))
            button.setStyleSheet(style)
            button.clicked.connect(functools.partial(self.select_difficulty, difficulty))
            layout.addWidget(button)
        self.show()

    def select_difficulty(self, difficulty):
        """
        Управляет выбором уровня сложности. Сбрасывает счет в игре, устанавливает условие выигрыша,
закрывает окно выбора сложности и отображает главное окно игры.

 Аргументы:
 сложность (int): выбранный уровень сложности (условие выигрыша).
        """
        self.game_window.score = 0
        self.game_window.win_condition = difficulty
        self.close()
        self.game_window.show()

    def load_high_score(self):
        """Загружает высокий балл из базы данных."""
        return load_high_score()

    def save_high_score(self, score):
        """Сохраняет высокий балл в базе данных."""
        save_high_score(score)

    def update_scores(self, score):
        """Обновляет отображаемый последний балл и высокий балл."""
        self.last_score_label.setText(f"Last Score: {score}")
        if score > self.high_score:
            self.high_score = score
            self.save_high_score(score)
        self.high_score_label.setText(f"High Score: {self.high_score}")


def initialize_database():
    """Инициализирует базу данных с высокими баллами."""
    user_data_dir = appdirs.user_data_dir("game2048", "YourCompanyName")
    db_path = os.path.join(user_data_dir, "high_scores.db")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS high_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                score INTEGER
            )
        ''')
        conn.commit()
        conn.close()
        logging.info(f"Database initialized at: {db_path}")
    except sqlite3.Error as e:
        logging.exception(f"Error initializing database: {e}")
def save_high_score(score):
    """Сохраняет высокий балл в базе данных."""
    try:
        user_data_dir = appdirs.user_data_dir("game2048", "YourCompanyName")
        db_path = os.path.join(user_data_dir, "high_scores.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO high_scores (score) VALUES (?)", (int(score),))
        conn.commit()
        conn.close()
        logging.info(f"High score saved: {score}")
    except (sqlite3.Error, ValueError) as e:
        logging.exception(f"Error saving high score: {e}")


def load_high_score():
    """Загружает высокий балл из базы данных."""
    try:
        user_data_dir = appdirs.user_data_dir("game2048", "YourCompanyName")
        db_path = os.path.join(user_data_dir, "high_scores.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT score FROM high_scores LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0  # Return 0 if no entry
    except (sqlite3.Error, ValueError) as e:
        logging.exception(f"Error loading high score: {e}")
        return 0
class Game2048(QWidget):
    """
    Главное окно игры 2048. Управляет игровой сеткой, обновляет ее и обрабатывает вводимые пользователем данные.
    """
    def __init__(self):
        super().__init__()
        self.size = 4
        self.grid = np.zeros((self.size, self.size), dtype=int)
        self.cells = [[GameCell() for _ in range(self.size)] for _ in range(self.size)]
        self.layout = QGridLayout()
        self.setLayout(self.layout)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.win_condition = 2048  # Default win condition
        self.hide()  # Initially hidden
        self.score = 0
        self.score_label = QLabel(f"Score: {self.score}")
        self.score_label.setFont(QFont("Arial", 16))
        self.layout.addWidget(self.score_label, 0, self.size)
        self.game_over = False
        self.init_grid()
        self.update_board()  # Initialize the board
        self.setStyleSheet("background-color: #f0f0f0;")

        self.close_button = QPushButton("Закрыть")
        self.close_button.setFixedSize(70, 30)
        self.close_button.setStyleSheet("background-color: pink; color: black;")
        self.close_button.clicked.connect(self.return_to_selection)
        self.layout.addWidget(self.close_button, self.size, 0, 1, 1)


    def return_to_selection(self):
        """Возвращается к окну выбора сложности и перезапускает игру."""
        global selection_window
        self.new_game()  # Resets the game
        selection_window.show()
        self.hide()


    def init_grid(self):
        """Инициализирует расположение сетки."""
        for i in range(self.size):
            for j in range(self.size):
                self.layout.addWidget(self.cells[i][j], i, j)


    def update_board(self):
        """Обновляет отображение игрового поля в соответствии с текущей сеткой."""
        for i in range(self.size):
            for j in range(self.size):
                self.cells[i][j].set_value(self.grid[i][j])

    def set_difficulty(self, difficulty):
        """Устанавливает условие выигрыша в игре и запускает новую игру."""
        self.win_condition = difficulty
        self.new_game()
        self.show()

    def new_game(self):
        """Начните новую игру, очистив сетку, сбросив счет и добавив начальные плитки."""
        self.grid.fill(0)
        self.score = 0
        self.score_label.setText(f"Score: {self.score}")
        self.update_board()
        self.add_random_tile()
        self.add_random_tile()
        self.game_over = False #Reset game over status

    def add_random_tile(self):
        """Добавляет случайные 2 или 4 плитки в пустую ячейку сетки."""
        empty_cells = np.where(self.grid == 0)
        if empty_cells[0].size:
            row, col = random.choice(list(zip(empty_cells[0], empty_cells[1])))
            self.grid[row, col] = 2 if random.random() < 0.9 else 4
            self.update_board()

    def move_tiles(self, direction):
        """
        Выполняет перемещение в указанном направлении.

 Аргументы:
 направление (str): направление перемещения ("вверх", "вниз", "влево" или "вправо").
        """
        try:
            self.grid = self.move_tiles_helper(self.grid, direction)
            self.update_board()
            if self.check_win():
                self.win_dialog()
            elif self.check_lose():
                self.lose_dialog()
            else:
                self.add_random_tile()
        except Exception as e:
            print(f"Error during move: {e}")

    def move_tiles_helper(self, grid, direction):
        """
        Вспомогательная функция для перемещения и объединения плиток в заданном направлении.

 Аргументы:
 сетка (numpy.ndarray): Текущая игровая сетка.
 направление (str): направление перемещения ("вверх", "вниз", "влево" или "вправо").

 Возвращается:
 numpy.ndarray: Обновленная игровая сетка.
        """
        new_grid = np.zeros_like(grid, dtype=int)  # Ensure int dtype
        score_increase = 0

        if direction == "up":
            for col in range(self.size):
                values = [val for val in grid[:, col] if val != 0]
                merged = [False] * len(values)
                row = 0
                for i, val in enumerate(values):
                    if i > 0 and values[i - 1] == val and not merged[i - 1]:
                        new_grid[row - 1, col] = val * 2
                        score_increase += val * 2
                        merged[i] = True  # Correct index for merged
                    else:
                        new_grid[row, col] = val
                    row += 1

        elif direction == "down":
            for col in range(self.size):
                values = [val for val in grid[:, col][::-1] if val != 0]
                merged = [False] * len(values)
                row = self.size - 1
                for i, val in enumerate(values):
                    if i > 0 and values[i - 1] == val and not merged[i - 1]:
                        new_grid[row +1, col] = val * 2 # Corrected index
                        score_increase += val * 2
                        merged[i] = True # Correct index for merged
                    else:
                        new_grid[row, col] = val
                    row -= 1

        elif direction == "left":
            for row in range(self.size):
                values = [val for val in grid[row, :] if val != 0]
                merged = [False] * len(values)
                col = 0
                for i, val in enumerate(values):
                    if i > 0 and values[i - 1] == val and not merged[i - 1]:
                        new_grid[row, col - 1] = val * 2 # Corrected index
                        score_increase += val * 2
                        merged[i] = True # Correct index for merged

                    else:
                        new_grid[row, col] = val
                    col += 1

        elif direction == "right":
            for row in range(self.size):
                values = [val for val in grid[row, :][::-1] if val != 0]
                merged = [False] * len(values)
                col = self.size - 1
                for i, val in enumerate(values):
                    if i > 0 and values[i - 1] == val and not merged[i - 1]:
                        new_grid[row, col + 1] = val * 2 # Corrected index
                        score_increase += val * 2
                        merged[i] = True # Correct index for merged

                    else:
                        new_grid[row, col] = val
                    col -= 1
        self.score += score_increase
        self.score_label.setText(f"Score: {self.score}")
        return new_grid

    def create_grid(self):
        """Создает новую пустую игровую сетку."""
        return np.array([[0] * self.size for _ in range(self.size)])

    def keyPressEvent(self, event: QKeyEvent):
        """Управляет нажатиями клавиш для управления ходом игры."""
        key = event.key()
        modifiers = event.modifiers()

        if modifiers:
            return

        key = event.text().lower()
        if key in ('w', 'ц'):
            self.move_tiles("up")
        elif key in ('s', 'ы'):
            self.move_tiles("down")
        elif key in ('a', 'ф'):
            self.move_tiles("left")
        elif key in ('d', 'в'):
            self.move_tiles("right")

    def check_win(self):
        """Проверяет, выиграл ли игрок игру."""
        return np.any(self.grid == self.win_condition)  # Efficient NumPy check

    def win_dialog(self):
        """Отображает диалоговое окно выигрыша, обновляет рекорды и перезапускает игру."""
        self.game_over = True
        QMessageBox.information(self, "Поздравляю!", f"Победа!")
        global selection_window
        selection_window.update_scores(self.score)
        selection_window.show()
        self.new_game()
        self.hide()

    def check_lose(self):
        """Проверяет, не проиграл ли игрок партию (больше ходов быть не может)."""

        # Check for empty cells
        if np.any(self.grid == 0):
            return False

        # Check for adjacent cells with the same value in all directions
        for i in range(self.size):
            for j in range(self.size):
                if i > 0 and self.grid[i][j] == self.grid[i - 1][j]:
                    return False
                if i < self.size - 1 and self.grid[i][j] == self.grid[i + 1][j]:
                    return False
                if j > 0 and self.grid[i][j] == self.grid[i][j - 1]:
                    return False
                if j < self.size - 1 and self.grid[i][j] == self.grid[i][j + 1]:
                    return False
        return True

    def lose_dialog(self):
        """Отображает диалоговое окно проигрыша, обновляет рекорды и перезапускает игру."""
        self.game_over = True
        QMessageBox.information(self, "Игра окончена!", "Вы проиграли!")
        global selection_window
        selection_window.update_scores(self.score)
        selection_window.show()
        self.new_game()
        self.hide()


if __name__ == "__main__":
    initialize_database()
    app = QApplication(sys.argv)
    icon = QIcon('2048')  # This line is changed to include setting the icon
    app.setWindowIcon(icon)
    game_window = Game2048() # Create game window FIRST
    selection_window = DifficultySelectionWindow(game_window)
    sys.exit(app.exec())