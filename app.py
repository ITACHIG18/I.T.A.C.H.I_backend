import os
import json
import uuid
import random
import smtplib

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from flask import Flask, request, jsonify
from flask_cors import CORS

from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

import fitz

from dotenv import load_dotenv
from openai import OpenAI
import jwt
import mysql.connector
from mysql.connector import Error


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

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

MAIL_SERVER = os.getenv(
    "MAIL_SERVER",
    ""
)

MAIL_PORT = int(
    os.getenv(
        "MAIL_PORT",
        "587"
    )
)

MAIL_USERNAME = os.getenv(
    "MAIL_USERNAME",
    ""
)

MAIL_PASSWORD = os.getenv(
    "MAIL_PASSWORD",
    ""
)

MAIL_FROM_NAME = os.getenv(
    "MAIL_FROM_NAME",
    "StudyMate"
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
# OPENAI CLIENT
# ============================================================

client = None

if OPENAI_API_KEY:

    client = OpenAI(
        api_key=OPENAI_API_KEY
    )


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

CORS(app)


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
        print("MySQL connection error:", error)
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
# HELPER FUNCTIONS
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
# EMAIL CONFIGURATION CHECK
# ============================================================

def email_is_configured():

    return all([
        MAIL_SERVER,
        MAIL_USERNAME,
        MAIL_PASSWORD
    ])


# ============================================================
# GENERATE VERIFICATION CODE
# ============================================================

def generate_verification_code():

    return str(
        random.randint(
            100000,
            999999
        )
    )


# ============================================================
# SEND VERIFICATION EMAIL
# ============================================================

def send_verification_email(
    recipient_email,
    recipient_name,
    verification_code
):

    if not email_is_configured():

        raise RuntimeError(
            "Email service is not configured."
        )

    message = EmailMessage()

    message[
        "Subject"
    ] = "StudyMate Email Verification Code"

    message[
        "From"
    ] = f"{MAIL_FROM_NAME} <{MAIL_USERNAME}>"

    message[
        "To"
    ] = recipient_email

    message.set_content(
        f"""
Hello {recipient_name},

Welcome to StudyMate.

Your email verification code is:

{verification_code}

This code will expire in 10 minutes.

If you did not create a StudyMate account, you can safely ignore this email.

StudyMate
Your AI-powered study companion.
"""
    )

    with smtplib.SMTP(
        MAIL_SERVER,
        MAIL_PORT
    ) as server:

        server.starttls()

        server.login(
            MAIL_USERNAME,
            MAIL_PASSWORD
        )

        server.send_message(
            message
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
            bool(
                user["email_verified"]
            ),

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
            else "disconnected"

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

    # --------------------------------------------------------
    # CHECK DATABASE
    # --------------------------------------------------------

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

        # ----------------------------------------------------
        # EXISTING ACCOUNT
        # ----------------------------------------------------

        if existing_user:

            if existing_user["email_verified"]:

                cursor.close()
                connection.close()

                return jsonify({
                    "error":
                        "An account with this email already exists."
                }), 409

            # ------------------------------------------------
            # EXISTING UNVERIFIED ACCOUNT
            # ------------------------------------------------

            verification_code = (
                generate_verification_code()
            )

            verification_expires = (
                datetime.now(
                    timezone.utc
                ).replace(
                    tzinfo=None
                )
                + timedelta(
                    minutes=10
                )
            )

            password_hash = generate_password_hash(
                password
            )

            cursor.execute(
                """
                UPDATE users
                SET
                    name = %s,
                    password_hash = %s,
                    verification_code = %s,
                    verification_expires = %s
                WHERE id = %s
                """,
                (
                    name,
                    password_hash,
                    verification_code,
                    verification_expires,
                    existing_user["id"]
                )
            )

            connection.commit()

            cursor.close()
            connection.close()

            try:

                send_verification_email(
                    email,
                    name,
                    verification_code
                )

            except Exception as error:

                print(
                    "Verification email error:",
                    error
                )

                return jsonify({
                    "error":
                        "We could not send the verification email. "
                        "Please check your email configuration."
                }), 500

            return jsonify({

                "message":
                    "Your account already exists but is not verified. "
                    "A new verification code has been sent to your email.",

                "email":
                    email

            }), 200

        # ----------------------------------------------------
        # NEW ACCOUNT
        # ----------------------------------------------------

        verification_code = (
            generate_verification_code()
        )

        verification_expires = (
            datetime.now(
                timezone.utc
            ).replace(
                tzinfo=None
            )
            + timedelta(
                minutes=10
            )
        )

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
                False,
                verification_code,
                verification_expires
            )
        )

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

    # --------------------------------------------------------
    # SEND EMAIL
    # --------------------------------------------------------

    try:

        send_verification_email(
            email,
            name,
            verification_code
        )

    except Exception as error:

        print(
            "Verification email error:",
            error
        )

        return jsonify({

            "error":
                "Your account was created, but we could not send "
                "the verification email. Please check your email "
                "configuration and use resend verification."

        }), 500

    return jsonify({

        "message":
            "Account created successfully. "
            "Check your email for the verification code.",

        "email":
            email

    }), 201


