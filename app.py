from flask import Flask, render_template, redirect, url_for, request, session
from bs4 import BeautifulSoup
from PIL import Image, ImageEnhance
from database import fetch_all_questions, insert_question, update_question_in_db, delete_question, insert_quiz_history, fetch_quiz_history, init_db, fetch_question_by_id, fetch_questions_by_ids
from datetime import datetime
from random import sample
import pytesseract
import requests
import cv2
import numpy as np
import os
import re
import logging

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Preprocess the image for better OCR performance
def preprocess_image(image):
    logging.debug("Preprocessing the image for better OCR.")
    # Convert image to grayscale
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)

    # Apply thresholding to get a binary image (binarization)
    _, binary_image = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Denoising to remove potential noise and artifacts
    denoised_image = cv2.fastNlMeansDenoising(binary_image, None, 30, 7, 21)

    # Sharpen the image using a kernel
    kernel = np.array([[0, -1, 0], [-1, 5,-1], [0, -1, 0]])
    sharpened_image = cv2.filter2D(denoised_image, -1, kernel)

    return Image.fromarray(sharpened_image)

def extract_text(image):
    logging.debug("Running Tesseract OCR on the preprocessed image.")
    config = "--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:()[]"
    extracted_text = pytesseract.image_to_string(image, config=config)
    return extracted_text

def correct_spacing(extracted_text):
    logging.debug("Correcting spacing issues in the extracted text.")
    
    # Insert space after periods (A., B., C., etc.)
    corrected_text = re.sub(r'([A-Z])\.', r'\1. ', extracted_text)

    # Handle cases where OCR output is squashed together
    corrected_text = re.sub(r'([a-z])([A-Z])', r'\1 \2', corrected_text)
    corrected_text = re.sub(r'([A-Z][a-z])([A-Z][a-z])', r'\1 \2', corrected_text)

    # Ensure spaces around symbols like colon or parenthesis
    corrected_text = re.sub(r'([a-zA-Z0-9])([:,()])', r'\1 \2', corrected_text)
    corrected_text = re.sub(r'([:,()])([a-zA-Z0-9])', r'\1 \2', corrected_text)

    return corrected_text

def extract_questions_and_choices(text):
    """
    Extract questions, choices, and answers from the corrected text.
    Assumes:
    - Question starts with "Question X ( Single Topic )"
    - Choices are A., B., C., D., etc.
    - Answer is indicated by "Answer :"
    """
    logging.debug("Extracting questions and choices from text.")
    
    questions = []
    current_question = None
    current_choices = []
    current_answer = None
    inside_question = False
    
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()

        if not line:
            continue
        
        # Skip reference lines or 'Next Question'
        if re.match(r'Reference|Next Question', line):
            logging.debug(f"Skipping reference or 'Next Question' line: {line}")
            continue
        
        # Detect the start of a new question
        if re.match(r'Question\s?\d+\s?\( Single Topic \)', line):
            # If there's a current question, store it
            if current_question and current_choices:
                questions.append({
                    'question': current_question.strip(),
                    'choices': current_choices,
                    'answer': current_answer
                })
            # Start a new question
            current_question = ""
            current_choices = []
            current_answer = None
            inside_question = True
            logging.debug(f"New question detected: {line}")
            continue
        
        # Detect and append choices (A., B., C., D., etc.)
        match_choice = re.match(r'([A-Za-z])\.\s?(.*)', line)
        if match_choice:
            choice_label = match_choice.group(1).upper()  # A, B, C, D
            choice_text = match_choice.group(2).strip()
            current_choices.append(f"{choice_label}. {choice_text}")
            logging.debug(f"Choice detected: {choice_label}. {choice_text}")
            continue
        
        # Detect answer
        match_answer = re.match(r'Answer\s?:\s?(.*)', line)
        if match_answer:
            current_answer = match_answer.group(1).strip()
            logging.debug(f"Answer detected: {current_answer}")
            continue
        
        # Append to the current question
        if inside_question and not match_choice and not match_answer:
            current_question += " " + line
            logging.debug(f"Appending to current question: {line}")

    # Add the final question if any
    if current_question and current_choices:
        questions.append({
            'question': current_question.strip(),
            'choices': current_choices,
            'answer': current_answer
        })

    return questions

def format_questions(questions):
    formatted_output = ""
    for q in questions:
        formatted_output += f"Question: {q['question']}\n"
        for choice in q['choices']:
            formatted_output += f"{choice}\n"
        formatted_output += f"Answer: {q['answer']}\n\n"
    return formatted_output

# Correct OCR errors, such as misrecognized characters
def correct_choices(text):
    # Replace common OCR errors
    text = text.replace("©", "C").replace("8.", "D.")  # Correct common mistakes
    return text

