import os
import json
import uuid
import re

from datetime import datetime, timedelta, timezone

from flask import Flask, request, jsonify
from flask_cors import CORS

from werkzeug.utils import secure_filename
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

import fitz

from dotenv import load_dotenv
from google import genai

import jwt
import mysql.connector
from mysql.connector import Error


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "CHANGE_THIS_SECRET_BEFORE_DEPLOYING"
)

JWT_EXPIRATION_MINUTES = int(
    os.getenv(
        "JWT_EXPIRATION_MINUTES",
        "1440"
    )
)


# ============================================================
# MYSQL CONFIGURATION
# ============================================================

DB_HOST = os.getenv(
    "DB_HOST",
    "127.0.0.1"
)

DB_PORT = int(
    os.getenv(
        "DB_PORT",
        "3306"
    )
)

DB_NAME = os.getenv(
    "DB_NAME",
    "studymate_db"
)

DB_USER = os.getenv(
    "DB_USER",
    "root"
)

DB_PASSWORD = os.getenv(
    "DB_PASSWORD",
    ""
)


# ============================================================
# GEMINI CLIENT
# ============================================================

gemini_client = None

if GEMINI_API_KEY:

    try:

        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        print(
            "Gemini client initialized successfully."
        )

    except Exception as error:

        print(
            "Gemini client initialization error:",
            error
        )

        gemini_client = None


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": "*"
        }
    },
    supports_credentials=True
)


# ============================================================
# UPLOAD CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

UPLOAD_FOLDER = os.path.join(
    BASE_DIR,
    "uploads"
)

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

app.config[
    "UPLOAD_FOLDER"
] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {
    "pdf"
}


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection():

    try:

        connection = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            use_pure=True
        )

        return connection

    except Error as error:

        print(
            "MySQL connection error:",
            error
        )

        return None


# ============================================================
# DATABASE HEALTH CHECK
# ============================================================

def database_is_available():

    connection = get_db_connection()

    if connection is None:

        return False

    try:

        cursor = connection.cursor()

        cursor.execute(
            "SELECT 1"
        )

        cursor.fetchone()

        cursor.close()

        connection.close()

        return True

    except Error as error:

        print(
            "Database health check error:",
            error
        )

        try:
            connection.close()
        except Exception:
            pass

        return False


# ============================================================
# FILE VALIDATION
# ============================================================

def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(
            ".",
            1
        )[1].lower() in ALLOWED_EXTENSIONS
    )


# ============================================================
# CREATE JWT TOKEN
# ============================================================

def create_access_token(user):

    now = datetime.now(
        timezone.utc
    )

    expiration = now + timedelta(
        minutes=JWT_EXPIRATION_MINUTES
    )

    payload = {

        "sub":
            str(user["id"]),

        "email":
            user["email"],

        "name":
            user["name"],

        "iat":
            now,

        "exp":
            expiration
    }

    token = jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm="HS256"
    )

    return token


# ============================================================
# FIND USER BY ID
# ============================================================

def get_user_by_id(user_id):

    connection = get_db_connection()

    if connection is None:

        return None

    try:

        cursor = connection.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT
                id,
                name,
                email,
                password_hash,
                email_verified,
                verification_code,
                verification_expires,
                created_at
            FROM users
            WHERE id = %s
            LIMIT 1
            """,
            (user_id,)
        )

        user = cursor.fetchone()

        cursor.close()

        connection.close()

        return user

    except Error as error:

        print(
            "Find user error:",
            error
        )

        try:
            connection.close()
        except Exception:
            pass

        return None


# ============================================================
# FIND USER BY EMAIL
# ============================================================

def get_user_by_email(email):

    connection = get_db_connection()

    if connection is None:

        return None

    try:

        cursor = connection.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT
                id,
                name,
                email,
                password_hash,
                email_verified,
                verification_code,
                verification_expires,
                created_at
            FROM users
            WHERE email = %s
            LIMIT 1
            """,
            (email,)
        )

        user = cursor.fetchone()

        cursor.close()

        connection.close()

        return user

    except Error as error:

        print(
            "Find user by email error:",
            error
        )

        try:
            connection.close()
        except Exception:
            pass

        return None