# ============================================================
# AUTH — VERIFY EMAIL
# ============================================================

@app.route(
    "/api/auth/verify-email",
    methods=["POST"]
)
def verify_email():

    data = request.get_json()

    if not data:

        return jsonify({
            "error":
                "No verification data was provided."
        }), 400

    email = str(
        data.get(
            "email",
            ""
        )
    ).strip().lower()

    code = str(
        data.get(
            "code",
            ""
        )
    ).strip()

    if not email:

        return jsonify({
            "error":
                "Email is required."
        }), 400

    if not code:

        return jsonify({
            "error":
                "Verification code is required."
        }), 400

    if not code.isdigit() or len(code) != 6:

        return jsonify({
            "error":
                "Verification code must be 6 digits."
        }), 400

    user = get_user_by_email(
        email
    )

    if not user:

        return jsonify({
            "error":
                "No account was found with this email."
        }), 404

    if user["email_verified"]:

        return jsonify({
            "message":
                "Email is already verified."
        }), 200

    verification_expires = user[
        "verification_expires"
    ]

    if not verification_expires:

        return jsonify({
            "error":
                "Your verification code has expired. "
                "Please request a new code."
        }), 400

    now = datetime.now()

    if now > verification_expires:

        return jsonify({
            "error":
                "Your verification code has expired. "
                "Please request a new code."
        }), 400

    if code != user[
        "verification_code"
    ]:

        return jsonify({
            "error":
                "Incorrect verification code."
        }), 400

    # --------------------------------------------------------
    # UPDATE DATABASE
    # --------------------------------------------------------

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "error":
                "Could not connect to the database."
        }), 500

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            UPDATE users
            SET
                email_verified = TRUE,
                verification_code = NULL,
                verification_expires = NULL
            WHERE id = %s
            """,
            (user["id"],)
        )

        connection.commit()

        cursor.close()
        connection.close()

    except Error as error:

        print(
            "Email verification database error:",
            error
        )

        try:
            connection.rollback()
            connection.close()
        except Exception:
            pass

        return jsonify({
            "error":
                "Could not verify your account."
        }), 500

    updated_user = get_user_by_id(
        user["id"]
    )

    token = create_access_token(
        updated_user
    )

    return jsonify({

        "message":
            "Email verified successfully.",

        "token":
            token,

        "user":
            public_user(
                updated_user
            )

    }), 200


# ============================================================
# AUTH — RESEND VERIFICATION CODE
# ============================================================

@app.route(
    "/api/auth/resend-code",
    methods=["POST"]
)
def resend_verification_code():

    data = request.get_json()

    if not data:

        return jsonify({
            "error":
                "No data was provided."
        }), 400

    email = str(
        data.get(
            "email",
            ""
        )
    ).strip().lower()

    if not email:

        return jsonify({
            "error":
                "Email is required."
        }), 400

    user = get_user_by_email(
        email
    )

    if not user:

        return jsonify({
            "error":
                "No account was found with this email."
        }), 404

    if user["email_verified"]:

        return jsonify({
            "message":
                "This email is already verified."
        }), 400

    verification_code = (
        generate_verification_code()
    )

    verification_expires = (
        datetime.now(
            timezone.utc
        ).replace(
            tzinfo=None
        )
        + timedelta(
            minutes=10
        )
    )

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "error":
                "Could not connect to the database."
        }), 500

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            UPDATE users
            SET
                verification_code = %s,
                verification_expires = %s
            WHERE id = %s
            """,
            (
                verification_code,
                verification_expires,
                user["id"]
            )
        )

        connection.commit()

        cursor.close()
        connection.close()

    except Error as error:

        print(
            "Resend code database error:",
            error
        )

        try:
            connection.rollback()
            connection.close()
        except Exception:
            pass

        return jsonify({
            "error":
                "Could not create a new verification code."
        }), 500

    try:

        send_verification_email(
            user["email"],
            user["name"],
            verification_code
        )

    except Exception as error:

        print(
            "Resend email error:",
            error
        )

        return jsonify({
            "error":
                "We could not send the verification email."
        }), 500

    return jsonify({

        "message":
            "A new verification code has been sent to your email.",

        "email":
            user["email"]

    }), 200


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

    if not user["email_verified"]:

        return jsonify({

            "error":
                "Please verify your email before logging in.",

            "email_verified":
                False,

            "email":
                user["email"]

        }), 403

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

    # --------------------------------------------------------
    # REQUIRE LOGIN
    # --------------------------------------------------------

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

    if client is None:

        return jsonify({
            "error":
                "OpenAI API key is not configured."
        }), 500

    data = request.get_json()

    if not data:

        return jsonify({
            "error":
                "No data was provided."
        }), 400

    text = data.get(
        "text",
        ""
    ).strip()

    if not text:

        return jsonify({
            "error":
                "No study material was provided."
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
            "notes":
                notes
        }), 200

    except Exception as error:

        print(
            "AI notes error:",
            error
        )

        return jsonify({

            "error":
                "Something went wrong while generating study notes."

        }), 500


# ============================================================
# GENERATE 30-QUESTION TEST
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

    if client is None:

        return jsonify({
            "error":
                "OpenAI API key is not configured."
        }), 500

    data = request.get_json()

    if not data:

        return jsonify({
            "error":
                "No data was provided."
        }), 400

    text = data.get(
        "text",
        ""
    ).strip()

    if not text:

        return jsonify({
            "error":
                "No study material was provided."
        }), 400

    attempt_id = data.get(
        "attempt"
    )

    if not attempt_id:

        attempt_id = str(
            uuid.uuid4()
        )

    previous_questions = data.get(
        "previousQuestions",
        []
    )

    if not isinstance(
        previous_questions,
        list
    ):

        previous_questions = []

    previous_questions = [

        str(question).strip()

        for question in previous_questions

        if str(question).strip()

    ]

    previous_questions = (
        previous_questions[:60]
    )

    if previous_questions:

        previous_questions_text = "\n".join(

            [
                f"{index + 1}. {question}"

                for index, question
                in enumerate(
                    previous_questions
                )
            ]

        )

    else:

        previous_questions_text = (
            "There are no previous questions. "
            "This is the first attempt."
        )

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
        print(
            "Student:",
            user["email"]
        )
        print(
            "Attempt:",
            attempt_id
        )
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

        raw_output = (
            response.output_text.strip()
        )

        if raw_output.startswith("```"):

            if raw_output.startswith(
                "```json"
            ):

                raw_output = raw_output[
                    len("```json"):
                ]

            elif raw_output.startswith(
                "```"
            ):

                raw_output = raw_output[
                    len("```"):
                ]

            if raw_output.endswith(
                "```"
            ):

                raw_output = raw_output[
                    :-len("```")
                ]

            raw_output = raw_output.strip()

        test_data = json.loads(
            raw_output
        )

        if not isinstance(
            test_data,
            dict
        ):

            raise ValueError(
                "AI response is not a JSON object."
            )

        questions = test_data.get(
            "questions",
            []
        )

        if not isinstance(
            questions,
            list
        ):

            raise ValueError(
                "Questions field is not a list."
            )

        generated_count = len(
            questions
        )

        print(
            "AI generated:",
            generated_count,
            "questions"
        )

        if generated_count < 30:

            return jsonify({

                "error": (
                    f"AI generated only "
                    f"{generated_count} questions. "
                    "At least 30 questions are required. "
                    "Please try generating the test again."
                )

            }), 500

        if generated_count > 30:

            print(
                f"AI generated {generated_count} questions. "
                "Keeping the first 30."
            )

            questions = questions[:30]

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

            for option in options:

                if not isinstance(
                    option,
                    str
                ) or not option.strip():

                    raise ValueError(
                        f"Question {index + 1} "
                        "contains an invalid option."
                    )

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

            explanation = question.get(
                "explanation"
            )

            if explanation is None:

                question[
                    "explanation"
                ] = ""

            elif not isinstance(
                explanation,
                str
            ):

                raise ValueError(
                    f"Question {index + 1} "
                    "has an invalid explanation."
                )

        normalized_questions = []

        for question in questions:

            normalized = " ".join(

                question[
                    "question"
                ]
                .lower()
                .split()

            )

            normalized_questions.append(
                normalized
            )

        if len(
            set(
                normalized_questions
            )
        ) != len(
            normalized_questions
        ):

            raise ValueError(
                "The AI generated duplicate "
                "questions inside the same test."
            )

        normalized_previous = {

            " ".join(
                question
                .lower()
                .split()
            )

            for question
            in previous_questions

        }

        repeated_questions = [

            question[
                "question"
            ]

            for question
            in questions

            if " ".join(
                question[
                    "question"
                ]
                .lower()
                .split()
            ) in normalized_previous

        ]

        if repeated_questions:

            print(
                "WARNING: AI repeated previous questions:",
                len(repeated_questions)
            )

        if len(questions) != 30:

            raise ValueError(
                "The final test does not contain "
                "exactly 30 questions."
            )

        print("")
        print(
            "30 FRESH QUESTIONS GENERATED SUCCESSFULLY."
        )
        print(
            "Attempt:",
            attempt_id
        )
        print("")

        return jsonify({

            "questions":
                questions,

            "attempt":
                attempt_id

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


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return jsonify({
        "error":
            "Endpoint not found."
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):

    return jsonify({
        "error":
            "Method not allowed."
    }), 405


@app.errorhandler(500)
def internal_server_error(error):

    return jsonify({
        "error":
            "Internal server error."
    }), 500


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":

    print("")
    print("======================================")
    print("         STUDYMATE BACKEND")
    print("======================================")
    print("")
    print("Server: http://127.0.0.1:5000")
    print("")
    print("Database:")
    print(f"MySQL: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print("")
    print("Authentication:")
    print("POST /api/auth/register")
    print("POST /api/auth/verify-email")
    print("POST /api/auth/resend-code")
    print("POST /api/auth/login")
    print("GET  /api/auth/me")
    print("POST /api/auth/logout")
    print("")
    print("StudyMate:")
    print("POST /api/upload-pdf")
    print("POST /api/generate-notes")
    print("POST /api/generate-test")
    print("")
    print("======================================")
    print("")

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000,
        use_reloader=False
    )