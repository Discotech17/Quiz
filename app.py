from flask import Flask, render_template, redirect, url_for, request, session
from bs4 import BeautifulSoup
from PIL import Image
from database import fetch_all_questions, insert_question, update_question_in_db, delete_question, insert_quiz_history, fetch_quiz_history, init_db
from datetime import datetime
import requests
import re
import pytesseract
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

def format_question_text(question_text):
    # Replace newline characters with <br> for proper HTML rendering
    return question_text.replace('\n', '<br>')

def row_to_dict(row):
    """Helper function to convert sqlite3.Row object to a dictionary."""
    return {key: row[key] for key in row.keys()}


# Home route
@app.route('/')
async def index():
    return render_template('index.html')

# Start quiz route
@app.route('/start_quiz')
async def start_quiz():
    questions = fetch_all_questions()
    formatted_questions = []

    for question in questions:
        # Convert each row to a dictionary
        question_dict = row_to_dict(question)
        # Format the question text with line breaks
        question_dict['question'] = format_question_text(question_dict['question'])
        # Append to formatted list
        formatted_questions.append(question_dict)

    return render_template('quiz.html', questions=formatted_questions)

# Submit quiz route
@app.route('/submit_quiz', methods=['POST'])
async def submit_quiz():
    user_answers = request.form.to_dict(flat=False)  # Use flat=False to handle multiple answers
    correct_answers = {}
    selected_answers = {}
    total_correct = 0

    questions = fetch_all_questions()

    for question in questions:
        user_answer = user_answers.get(f'answer_{question["id"]}')
        correct_answer = question['correct_answer']  # No normalization, using the correct answer directly

        if isinstance(user_answer, list):  # Handle multi-select answers
            selected_answers[question["id"]] = ", ".join(user_answer)  # Combine selected multi-select answers into a string
            combined_user_answer = ", ".join(user_answer)  # Combine user answers as a single string
            if combined_user_answer == correct_answer:  # Direct comparison with the correct answer string
                total_correct += 1
                correct_answers[question['id']] = 'correct'
            else:
                correct_answers[question['id']] = 'wrong'
        else:
            selected_answers[question["id"]] = user_answer  # Store the selected single answer
            if user_answer == correct_answer:  # Direct string comparison for single select
                total_correct += 1
                correct_answers[question['id']] = 'correct'
            else:
                correct_answers[question['id']] = 'wrong'

    insert_quiz_history(total_correct, len(questions))

    return render_template('review.html', correct_answers=correct_answers, selected_answers=selected_answers, questions=questions)

# Manage questions route
@app.route('/manage_questions')
async def manage_questions():
    questions = fetch_all_questions()
    return render_template('manage_questions.html', questions=questions)

# Add question route
@app.route('/add_question')
async def add_question():
    return render_template('add_question.html')

# Add questions from URL route
@app.route('/add_questions_from_url')
async def add_questions_from_url():
    return render_template('add_questions_from_url.html')

# Process the URL to extract questions
@app.route('/process_url', methods=['POST'])
async def process_url():
    url = request.form['url']

    # Make a request to the URL
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an error for bad responses (4xx, 5xx)
        
        # Parse the HTML content using BeautifulSoup
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract questions and choices
        questions = []
        for card in soup.find_all('div', class_='card'):
            question_text = card.find('div', class_='question_text').get_text(strip=True)
            
            # Get the choices from the "choices-list" ul
            choices = [choice.get_text(strip=True) for choice in card.find('ul', class_='choices-list').find_all('li')]
            
            if len(choices) == 4:  # Ensure there are exactly 4 choices
                questions.append({
                    'question': question_text,
                    'choices': choices
                })

        if not questions:
            return "No valid questions found from the provided URL", 400

        return render_template('questions_from_url.html', questions=questions)
    
    except requests.exceptions.RequestException as e:
        return f"Error fetching content from the URL: {str(e)}", 500

# Save the questions extracted from the URL
@app.route('/save_questions_from_url', methods=['POST'])
async def save_questions_from_url():
    # Handle saving the fetched questions with user-provided correct answers
    question_data = request.form.to_dict()

    # Calculate the number of questions
    num_questions = len(question_data) // 6  # Adjust this to match the form field structure
    
    # Iterate through the questions and save them
    for i in range(1, num_questions + 1):
        question = question_data.get(f'question_{i}')
        correct_answer = question_data.get(f'correct_answer_{i}')
        choices = [question_data.get(f'choice_{i}_{j}') for j in range(1, 5)]
        multiple_selection = f'multiple_selection_{i}' in question_data  # Check if multiple selection is enabled

        if question and correct_answer and all(choices):
            insert_question(question, correct_answer, choices, multiple_selection)

    return redirect(url_for('manage_questions'))

# Add questions through screenshot route
@app.route('/add_questions_from_image')
async def add_questions_from_image():
    return render_template('add_questions_from_image.html')