# ============================================================
# SAFE USER RESPONSE
# ============================================================

def public_user(user):

    created_at = user.get(
        "created_at"
    )

    if isinstance(
        created_at,
        datetime
    ):

        created_at = created_at.isoformat()

    return {

        "id":
            user["id"],

        "name":
            user["name"],

        "email":
            user["email"],

        "email_verified":
            True,

        "created_at":
            created_at
    }


# ============================================================
# VERIFY JWT TOKEN
# ============================================================

def get_current_user():

    authorization = request.headers.get(
        "Authorization"
    )

    if not authorization:

        return None, (
            jsonify({
                "error":
                    "Authorization token is required."
            }),
            401
        )

    parts = authorization.split()

    if len(parts) != 2:

        return None, (
            jsonify({
                "error":
                    "Invalid authorization header."
            }),
            401
        )

    if parts[0].lower() != "bearer":

        return None, (
            jsonify({
                "error":
                    "Authorization must use Bearer token."
            }),
            401
        )

    token = parts[1]

    try:

        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=["HS256"]
        )

        user_id = payload.get(
            "sub"
        )

        if not user_id:

            return None, (
                jsonify({
                    "error":
                        "Invalid token."
                }),
                401
            )

        user = get_user_by_id(
            user_id
        )

        if not user:

            return None, (
                jsonify({
                    "error":
                        "User account was not found."
                }),
                401
            )

        return user, None

    except jwt.ExpiredSignatureError:

        return None, (
            jsonify({
                "error":
                    "Your session has expired. Please log in again."
            }),
            401
        )

    except jwt.InvalidTokenError:

        return None, (
            jsonify({
                "error":
                    "Invalid or expired authentication token."
            }),
            401
        )


# ============================================================
# CLEAN AI JSON RESPONSE
# ============================================================

def extract_json_from_ai_response(text):

    if not text:

        return None

    cleaned = text.strip()

    # Remove markdown code fences
    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned
    )

    cleaned = cleaned.strip()

    try:

        return json.loads(
            cleaned
        )

    except json.JSONDecodeError:

        pass

    # Try finding a JSON object
    object_match = re.search(
        r"\{.*\}",
        cleaned,
        re.DOTALL
    )

    if object_match:

        try:

            return json.loads(
                object_match.group(0)
            )

        except json.JSONDecodeError:

            pass

    # Try finding a JSON array
    array_match = re.search(
        r"\[.*\]",
        cleaned,
        re.DOTALL
    )

    if array_match:

        try:

            return json.loads(
                array_match.group(0)
            )

        except json.JSONDecodeError:

            pass

    return None


# ============================================================
# GEMINI TEXT GENERATION
# ============================================================

def ask_gemini(
    system_prompt,
    user_prompt
):

    if gemini_client is None:

        return None, (
            "Gemini is not configured on the server. "
            "Please add GEMINI_API_KEY to your environment variables."
        )

    try:

        full_prompt = f"""
{system_prompt}

USER REQUEST:

{user_prompt}
"""

        response = gemini_client.models.generate_content(

            model="gemini-3.6-flash",

            contents=full_prompt

        )

        if not response:

            return None, (
                "Gemini returned an empty response."
            )

        content = getattr(
            response,
            "text",
            None
        )

        if not content:

            return None, (
                "Gemini returned an empty response."
            )

        return content, None

    except Exception as error:

        print(
            "Gemini request error:",
            repr(error)
        )

        error_text = str(
            error
        )

        if (
            "401" in error_text
            or "403" in error_text
            or "API key" in error_text
            or "authentication" in error_text.lower()
        ):

            return None, (
                "The Gemini API key configured on the server "
                "is invalid or unauthorized."
            )

        if "429" in error_text:

            return None, (
                "The Gemini free-tier request limit has been reached. "
                "Please wait and try again later."
            )

        return None, (
            "The Gemini AI service could not process your request."
        )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return jsonify({

        "message":
            "StudyMate backend is running.",

        "status":
            "online",

        "service":
            "StudyMate API"

    }), 200


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/api/health",
    methods=["GET"]
)
def health():

    database_status = database_is_available()

    return jsonify({

        "status":
            "ok",

        "message":
            "StudyMate API is working.",

        "database":
            "connected"
            if database_status
            else "disconnected",

        "gemini":
            "configured"
            if GEMINI_API_KEY
            else "not configured"

    }), 200


