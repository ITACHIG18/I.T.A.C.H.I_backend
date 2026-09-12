
import os
import json
import uuid

from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import fitz

from dotenv import load_dotenv
from openai import OpenAI


# ==========================================
# LOAD ENVIRONMENT VARIABLES
# ==========================================

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = None

if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)


# ==========================================
# FLASK APP
# ==========================================

app = Flask(__name__)

CORS(app)


# ==========================================
# UPLOAD CONFIGURATION
# ==========================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {"pdf"}


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# ==========================================
# HOME
# ==========================================

@app.route("/")
def home():
    return jsonify({
        "message": "StudyMate backend is running."
    })


# ==========================================
# PDF UPLOAD
# ==========================================

@app.route("/api/upload-pdf", methods=["POST"])
def upload_pdf():

    if "file" not in request.files:
        return jsonify({
            "error": "No file was uploaded."
        }), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({
            "error": "No file was selected."
        }), 400

    if not allowed_file(file.filename):
        return jsonify({
            "error": "Only PDF files are allowed."
        }), 400

    original_filename = secure_filename(file.filename)

    unique_filename = f"{uuid.uuid4().hex}_{original_filename}"

    file_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        unique_filename
    )

    try:

        file.save(file_path)

        document = fitz.open(file_path)

        extracted_text = ""

        for page_number, page in enumerate(document):

            page_text = page.get_text()

            extracted_text += page_text

            if page_number < len(document) - 1:
                extracted_text += "\n\n"

        page_count = len(document)

        document.close()

        return jsonify({
            "message": "PDF uploaded and processed successfully.",
            "filename": unique_filename,
            "original_filename": original_filename,
            "pages": page_count,
            "text": extracted_text
        }), 200

    except Exception as error:

        print("PDF processing error:", error)

        return jsonify({
            "error": "Something went wrong while processing the PDF."
        }), 500


# ==========================================
# GENERATE AI STUDY NOTES
# ==========================================

@app.route("/api/generate-notes", methods=["POST"])
def generate_notes():

    if client is None:
        return jsonify({
            "error": "OpenAI API key is not configured."
        }), 500

    data = request.get_json()

    if not data:
        return jsonify({
            "error": "No data was provided."
        }), 400

    text = data.get("text", "").strip()

    if not text:
        return jsonify({
            "error": "No study material was provided."
        }), 400

    system_prompt = """
You are StudyMate, an AI study assistant.

Your job is to transform the educational material supplied by the student
into short, clear and exam-focused study notes.

IMPORTANT RULES:

1. Use ONLY information contained in the supplied material.
2. Do not invent facts.
3. Do not add information from outside sources.
4. Preserve important technical terms.
5. Keep explanations simple but academically accurate.
6. Organize the notes clearly.
7. Highlight important definitions.
8. Include important formulas.
9. Include important processes.
10. Include important examples when they appear in the material.
11. Include comparisons when useful.
12. Focus on information that is likely to help the student prepare for a test.

Use headings and bullet points where appropriate.

The notes should be concise enough for revision but detailed enough
to cover the important information.
"""

    user_prompt = f"""
Create StudyMate revision notes from the following lecture material:

{text}
"""

    try:

        response = client.responses.create(
            model="gpt-5.6-luna",
            instructions=system_prompt,
            input=user_prompt
        )

        notes = response.output_text.strip()

        return jsonify({
            "notes": notes
        }), 200

    except Exception as error:

        print("AI notes error:", error)

        return jsonify({
            "error": "Something went wrong while generating study notes."
        }), 500


# ==========================================
# GENERATE 30-QUESTION TEST
# ==========================================

@app.route("/api/generate-test", methods=["POST"])
def generate_test():

    if client is None:
        return jsonify({
            "error": "OpenAI API key is not configured."
        }), 500

    data = request.get_json()

    if not data:
        return jsonify({
            "error": "No data was provided."
        }), 400

    text = data.get("text", "").strip()

    if not text:
        return jsonify({
            "error": "No study material was provided."
        }), 400

    # ======================================
    # ATTEMPT INFORMATION
    # ======================================

    attempt_id = data.get("attempt")

    if not attempt_id:
        attempt_id = str(uuid.uuid4())

    previous_questions = data.get(
        "previousQuestions",
        []
    )

    if not isinstance(previous_questions, list):
        previous_questions = []

    previous_questions = [
        str(question).strip()
        for question in previous_questions
        if str(question).strip()
    ]

    previous_questions = previous_questions[:60]

    if previous_questions:

        previous_questions_text = "\n".join(
            [
                f"{index + 1}. {question}"
                for index, question in enumerate(
                    previous_questions
                )
            ]
        )

    else:

        previous_questions_text = (
            "There are no previous questions. "
            "This is the first attempt."
        )

    # ======================================
    # TEST GENERATION INSTRUCTIONS
    # ======================================

    system_prompt = """
You are StudyMate's AI Test Generator.

Your job is to create a university-level multiple-choice test using ONLY
the educational material supplied by the student.

The student may take the test multiple times.

EVERY NEW ATTEMPT MUST GENERATE A FRESH SET OF QUESTIONS.

Do NOT simply reuse the previous test.

STRICT REQUIREMENTS:

1. Generate exactly 30 questions.
2. Every question must have exactly 4 options.
3. Only ONE option can be correct.
4. Do not invent information.
5. Do not use outside knowledge.
6. Questions must be based directly on the supplied material.
7. Cover different parts of the material.
8. Avoid duplicate questions.
9. Avoid repeating questions from previous attempts.
10. Do not merely change one word in an old question.
11. When possible, test different concepts from the material.
12. Vary the wording and structure of questions.
13. Vary the correct-answer position.
14. Vary the distractors.
15. Vary the order in which concepts are tested.
16. Include a mixture of:
    - definitions
    - concepts
    - understanding
    - applications
    - calculations where appropriate
    - important facts
17. Keep questions clear and suitable for a university student.
18. Every answer and explanation must be supported by the supplied material.
19. Do not reveal the correct answer outside the JSON structure.
20. The attempt identifier is only used to distinguish attempts. It is NOT
    educational material and must never be treated as a factual source.

FRESHNESS RULE:

The previous questions supplied by the user are examples of questions that
have already been asked.

You MUST create new questions that test the same material in different ways.

Do not copy previous question wording.

Do not create a question that is effectively the same question with
different numbers, names, or wording.

Try to explore concepts that were not tested previously.

If the previous test focused heavily on definitions, use more conceptual,
application, calculation, comparison, or interpretation questions where
the material allows it.

If calculations are present in the material, vary the values while keeping
the calculation fully solvable from the supplied material.

Return ONLY valid JSON.

The JSON MUST have exactly this structure:

{
    "questions": [
        {
            "question": "Question text",
            "options": [
                "Option A",
                "Option B",
                "Option C",
                "Option D"
            ],
            "answer": 0,
            "explanation": "Short explanation of the correct answer."
        }
    ]
}

The answer value MUST be:

0 = Option A
1 = Option B
2 = Option C
3 = Option D
"""

    # ======================================
    # USER PROMPT
    # ======================================

    user_prompt = f"""
StudyMate test attempt ID:

{attempt_id}

Create EXACTLY 30 NEW multiple-choice questions from the following
StudyMate learning material.

This is a fresh test attempt.

IMPORTANT:
The previous questions listed below have already been used.

You MUST avoid repeating them.

PREVIOUS QUESTIONS:

{previous_questions_text}

NOW CREATE A COMPLETELY FRESH SET OF 30 QUESTIONS.

Learning material:

{text}
"""

    try:

        print("")
        print("======================================")
        print("GENERATING STUDYMATE TEST")
        print("======================================")
        print("Attempt:", attempt_id)
        print(
            "Previous questions:",
            len(previous_questions)
        )
        print("======================================")
        print("")

        response = client.responses.create(
            model="gpt-5.6-luna",
            instructions=system_prompt,
            input=user_prompt
        )

        raw_output = response.output_text.strip()

        # ==================================
        # REMOVE MARKDOWN CODE FENCES
        # ==================================

        if raw_output.startswith("```"):

            if raw_output.startswith("```json"):
                raw_output = raw_output[
                    len("```json"):
                ]

            elif raw_output.startswith("```"):
                raw_output = raw_output[
                    len("```"):
                ]

            if raw_output.endswith("```"):
                raw_output = raw_output[
                    :-len("```")
                ]

            raw_output = raw_output.strip()

        # ==================================
        # PARSE JSON
        # ==================================

        test_data = json.loads(raw_output)

        if not isinstance(test_data, dict):
            raise ValueError(
                "AI response is not a JSON object."
            )

        questions = test_data.get(
            "questions",
            []
        )

        if not isinstance(questions, list):
            raise ValueError(
                "Questions field is not a list."
            )

        # ==================================
        # HANDLE QUESTION COUNT
        # ==================================

        generated_count = len(questions)

        print(
            "AI generated:",
            generated_count,
            "questions"
        )

        # Fewer than 30 cannot be safely completed.
        if generated_count < 30:

            return jsonify({
                "error": (
                    f"AI generated only {generated_count} "
                    "questions. At least 30 questions are required. "
                    "Please try generating the test again."
                )
            }), 500

        # If AI generates more than 30, automatically
        # keep exactly 30 instead of failing the test.
        if generated_count > 30:

            print(
                f"AI generated {generated_count} questions. "
                "Keeping the first 30."
            )

            questions = questions[:30]

        # ==================================
        # VALIDATE EVERY QUESTION
        # ==================================

        for index, question in enumerate(
            questions
        ):

            if not isinstance(
                question,
                dict
            ):
                raise ValueError(
                    f"Question {index + 1} is invalid."
                )

            # Question text
            question_text = question.get(
                "question"
            )

            if not isinstance(
                question_text,
                str
            ) or not question_text.strip():

                raise ValueError(
                    f"Question {index + 1} "
                    "is missing valid question text."
                )

            # Options
            options = question.get(
                "options"
            )

            if not isinstance(
                options,
                list
            ):

                raise ValueError(
                    f"Question {index + 1} "
                    "is missing its options."
                )

            if len(options) != 4:

                raise ValueError(
                    f"Question {index + 1} "
                    "does not have exactly 4 options."
                )

            # Make sure all options are strings
            for option in options:

                if not isinstance(
                    option,
                    str
                ) or not option.strip():

                    raise ValueError(
                        f"Question {index + 1} "
                        "contains an invalid option."
                    )

            # Answer
            answer = question.get(
                "answer"
            )

            if not isinstance(
                answer,
                int
            ) or answer not in [
                0,
                1,
                2,
                3
            ]:

                raise ValueError(
                    f"Question {index + 1} "
                    "has an invalid answer index."
                )

            # Explanation
            explanation = question.get(
                "explanation"
            )

            if explanation is None:
                question["explanation"] = ""

            elif not isinstance(
                explanation,
                str
            ):

                raise ValueError(
                    f"Question {index + 1} "
                    "has an invalid explanation."
                )

        # ==================================
        # BASIC DUPLICATE DETECTION
        # ==================================

        normalized_questions = []

        for question in questions:

            normalized = " ".join(
                question["question"]
                .lower()
                .split()
            )

            normalized_questions.append(
                normalized
            )

        if len(
            set(normalized_questions)
        ) != len(normalized_questions):

            raise ValueError(
                "The AI generated duplicate questions "
                "inside the same test."
            )

        # ==================================
        # CHECK AGAINST PREVIOUS QUESTIONS
        # ==================================

        normalized_previous = {
            " ".join(
                question
                .lower()
                .split()
            )
            for question in previous_questions
        }

        repeated_questions = [
            question["question"]
            for question in questions
            if " ".join(
                question["question"]
                .lower()
                .split()
            ) in normalized_previous
        ]

        if repeated_questions:

            print(
                "WARNING: AI repeated previous questions:",
                len(repeated_questions)
            )

        # ==================================
        # FINAL COUNT SAFETY CHECK
        # ==================================

        if len(questions) != 30:

            raise ValueError(
                "The final test does not contain exactly 30 questions."
            )

        # ==================================
        # SUCCESS
        # ==================================

        print("")
        print("30 FRESH QUESTIONS GENERATED SUCCESSFULLY.")
        print("Attempt:", attempt_id)
        print("")

        return jsonify({
            "questions": questions,
            "attempt": attempt_id
        }), 200

    except json.JSONDecodeError:

        print("")
        print("======================================")
        print("INVALID JSON RETURNED BY AI")
        print("======================================")
        print(raw_output)
        print("")

        return jsonify({
            "error": (
                "The AI returned an invalid test format. "
                "Please try generating the test again."
            )
        }), 500

    except Exception as error:

        print("")
        print("======================================")
        print("TEST GENERATION ERROR")
        print("======================================")
        print(error)
        print("")

        return jsonify({
            "error": (
                "Something went wrong while generating "
                "the test."
            )
        }), 500


# ==========================================
# RUN SERVER
# ==========================================

if __name__ == "__main__":

    print("")
    print("======================================")
    print("       STUDYMATE BACKEND")
    print("======================================")
    print("")
    print("Server: http://127.0.0.1:5000")
    print("")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
