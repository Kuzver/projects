import unittest
import numpy as np
from game2048 import *

def test_game_initialization():
    app = QApplication(sys.argv)
    game = Game2048()
    assert game.size == 4
    assert game.grid.shape == (4, 4)
    assert len(game.cells) == 4
    assert len(game.cells[0]) == 4
    app.quit()

def test_initial_tiles():
    app = QApplication(sys.argv)
    game = Game2048()
    game.new_game()
    non_zero = np.count_nonzero(game.grid)
    assert non_zero == 2
    app.quit()

def test_move_up_no_merge():
    app = QApplication(sys.argv)
    game = Game2048()
    game.grid = np.array([
        [0, 0, 0, 0],
        [2, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0]
    ])
    new_grid = game.move_tiles_helper(game.grid, "up")
    assert new_grid[0][0] == 2
    app.quit()

def test_move_up_with_merge():
    app = QApplication(sys.argv)
    game = Game2048()
    game.grid = np.array([
        [2, 0, 0, 0],
        [2, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0]
    ])
    new_grid = game.move_tiles_helper(game.grid, "up")
    assert new_grid[0][0] == 4
    app.quit()

def test_move_down():
    app = QApplication(sys.argv)
    game = Game2048()
    game.grid = np.array([
        [0, 0, 0, 0],
        [2, 0, 0, 0],
        [0, 0, 0, 0],
        [2, 0, 0, 0]
    ])
    new_grid = game.move_tiles_helper(game.grid, "down")
    assert new_grid[3][0] == 4
    app.quit()

def test_move_left():
    app = QApplication(sys.argv)
    game = Game2048()
    game.grid = np.array([
        [0, 0, 2, 2],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0]
    ])
    new_grid = game.move_tiles_helper(game.grid, "left")
    assert new_grid[0][0] == 4
    app.quit()

def test_move_right():
    app = QApplication(sys.argv)
    game = Game2048()
    game.grid = np.array([
        [2, 2, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0]
    ])
    new_grid = game.move_tiles_helper(game.grid, "right")
    assert new_grid[0][3] == 4
    app.quit()

def test_score_calculation():
    app = QApplication(sys.argv)
    game = Game2048()
    game.grid = np.array([
        [2, 2, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0]
    ])
    game.move_tiles_helper(game.grid, "right")
    assert game.score == 4
    app.quit()

def test_win_condition():
    app = QApplication(sys.argv)
    game = Game2048()
    game.win_condition = 2048
    game.grid[0][0] = 2048
    assert game.check_win() == True
    app.quit()

def test_lose_condition():
    app = QApplication(sys.argv)
    game = Game2048()
    game.grid = np.array([
        [2, 4, 2, 4],
        [4, 2, 4, 2],
        [2, 4, 2, 4],
        [4, 2, 4, 2]
    ])
    assert game.check_lose() == True
    app.quit()


def test_key_press():
    app = QApplication(sys.argv)
    game = Game2048()

    # Создаем mock-событие
    class MockEvent:
        def __init__(self, key):
            self.key = key
            self.text = chr(key) if key <= 255 else ''

    # Проверяем обработку клавиш
    game.keyPressEvent(MockEvent(ord('W')))
    game.keyPressEvent(MockEvent(ord('S')))
    game.keyPressEvent(MockEvent(ord('A')))
    game.keyPressEvent(MockEvent(ord('D')))

    app.quit()

def test_new_game_reset():
    app = QApplication(sys.argv)
    game = Game2048()
    game.grid.fill(2)
    game.score = 100
    game.new_game()
    assert game.score == 0
    assert np.count_nonzero(game.grid) == 2
    app.quit()

def test_cell_styles():
    app = QApplication(sys.argv)
    cell = GameCell(2)
    assert "background-color: #eee4da" in cell.get_style()
    cell.set_value(0)
    assert "background-color: #ccc" in cell.get_style()
    app.quit()

def test_difficulty_selection():
    app = QApplication(sys.argv)
    game = Game2048()
    selection = DifficultySelectionWindow(game)
    selection.select_difficulty(256)
    assert game.win_condition == 256
    app.quit()

def test_high_score_storage():
    save_high_score(1000)
    assert load_high_score() == 1000
    save_high_score(0)  # Очищаем тестовые данные

def test_random_tile_addition():
    app = QApplication(sys.argv)
    game = Game2048()
    game.grid.fill(0)
    game.add_random_tile()
    assert np.count_nonzero(game.grid) == 1
    app.quit()

def test_board_update():
    app = QApplication(sys.argv)
    game = Game2048()
    game.grid[0][0] = 2
    game.update_board()
    assert game.cells[0][0].value == 2
    app.quit()

def test_return_to_selection():
    app = QApplication(sys.argv)
    game = Game2048()
    selection = DifficultySelectionWindow(game)
    game.return_to_selection()
    assert game.isHidden()
    assert selection.isVisible()
    app.quit()

def test_win_handling():
    app = QApplication(sys.argv)
    game = Game2048()
    game.win_condition = 8
    game.grid[0][0] = 8
    game.check_win()
    # Проверяем, что игра перешла в состояние "завершено"
    assert game.game_over == True
    app.quit()

def test_lose_handling():
    app = QApplication(sys.argv)
    game = Game2048()
    game.grid = np.array([
        [2, 4, 2, 4],
        [4, 2, 4, 2],
        [2, 4, 2, 4],
        [4, 2, 4, 2]
    ])
    game.check_lose()
    # Проверяем, что игра перешла в состояние "завершено"
    assert game.game_over == True
    app.quit()