# ============================================================
# AUTH — REGISTER
# ============================================================

@app.route(
    "/api/auth/register",
    methods=["POST"]
)
def register():

    data = request.get_json()

    if not data:

        return jsonify({
            "error":
                "No registration data was provided."
        }), 400

    name = str(
        data.get(
            "name",
            ""
        )
    ).strip()

    email = str(
        data.get(
            "email",
            ""
        )
    ).strip().lower()

    password = str(
        data.get(
            "password",
            ""
        )
    )

    if not name:

        return jsonify({
            "error":
                "Name is required."
        }), 400

    if len(name) < 2:

        return jsonify({
            "error":
                "Name must contain at least 2 characters."
        }), 400

    if not email:

        return jsonify({
            "error":
                "Email is required."
        }), 400

    if "@" not in email or "." not in email:

        return jsonify({
            "error":
                "Please enter a valid email address."
        }), 400

    if not password:

        return jsonify({
            "error":
                "Password is required."
        }), 400

    if len(password) < 8:

        return jsonify({
            "error":
                "Password must be at least 8 characters."
        }), 400

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "error":
                "Could not connect to the database."
        }), 500

    try:

        cursor = connection.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE email = %s
            LIMIT 1
            """,
            (email,)
        )

        existing_user = cursor.fetchone()

        if existing_user:

            cursor.close()
            connection.close()

            return jsonify({
                "error":
                    "An account with this email already exists."
            }), 409

        password_hash = generate_password_hash(
            password
        )

        cursor.execute(
            """
            INSERT INTO users (
                name,
                email,
                password_hash,
                email_verified,
                verification_code,
                verification_expires
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                name,
                email,
                password_hash,
                True,
                None,
                None
            )
        )

        user_id = cursor.lastrowid

        connection.commit()

        cursor.close()
        connection.close()

    except Error as error:

        print(
            "Registration database error:",
            error
        )

        try:
            connection.rollback()
            connection.close()
        except Exception:
            pass

        return jsonify({
            "error":
                "Something went wrong while creating your account."
        }), 500

    user = get_user_by_id(
        user_id
    )

    if not user:

        return jsonify({
            "error":
                "Account was created, but the user could not be loaded."
        }), 500

    token = create_access_token(
        user
    )

    return jsonify({

        "message":
            "Account created successfully.",

        "token":
            token,

        "user":
            public_user(
                user
            )

    }), 201


# ============================================================
# AUTH — LOGIN
# ============================================================

@app.route(
    "/api/auth/login",
    methods=["POST"]
)
def login():

    data = request.get_json()

    if not data:

        return jsonify({
            "error":
                "No login data was provided."
        }), 400

    email = str(
        data.get(
            "email",
            ""
        )
    ).strip().lower()

    password = str(
        data.get(
            "password",
            ""
        )
    )

    if not email:

        return jsonify({
            "error":
                "Email is required."
        }), 400

    if not password:

        return jsonify({
            "error":
                "Password is required."
        }), 400

    user = get_user_by_email(
        email
    )

    if not user:

        return jsonify({
            "error":
                "Invalid email or password."
        }), 401

    if not check_password_hash(
        user["password_hash"],
        password
    ):

        return jsonify({
            "error":
                "Invalid email or password."
        }), 401

    token = create_access_token(
        user
    )

    return jsonify({

        "message":
            "Login successful.",

        "token":
            token,

        "user":
            public_user(
                user
            )

    }), 200