# Process the uploaded screenshot and extract text
@app.route('/process_image', methods=['POST'])
async def process_image():
    if 'screenshot' not in request.files:
        return "No file uploaded", 400
    
    file = request.files['screenshot']
    if file.filename == '':
        return "No selected file", 400

    # Save the uploaded file
    file_path = os.path.join('uploads', file.filename)
    file.save(file_path)

    try:
        image = Image.open(file_path)
        extracted_text = pytesseract.image_to_string(image)

        print("Extracted Text:\n", extracted_text)  # Log the raw extracted text

        questions = []

        # Split the text into blocks where each block starts with "Question X (Single Topic)"
        question_blocks = re.split(r'(Question \d+ \( Single Topic \))', extracted_text)

        # Process each question block
        for i in range(1, len(question_blocks), 2):  # Iterate over every second block (since split keeps the delimiter)
            question_title = question_blocks[i].strip()  # The "Question X (Single Topic)" part

            # Clean up the question title by removing any trailing unwanted characters like 'x'
            question_title = re.sub(r'\s*x\s*$', '', question_title)

            question_body = question_blocks[i + 1].strip()  # The actual question content

            # Extract question content before choices (anything before A.)
            question_content_match = re.search(r'^(.+?)(?=A\.)', question_body, re.DOTALL)
            question_content = question_content_match.group(1).strip() if question_content_match else ""

            # Extract the choices (A., B., C., D.) and remove the first 3 characters (A., B., etc.)
            choices_match = re.findall(r'([A-D]\.\s?.+)', question_body)
            choices = [choice[2:].strip() for choice in choices_match]  # Remove the first 2 characters ("A.")

            # Extract the correct answer
            answer_match = re.search(r'Answer :\s?(.+)', question_body)
            correct_answer_letters = answer_match.group(1).replace(" ", "").split(",") if answer_match else []
            correct_answer_list = []
            for letter in correct_answer_letters:
                if letter == "A":
                    correct_answer_list.append(choices[0])
                elif letter == "B":
                    correct_answer_list.append(choices[1])
                elif letter == "C":
                    correct_answer_list.append(choices[2])
                elif letter == "D":
                    correct_answer_list.append(choices[3])

            correct_answer = ", ".join(correct_answer_list)

            # Log what we captured for debugging purposes
            print(f"Question Title: {question_title}")
            print(f"Question Content: {question_content}")
            print(f"Choices: {choices}")
            print(f"Correct Answer: {correct_answer}")

            # Add the question to the list
            if question_content and len(choices) == 4 and correct_answer:
                questions.append({
                    'title': question_title,
                    'question': question_content,
                    'choices': choices,
                    'correct_answer': correct_answer
                })

        os.remove(file_path)  # Clean up by removing the saved file

        print(f"All processed questions: {questions}")  # Log the final questions list
        return render_template('questions_from_url.html', questions=questions)

    except IndexError as e:
        print(f"Error processing image: {str(e)}")  # Log the error
        return "Error processing image: Index out of range", 500
    
    except Exception as e:
        return f"Error processing image: {str(e)}", 500

# Save new question route
@app.route('/save_question', methods=['POST'])
async def save_question():
    question = request.form['question']
    correct_answer = request.form['correct_answer']
    choices = [request.form[f'choice{i}'] for i in range(1, 5)]

    insert_question(question, correct_answer, choices)
    return redirect(url_for('manage_questions'))

# Edit question route
@app.route('/edit_question/<int:question_id>')
async def edit_question(question_id):
    questions = fetch_all_questions()
    question = next((q for q in questions if q['id'] == question_id), None)
    return render_template('edit_question.html', question=question)

# Update question route
@app.route('/update_question/<int:question_id>', methods=['POST'])
async def update_question(question_id):
    question = request.form['question']
    correct_answer = request.form['correct_answer']
    choices = [request.form[f'choice{i}'] for i in range(1, 5)]
    multiple_selection = 'multiple_selection' in request.form  # Check if the checkbox was selected

    # Call the renamed update function
    update_question_in_db(question_id, question, correct_answer, choices[0], choices[1], choices[2], choices[3], multiple_selection)
    
    return redirect(url_for('manage_questions'))

# Delete question route
@app.route('/delete_question/<int:question_id>', methods=['POST'])
async def delete_question_route(question_id):
    delete_question(question_id)
    return redirect(url_for('manage_questions'))

# Quiz history route
@app.route('/history')
async def history():
    history = fetch_quiz_history()
    return render_template('history.html', history=history)

# New route to generate the report
@app.route('/generate_report')
def generate_report():
    history = fetch_quiz_history()

    # Extract data for the report (dates and scores)
    dates = [entry['date_taken'] for entry in history]
    scores = [(entry['correct_answers'] / entry['total_questions']) * 100 for entry in history]

    # Format the dates to remove seconds (use strftime)
    formatted_dates = [datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M') for date in dates]

    # Calculate the maximum score to add a buffer above the highest value
    max_score = max(scores) if scores else 100  # Ensure it doesn't fail if scores list is empty
    y_max = min(max_score + 10, 110)  # Add a buffer of 10% but don't exceed 100%

    # Pass the formatted dates and scores to the template, along with the max y value
    return render_template('report.html', quizDates=formatted_dates, quizPercentages=scores, y_max=y_max)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)