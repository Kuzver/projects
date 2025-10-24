class UserWindow(QDialog):
    def __init__(self, conn, cursor, user_role):
        super().__init__()
        self.conn = conn
        self.cursor = cursor
        self.user_role = user_role  # 👈 добавлено

        loadUi("design.ui", self)
        self.setFixedSize(self.widget.size())

        self.sport_combo = self.findChild(type(self.comboBox), "comboBox")
        self.date_edit = self.findChild(type(self.dateEdit), "dateEdit")
        self.result_button = self.findChild(type(self.pushButton), "pushButton")
        self.add_match_button = self.findChild(type(self.pushButton_2), "pushButton_2")
        self.table_view = self.findChild(type(self.tableView), "tableView")

        self.result_button.clicked.connect(self.load_match_results)
        self.add_match_button.clicked.connect(self.add_match)

        self.load_sport_types()

        self.check_permissions()  # добавим метод проверки прав


    def load_sport_types(self):
        try:
            self.cursor.execute("SELECT SportName FROM SportType;")
            sports = self.cursor.fetchall()
            self.sport_combo.clear()
            for sport in sports:
                self.sport_combo.addItem(sport[0])
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка загрузки видов спорта:\n{e}")

    def load_match_results(self):
        selected_sport = self.sport_combo.currentText()
        selected_date = self.date_edit.date().toString("yyyy-MM-dd")

        try:
            self.cursor.execute("""
                SELECT m.MatchDateTime, t1.TeamName, t2.TeamName, r1.Score, r2.Score
                FROM Match m
                JOIN Team t1 ON m.ID_Team1 = t1.ID_Team
                JOIN Team t2 ON m.ID_Team2 = t2.ID_Team
                JOIN SportType st ON m.ID_SportType = st.ID_SportType
                JOIN Result r1 ON r1.ID_Match = m.ID_Match AND r1.ID_Team = t1.ID_Team
                JOIN Result r2 ON r2.ID_Match = m.ID_Match AND r2.ID_Team = t2.ID_Team
                WHERE st.SportName = %s AND DATE(m.MatchDateTime) = %s;
            """, (selected_sport, selected_date))

            data = self.cursor.fetchall()

            model = QStandardItemModel()
            model.setHorizontalHeaderLabels(["Дата", "Команда 1", "Счёт 1", "Счёт 2", "Команда 2"])

            for row in data:
                match_date, team1, team2, score1, score2 = row
                items = [
                    QStandardItem(str(match_date)),
                    QStandardItem(team1),
                    QStandardItem(str(score1)),
                    QStandardItem(str(score2)),
                    QStandardItem(team2),
                ]
                model.appendRow(items)
            self.table_view.setModel(model)

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка загрузки результатов:\n{e}")

    def add_match(self):
        self.add_match_button = AddResult(self.conn, self.cursor)
        self.user_window.show()


class AddResult(QDialog):
    def __init__(self, conn, cursor):
        super().__init__()
        self.conn = conn
        self.cursor = cursor

        loadUi("addmatch.ui", self)  # Название твоего .ui-файла

        self.setFixedSize(self.widget.size())

        # Привязка виджетов
        self.sport_combo = self.findChild(type(self.comboBox), "comboBox")
        self.date_edit = self.findChild(type(self.dateEdit), "dateEdit")
        self.team1_line = self.findChild(type(self.lineEdit), "lineEdit")
        self.team2_line = self.findChild(type(self.lineEdit_2), "lineEdit_2")
        self.score_line = self.findChild(type(self.lineEdit_3), "lineEdit_3")
        self.add_button = self.findChild(type(self.pushButton_2), "pushButton_2")

        # Подключение кнопки
        self.add_button.clicked.connect(self.save_result)

        # Загрузка видов спорта
        self.load_sports()

    def load_sports(self):
        try:
            self.cursor.execute("SELECT SportName FROM SportType;")
            sports = self.cursor.fetchall()
            self.sport_combo.clear()
            for sport in sports:
                self.sport_combo.addItem(sport[0])
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка загрузки видов спорта:\n{e}")

    def save_result(self):
        try:
            sport_name = self.sport_combo.currentText()
            match_date = self.date_edit.date().toString("yyyy-MM-dd")
            team1_name = self.team1_line.text().strip()
            team2_name = self.team2_line.text().strip()
            score_text = self.score_line.text().strip()

            if not (team1_name and team2_name and score_text):
                QMessageBox.warning(self, "Проверка", "Пожалуйста, заполните все поля.")
                return

            scores = score_text.split()
            if len(scores) != 2 or not all(s.isdigit() for s in scores):
                QMessageBox.warning(self, "Неверный формат", "Введите счёт в формате: `1 2` (через пробел).")
                return

            score1, score2 = int(scores[0]), int(scores[1])

            # Получение ID вида спорта
            self.cursor.execute("SELECT ID_SportType FROM SportType WHERE SportName = %s;", (sport_name,))
            sport_id = self.cursor.fetchone()
            if not sport_id:
                QMessageBox.critical(self, "Ошибка", "Выбранный вид спорта не найден.")
                return
            sport_id = sport_id[0]

            # Вставка команд (если не существует, то добавляем)
            self.cursor.execute("SELECT ID_Team FROM Team WHERE TeamName = %s;", (team1_name,))
            result = self.cursor.fetchone()
            if result:
                team1_id = result[0]
            else:
                self.cursor.execute("INSERT INTO Team (TeamName) VALUES (%s) RETURNING ID_Team;", (team1_name,))
                team1_id = self.cursor.fetchone()[0]

            self.cursor.execute("SELECT ID_Team FROM Team WHERE TeamName = %s;", (team2_name,))
            result = self.cursor.fetchone()
            if result:
                team2_id = result[0]
            else:
                self.cursor.execute("INSERT INTO Team (TeamName) VALUES (%s) RETURNING ID_Team;", (team2_name,))
                team2_id = self.cursor.fetchone()[0]

            # Вставка матча
            self.cursor.execute("""
                INSERT INTO Match (MatchDateTime, Location, ID_Team1, ID_Team2, ID_SportType)
                VALUES (%s, 'Не указано', %s, %s, %s)
                RETURNING ID_Match;
            """, (match_date, team1_id, team2_id, sport_id))
            match_id = self.cursor.fetchone()[0]

            # Вставка результатов
            self.cursor.execute("""
                INSERT INTO Result (ID_Match, ID_Team, Score)
                VALUES (%s, %s, %s), (%s, %s, %s);
            """, (match_id, team1_id, score1, match_id, team2_id, score2))

            self.conn.commit()
            QMessageBox.information(self, "Успешно", "Матч и результат добавлены!")

            # Очистка полей
            self.team1_line.clear()
            self.team2_line.clear()
            self.score_line.clear()

        except Exception as e:
            self.conn.rollback()
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить результат:\n{e}")
