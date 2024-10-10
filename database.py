import sqlite3

def get_db_connection():
    conn = sqlite3.connect('quiz.db')
    conn.row_factory = sqlite3.Row
    return conn

# Initialize the database and create the necessary tables
def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            choice1 TEXT NOT NULL,
            choice2 TEXT NOT NULL,
            choice3 TEXT NOT NULL,
            choice4 TEXT NOT NULL,
            multiple_selection BOOLEAN DEFAULT FALSE
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS quiz_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            correct_answers INTEGER NOT NULL,
            total_questions INTEGER NOT NULL,
            date_taken DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# Fetch all questions
def fetch_all_questions():
    conn = get_db_connection()
    questions = conn.execute('SELECT * FROM questions').fetchall()
    conn.close()
    return questions

# Insert a new question
def insert_question(question, correct_answer, choices, multiple_selection=False):
    conn = get_db_connection()
    
    # Check if the question already exists in the database
    existing_question = conn.execute('SELECT * FROM questions WHERE question = ?', (question,)).fetchone()
    
    if existing_question:
        print(f"Question '{question}' already exists. Skipping insertion.")
    else:
        # Insert only if the question does not exist
        conn.execute('''
            INSERT INTO questions (question, correct_answer, choice1, choice2, choice3, choice4, multiple_selection)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (question, correct_answer, choices[0], choices[1], choices[2], choices[3], multiple_selection))
        conn.commit()

    conn.close()

# Update a question
def update_question_in_db(question_id, question, correct_answer, choice1, choice2, choice3, choice4, multiple_selection):
    conn = sqlite3.connect('quiz.db')
    cursor = conn.cursor()

    # Update the question, choices, correct answer, and the multiple_selection flag
    cursor.execute('''
        UPDATE questions
        SET question = ?, correct_answer = ?, choice1 = ?, choice2 = ?, choice3 = ?, choice4 = ?, multiple_selection = ?
        WHERE id = ?
    ''', (question, correct_answer, choice1, choice2, choice3, choice4, multiple_selection, question_id))

    conn.commit()
    conn.close()

# Delete a question
def delete_question(question_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM questions WHERE id = ?', (question_id,))
    conn.commit()
    conn.close()

# Insert quiz history
def insert_quiz_history(correct_answers, total_questions):
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO quiz_history (correct_answers, total_questions, date_taken)
        VALUES (?, ?, datetime('now'))
    ''', (correct_answers, total_questions))
    conn.commit()
    conn.close()

# Fetch quiz history
def fetch_quiz_history():
    conn = get_db_connection()
    history = conn.execute('SELECT * FROM quiz_history ORDER BY date_taken DESC').fetchall()
    conn.close()
    return history