# ============================================================
# AUTH — CURRENT USER
# ============================================================

@app.route(
    "/api/auth/me",
    methods=["GET"]
)
def current_user():

    user, error_response = (
        get_current_user()
    )

    if error_response:

        return error_response

    return jsonify({

        "user":
            public_user(
                user
            )

    }), 200


# ============================================================
# AUTH — LOGOUT
# ============================================================

@app.route(
    "/api/auth/logout",
    methods=["POST"]
)
def logout():

    return jsonify({

        "message":
            "Logged out successfully."

    }), 200


# ============================================================
# PDF UPLOAD
# ============================================================

@app.route(
    "/api/upload-pdf",
    methods=["POST"]
)
def upload_pdf():

    user, error_response = (
        get_current_user()
    )

    if error_response:

        return error_response

    if "file" not in request.files:

        return jsonify({
            "error":
                "No file was uploaded."
        }), 400

    file = request.files[
        "file"
    ]

    if file.filename == "":

        return jsonify({
            "error":
                "No file was selected."
        }), 400

    if not allowed_file(
        file.filename
    ):

        return jsonify({
            "error":
                "Only PDF files are allowed."
        }), 400

    original_filename = secure_filename(
        file.filename
    )

    unique_filename = (
        f"{uuid.uuid4().hex}_"
        f"{original_filename}"
    )

    file_path = os.path.join(
        app.config[
            "UPLOAD_FOLDER"
        ],
        unique_filename
    )

    try:

        file.save(
            file_path
        )

        document = fitz.open(
            file_path
        )

        extracted_text = ""

        for page_number, page in enumerate(
            document
        ):

            page_text = page.get_text()

            extracted_text += page_text

            if page_number < len(document) - 1:

                extracted_text += "\n\n"

        page_count = len(
            document
        )

        document.close()

        if not extracted_text.strip():

            return jsonify({
                "error":
                    "The PDF was uploaded, but no readable text was found."
            }), 400

        return jsonify({

            "message":
                "PDF uploaded and processed successfully.",

            "filename":
                unique_filename,

            "original_filename":
                original_filename,

            "pages":
                page_count,

            "text":
                extracted_text

        }), 200

    except Exception as error:

        print(
            "PDF processing error:",
            error
        )

        if os.path.exists(
            file_path
        ):

            try:

                os.remove(
                    file_path
                )

            except Exception:
                pass

        return jsonify({

            "error":
                "Something went wrong while processing the PDF."

        }), 500


# ============================================================
# GENERATE AI STUDY NOTES
# ============================================================

@app.route(
    "/api/generate-notes",
    methods=["POST"]
)
def generate_notes():

    # --------------------------------------------------------
    # REQUIRE LOGIN
    # --------------------------------------------------------

    user, error_response = (
        get_current_user()
    )

    if error_response:

        return error_response

    # --------------------------------------------------------
    # CHECK GEMINI
    # --------------------------------------------------------

    if gemini_client is None:

        return jsonify({
            "error":
                "Gemini is not configured on the server. "
                "Please add GEMINI_API_KEY to your environment variables."
        }), 500

    # --------------------------------------------------------
    # READ REQUEST
    # --------------------------------------------------------

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "error":
                "No study material was provided."
        }), 400

    text = str(
        data.get(
            "text",
            ""
        )
    ).strip()

    if not text:

        return jsonify({
            "error":
                "Study material is empty."
        }), 400

    # --------------------------------------------------------
    # LIMIT EXTREMELY LARGE PDF TEXT
    # --------------------------------------------------------

    max_characters = 60000

    if len(text) > max_characters:

        text = text[
            :max_characters
        ]

    # --------------------------------------------------------
    # AI PROMPT
    # --------------------------------------------------------

    system_prompt = """
You are StudyMate, an expert academic study assistant.

Your job is to turn study material into SHORT, clear,
high-quality revision notes.

Rules:

1. Use only information contained in the supplied material.
2. Do not invent facts.
3. Focus on concepts students are likely to be examined on.
4. Use clear headings.
5. Use bullet points where appropriate.
6. Explain difficult concepts simply.
7. Include important definitions.
8. Include formulas only when they appear in the material.
9. Remove unnecessary repetition.
10. Make the notes easy to revise quickly.
11. Do not mention that you are an AI.
12. Do not add a test or questions.
"""

    user_prompt = f"""
Create concise revision notes from the following study material.

STUDY MATERIAL:

{text}
"""

    # --------------------------------------------------------
    # CALL GEMINI
    # --------------------------------------------------------

    notes, ai_error = ask_gemini(
        system_prompt,
        user_prompt
    )

    if ai_error:

        return jsonify({
            "error":
                ai_error
        }), 500

    if not notes:

        return jsonify({
            "error":
                "The AI did not return any study notes."
        }), 500

    return jsonify({

        "message":
            "Study notes generated successfully.",

        "notes":
            notes

    }), 200


