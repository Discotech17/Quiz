import sqlite3

DB_PATH = "quiz.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create questions table if not exists
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        correct_answer TEXT NOT NULL,
        multiple_selection BOOLEAN NOT NULL DEFAULT 0
    )
    ''')

    # Create choices table if not exists
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS choices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL,
        choice_text TEXT NOT NULL,
        FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
    )
    ''')

    # Create quiz_history table if not exists
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS quiz_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_taken TEXT NOT NULL,
        correct_answers INTEGER NOT NULL,
        total_questions INTEGER NOT NULL
    )
    ''')

    conn.commit()
    conn.close()

def insert_question(question, correct_answer, choices, multiple_selection):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Insert the question into the questions table
    cursor.execute('''
    INSERT INTO questions (question, correct_answer, multiple_selection)
    VALUES (?, ?, ?)
    ''', (question, correct_answer, multiple_selection))

    question_id = cursor.lastrowid

    # Insert the choices into the choices table
    for choice in choices:
        cursor.execute('''
        INSERT INTO choices (question_id, choice_text)
        VALUES (?, ?)
        ''', (question_id, choice))

    conn.commit()
    conn.close()

def fetch_all_questions():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Fetch all questions
    cursor.execute('SELECT * FROM questions')
    questions = cursor.fetchall()

    question_list = []
    
    # Iterate over the questions and convert them to dicts to modify
    for question in questions:
        question_dict = dict(question)  # Convert to a dict to allow modifications
        
        # Fetch the corresponding choices for each question
        cursor.execute('SELECT * FROM choices WHERE question_id = ?', (question['id'],))
        choices = cursor.fetchall()
        
        # Add the choices to the question dict
        question_dict['choices'] = [choice['choice_text'] for choice in choices]

        # Add the updated question to the list
        question_list.append(question_dict)

    conn.close()
    return question_list

def update_question_in_db(question_id, question, correct_answer, choices, multiple_selection):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Update the question in the questions table
    cursor.execute('''
    UPDATE questions
    SET question = ?, correct_answer = ?, multiple_selection = ?
    WHERE id = ?
    ''', (question, correct_answer, multiple_selection, question_id))

    # Delete existing choices for the question
    cursor.execute('DELETE FROM choices WHERE question_id = ?', (question_id,))

    # Insert the updated choices
    for choice in choices:
        cursor.execute('''
        INSERT INTO choices (question_id, choice_text)
        VALUES (?, ?)
        ''', (question_id, choice))

    conn.commit()
    conn.close()

def fetch_questions_by_ids(ids):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Use placeholders for safe querying with IN clause
    query = f"SELECT * FROM questions WHERE id IN ({','.join('?' for _ in ids)})"
    cursor.execute(query, ids)
    
    questions = cursor.fetchall()
    conn.close()
    return questions

# Fetch a question by its ID
def fetch_question_by_id(question_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    question = cursor.execute('SELECT * FROM questions WHERE id = ?', (question_id,)).fetchone()
    choices = cursor.execute('SELECT * FROM choices WHERE question_id = ?', (question_id,)).fetchall()
    conn.close()
    
    return {
        'id': question['id'],
        'question': question['question'],
        'correct_answer': question['correct_answer'],
        'multiple_selection': question['multiple_selection'],
        'choices': [choice['choice_text'] for choice in choices]
    }

# Update a question in the database
def update_question_in_db(question_id, question_text, correct_answer, choices, multiple_selection):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE questions SET question = ?, correct_answer = ?, multiple_selection = ? WHERE id = ?',
                 (question_text, correct_answer, multiple_selection, question_id))

    # Delete existing choices and insert updated ones
    cursor.execute('DELETE FROM choices WHERE question_id = ?', (question_id,))
    for choice in choices:
        cursor.execute('INSERT INTO choices (question_id, choice_text) VALUES (?, ?)', (question_id, choice))

    conn.commit()
    conn.close()

def delete_question(question_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Delete the question from the questions table
    cursor.execute('DELETE FROM questions WHERE id = ?', (question_id,))

    # Choices will automatically be deleted due to the foreign key constraint
    conn.commit()
    conn.close()

def fetch_quiz_history():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Fetch quiz history data (if you have a separate history table, modify this accordingly)
    cursor.execute('SELECT * FROM quiz_history ORDER BY date_taken DESC')
    history = cursor.fetchall()

    conn.close()
    return history

def insert_quiz_history(correct_answers, total_questions):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Insert quiz history data (add your table if necessary)
    cursor.execute('''
    INSERT INTO quiz_history (date_taken, correct_answers, total_questions)
    VALUES (datetime('now'), ?, ?)
    ''', (correct_answers, total_questions))

    conn.commit()
    conn.close()