# Format the question text with line breaks for rendering
def format_question_text(question_text):
    return question_text.replace('\n', '<br>')

# Convert database row to dictionary
def row_to_dict(row):
    return {key: row[key] for key in row.keys()}

# Home route
@app.route('/')
async def index():
    return render_template('index.html')

# Start quiz route
@app.route('/start_quiz')
async def start_quiz():
    # Fetch all questions and sample 40 at random
    all_questions = fetch_all_questions()
    selected_questions = sample(all_questions, 40)
    
    # Extract IDs of selected questions and save in session
    session['quiz_question_ids'] = [q['id'] for q in selected_questions]
    
    # Prepare questions for display
    formatted_questions = []
    for question in selected_questions:
        question_dict = row_to_dict(question)
        question_dict['question'] = format_question_text(question_dict['question'])
        formatted_questions.append(question_dict)

    return render_template('quiz.html', questions=formatted_questions)

# Submit quiz route
@app.route('/submit_quiz', methods=['POST'])
async def submit_quiz():
    user_answers = request.form.to_dict(flat=False)
    correct_answers = {}
    selected_answers = {}
    total_correct = 0
    
    # Retrieve the IDs of selected questions from the session
    question_ids = session.get('quiz_question_ids', [])
    
    # Fetch only the selected questions from the database
    questions = fetch_questions_by_ids(question_ids)  # Ensure `fetch_questions_by_ids` is defined in `database.py`

    for question in questions:
        user_answer = user_answers.get(f'answer_{question["id"]}')
        correct_answer = question['correct_answer']
        
        if isinstance(user_answer, list):  # If multiple answers
            selected_answers[question["id"]] = ", ".join(user_answer)
            combined_user_answer = ", ".join(user_answer)
            if combined_user_answer == correct_answer:
                total_correct += 1
                correct_answers[question['id']] = 'correct'
            else:
                correct_answers[question['id']] = 'wrong'
        else:
            selected_answers[question["id"]] = user_answer
            if user_answer == correct_answer:
                total_correct += 1
                correct_answers[question['id']] = 'correct'
            else:
                correct_answers[question['id']] = 'wrong'
    
    # Store quiz history
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

    try:
        response = requests.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        questions = []
        for card in soup.find_all('div', class_='card'):
            question_text = card.find('div', class_='question_text').get_text(strip=True)

            choices = [choice.get_text(strip=True) for choice in card.find('ul', class_='choices-list').find_all('li')]

            if len(choices) >= 2:  # Ensure there are at least 2 choices
                questions.append({
                    'question': question_text,
                    'choices': choices
                })

        if not questions:
            return "No valid questions found from the provided URL", 400

        return render_template('questions_from_url.html', questions=questions)

    except requests.exceptions.RequestException as e:
        return f"Error fetching content from the URL: {str(e)}", 500

# Save questions extracted from the URL
@app.route('/save_questions_from_url', methods=['POST'])
async def save_questions_from_url():
    question_data = request.form.to_dict()
    num_questions = len(question_data) // 6

    for i in range(1, num_questions + 1):
        question = question_data.get(f'question_{i}')
        correct_answer = question_data.get(f'correct_answer_{i}')
        choices = [question_data.get(f'choice_{i}_{j}') for j in range(1, 5)]
        multiple_selection = f'multiple_selection_{i}' in question_data

        if question and correct_answer and all(choices):
            insert_question(question, correct_answer, choices, multiple_selection)

    return redirect(url_for('manage_questions'))

# Add questions from image route
@app.route('/add_questions_from_image')
async def add_questions_from_image():
    return render_template('add_questions_from_image.html')

# Process uploaded screenshot and extract text
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
        # Open and preprocess the image
        image = Image.open(file_path)
        preprocessed_image = preprocess_image(image)

        # Extract text using Tesseract
        extracted_text = extract_text(preprocessed_image)

        logging.debug("Extracted Text Before Correction:\n" + extracted_text)

        # Correct missing spaces
        corrected_text = correct_spacing(extracted_text)

        logging.debug("Corrected Text:\n" + corrected_text)

        # Process the corrected text to extract questions and choices
        questions = extract_questions_and_choices(corrected_text)

        logging.debug(f"All processed questions: {questions}")

        os.remove(file_path)

        return render_template('questions_from_url.html', questions=questions)

    except Exception as e:
        logging.error(f"Error processing image: {str(e)}")
        return f"Error processing image: {str(e)}", 500

# Save new question route
@app.route('/save_question', methods=['POST'])
async def save_question():
    question = request.form['question']
    correct_answer = request.form['correct_answer']
    choices = [request.form[f'choice{i}'] for i in range(1, 5)]
    multiple_selection = request.form['multiple_selection']

    insert_question(question, correct_answer, choices)
    return redirect(url_for('manage_questions'))

# Edit question route
@app.route('/edit_question/<int:question_id>')
async def edit_question(question_id):
    question = fetch_question_by_id(question_id)  # Ensure this function fetches the question correctly
    choices = question["choices"]
    return render_template('edit_question.html', question=question, choices=choices)

# Update question route
@app.route('/update_question/<int:question_id>', methods=['POST'])
async def update_question(question_id):
    question = request.form['question']
    correct_answer = request.form['correct_answer']

    # print(f'Request:\n{request.form}')

    # Update the choices to match the form field names
    # choices = [request.form[f'choice_{i}'] for i in range(1, 7)]
    choices = []
    i = 1
    while True:
        choice_key = f'choice_{i}'
        if choice_key in request.form:
            choices.append(request.form[f'choice_{i}'])
            i += 1
        else:
            break

    multiple_selection = 'multiple_selection' in request.form  # Check if the checkbox was selected

    # Call the renamed update function
    update_question_in_db(question_id, question, correct_answer, choices, multiple_selection)
    
    return redirect(url_for('manage_questions'))

# Delete question route
@app.route('/delete_question/<int:question_id>', methods=['POST'])
async def delete_question_route(question_id):
    delete_question(question_id)
    return redirect(url_for('manage_questions'))

# Add questions from text route
@app.route('/add_questions_from_text')
async def add_questions_from_text():
    return render_template('add_questions_from_text.html')

# Process text input from the form
@app.route('/process_text', methods=['POST'])
async def process_text():
    raw_text = request.form['questionText']
    
    # Split questions based on a pattern like "Question X ( Single Topic )"
    question_blocks = re.split(r'(Question \d+ \( Single Topic \))', raw_text)
    
    questions = []
    
    for i in range(1, len(question_blocks), 2):
        question_title = question_blocks[i].strip()
        question_body = question_blocks[i + 1].strip()

        # Extract question content before choices (anything before A.)
        question_content_match = re.search(r'^(.+?)(?=A\.)', question_body, re.DOTALL)
        question_content = question_content_match.group(1).strip() if question_content_match else ""

        # Extract the choices (A., B., C., etc.)
        choices_match = re.findall(r'([A-Z]\.\s?.+)', question_body)
        choices = [choice[2:].strip() for choice in choices_match]

        # Extract the correct answer(s) (handles cases like "A", "B", or "CD")
        answer_match = re.search(r'Answer :\s?([A-Z, ]+)', question_body)
        answer_letters = answer_match.group(1).strip() if answer_match else "N/A"

        correct_answers = []
        if answer_letters != "N/A":
            # Split the answer string into individual letters (e.g., "CD" -> ['C', 'D'])
            answer_letters = re.findall(r'[A-Z]', answer_letters)

            # Map each letter to the corresponding choice text
            for answer_letter in answer_letters:
                answer_index = ord(answer_letter) - ord('A')  # Convert A, B, C, D to index 0, 1, 2, 3
                if 0 <= answer_index < len(choices):
                    correct_answers.append(choices[answer_index])

        # Append the question to the list
        if question_content and len(choices) >= 2 and correct_answers:
            questions.append({
                'question': question_content,
                'choices': choices,
                'correct_answer': ", ".join(correct_answers),  # Store as a comma-separated string
                'index': i // 2 + 1  # Add index to each question object
            })

    # Render the review page for questions from text
    return render_template('questions_from_text.html', questions=questions)

@app.route('/save_questions_from_text', methods=['POST'])
async def save_questions_from_text():
    question_data = request.form.to_dict(flat=False)

    num_questions = len([key for key in question_data.keys() if key.startswith('question_')])

    for i in range(1, num_questions + 1):
        question = question_data.get(f'question_{i}')[0]
        correct_answer = question_data.get(f'correct_answer_{i}')[0]
        
        # Extract choices
        choices = []
        j = 1
        while True:
            choice_key = f'choice_{i}_{j}'
            if choice_key in question_data:
                choices.append(question_data.get(choice_key)[0])
            else:
                break
        # for j in range(1, 7):  # Assuming a fixed number of 4 choices
        #     choice_key = f'choice_{i}_{j}'
        #     if choice_key in question_data:
        #         choices.append(question_data.get(choice_key)[0])

        # Multiple selection check (optional)
        multiple_selection = request.form.get(f'multiple_selection_{i}') == 'true'

        # Insert into database
        if question and correct_answer and len(choices) == 4:  # Ensure all choices are present
            insert_question(question, correct_answer, choices, multiple_selection)

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