# ============================================================
# GENERATE 30 QUESTION AI TEST
# ============================================================

@app.route(
    "/api/generate-test",
    methods=["POST"]
)
def generate_test():

    # --------------------------------------------------------
    # REQUIRE LOGIN
    # --------------------------------------------------------

    user, error_response = (
        get_current_user()
    )

    if error_response:

        return error_response

    # --------------------------------------------------------
    # CHECK GEMINI
    # --------------------------------------------------------

    if gemini_client is None:

        return jsonify({
            "error":
                "Gemini is not configured on the server. "
                "Please add GEMINI_API_KEY to your environment variables."
        }), 500

    # --------------------------------------------------------
    # READ REQUEST
    # --------------------------------------------------------

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "error":
                "No study material was provided."
        }), 400

    text = str(
        data.get(
            "text",
            ""
        )
    ).strip()

    if not text:

        return jsonify({
            "error":
                "Study material is empty."
        }), 400

    previous_questions = data.get(
        "previousQuestions",
        []
    )

    if not isinstance(
        previous_questions,
        list
    ):

        previous_questions = []

    # --------------------------------------------------------
    # LIMIT MATERIAL SIZE
    # --------------------------------------------------------

    max_characters = 60000

    if len(text) > max_characters:

        text = text[
            :max_characters
        ]

    # --------------------------------------------------------
    # PREVIOUS QUESTION INFORMATION
    # --------------------------------------------------------

    previous_text = ""

    if previous_questions:

        cleaned_previous = []

        for question in previous_questions:

            if isinstance(
                question,
                str
            ):

                question = question.strip()

                if question:

                    cleaned_previous.append(
                        question
                    )

        if cleaned_previous:

            previous_text = (
                "\n\n"
                "DO NOT REPEAT THESE PREVIOUS QUESTIONS:\n"
                + "\n".join(
                    f"- {question}"
                    for question in cleaned_previous[
                        :50
                    ]
                )
            )

    # --------------------------------------------------------
    # AI PROMPT
    # --------------------------------------------------------

    system_prompt = """
You are StudyMate's examination generator.

Create exactly 30 high-quality multiple-choice questions
from the supplied study material.

Every question MUST have exactly:

- question
- options
- answer
- explanation

The answer must be the ZERO-BASED option index:

0 = first option
1 = second option
2 = third option
3 = fourth option

Return ONLY valid JSON.

The JSON must have exactly this structure:

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
      "explanation": "Short explanation."
    }
  ]
}

Rules:

1. Generate exactly 30 questions.
2. Every question must have exactly 4 options.
3. Only one option can be correct.
4. The answer must be an integer from 0 to 3.
5. Questions must be based only on the supplied material.
6. Do not invent information.
7. Avoid duplicate questions.
8. Mix easy, medium and difficult questions.
9. Test understanding, not just memorization.
10. Keep explanations concise.
11. Do not use markdown.
12. Return JSON only.
"""

    user_prompt = f"""
Create exactly 30 multiple-choice questions from this
study material.

STUDY MATERIAL:

{text}

{previous_text}
"""

    # --------------------------------------------------------
    # CALL GEMINI
    # --------------------------------------------------------

    ai_response, ai_error = ask_gemini(
        system_prompt,
        user_prompt
    )

    if ai_error:

        return jsonify({
            "error":
                ai_error
        }), 500

    if not ai_response:

        return jsonify({
            "error":
                "The AI did not return a test."
        }), 500

    # --------------------------------------------------------
    # PARSE JSON
    # --------------------------------------------------------

    parsed = extract_json_from_ai_response(
        ai_response
    )

    if not parsed:

        print(
            "Could not parse AI test response:"
        )

        print(
            ai_response[:5000]
        )

        return jsonify({
            "error":
                "The AI returned an invalid test format. Please try again."
        }), 500

    # --------------------------------------------------------
    # EXTRACT QUESTIONS
    # --------------------------------------------------------

    if isinstance(
        parsed,
        dict
    ):

        questions = parsed.get(
            "questions"
        )

    elif isinstance(
        parsed,
        list
    ):

        questions = parsed

    else:

        questions = None

    if not isinstance(
        questions,
        list
    ):

        return jsonify({
            "error":
                "The AI did not return a valid question list."
        }), 500

    # --------------------------------------------------------
    # VALIDATE QUESTIONS
    # --------------------------------------------------------

    valid_questions = []

    for question in questions:

        if not isinstance(
            question,
            dict
        ):

            continue

        question_text = str(
            question.get(
                "question",
                ""
            )
        ).strip()

        options = question.get(
            "options"
        )

        answer = question.get(
            "answer"
        )

        explanation = str(
            question.get(
                "explanation",
                ""
            )
        ).strip()

        if not question_text:

            continue

        if not isinstance(
            options,
            list
        ):

            continue

        if len(options) != 4:

            continue

        cleaned_options = []

        for option in options:

            option = str(
                option
            ).strip()

            if not option:

                break

            cleaned_options.append(
                option
            )

        if len(cleaned_options) != 4:

            continue

        try:

            answer = int(
                answer
            )

        except (
            ValueError,
            TypeError
        ):

            continue

        if answer < 0 or answer > 3:

            continue

        valid_questions.append({

            "question":
                question_text,

            "options":
                cleaned_options,

            "answer":
                answer,

            "explanation":
                explanation

        })

    # --------------------------------------------------------
    # REMOVE DUPLICATES
    # --------------------------------------------------------

    unique_questions = []

    seen_questions = set()

    for question in valid_questions:

        normalized = (
            question["question"]
            .strip()
            .lower()
        )

        if normalized in seen_questions:

            continue

        seen_questions.add(
            normalized
        )

        unique_questions.append(
            question
        )

    # --------------------------------------------------------
    # REQUIRE EXACTLY 30
    # --------------------------------------------------------

    if len(unique_questions) < 30:

        return jsonify({
            "error":
                (
                    f"The AI generated only "
                    f"{len(unique_questions)} valid questions "
                    "instead of 30. Please try again."
                )
        }), 500

    unique_questions = unique_questions[
        :30
    ]

    return jsonify({

        "message":
            "30-question test generated successfully.",

        "questions":
            unique_questions

    }), 200


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return jsonify({

        "error":
            "The requested endpoint was not found.",

        "path":
            request.path

    }), 404


@app.errorhandler(405)
def method_not_allowed(error):

    return jsonify({

        "error":
            "The requested method is not allowed."

    }), 405


@app.errorhandler(500)
def internal_server_error(error):

    print(
        "Unhandled server error:",
        error
    )

    return jsonify({

        "error":
            "An unexpected server error occurred."

    }), 500


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )