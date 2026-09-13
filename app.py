import os
import json
import uuid
import re

from datetime import datetime, timedelta, timezone
from io import BytesIO

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from werkzeug.security import generate_password_hash, check_password_hash

import fitz

from dotenv import load_dotenv
from google import genai
from google.genai import types

import jwt
import mysql.connector
from mysql.connector import Error


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "CHANGE_THIS_SECRET_BEFORE_DEPLOYING"
)

JWT_EXPIRATION_MINUTES = int(
    os.getenv("JWT_EXPIRATION_MINUTES", "1440")
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
# GEMINI CONFIGURATION
# ============================================================

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
)

gemini_client = None

if GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        print(
            "Gemini client initialized successfully."
        )

        print(
            "Gemini model:",
            GEMINI_MODEL
        )

    except Exception as error:
        print(
            "Gemini client initialization error:",
            repr(error)
        )

        gemini_client = None

else:
    print(
        "WARNING: GEMINI_API_KEY is not configured."
    )


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)


# ============================================================
# CORS
# ============================================================

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": "*",
            "methods": [
                "GET",
                "POST",
                "PUT",
                "PATCH",
                "DELETE",
                "OPTIONS"
            ],
            "allow_headers": [
                "Content-Type",
                "Authorization"
            ],
            "expose_headers": [
                "Content-Type",
                "Content-Disposition"
            ]
        }
    },
    supports_credentials=False
)


# Explicit OPTIONS support
@app.route(
    "/api/<path:path>",
    methods=["OPTIONS"]
)
def handle_options(path):
    response = jsonify({
        "message": "CORS preflight successful."
    })

    response.status_code = 200

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization"
    )
    response.headers["Access-Control-Allow-Methods"] = (
        "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    )

    return response


# ============================================================
# PDF CONFIGURATION
# ============================================================

ALLOWED_EXTENSIONS = {
    "pdf"
}
def allowed_file(filename):
    if not filename:
        return False

    if "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    return extension in ALLOWED_EXTENSIONS

MAX_PDF_SIZE_MB = int(
    os.getenv(
        "MAX_PDF_SIZE_MB",
        "25"
    )
)

MAX_PDF_SIZE_BYTES = (
    MAX_PDF_SIZE_MB * 1024 * 1024
)

app.config[
    "MAX_CONTENT_LENGTH"
] = MAX_PDF_SIZE_BYTES


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
            repr(error)
        )

        return None


def database_is_available():

    connection = get_db_connection()

    if connection is None:
        return False

    cursor = None

    try:

        cursor = connection.cursor()

        cursor.execute(
            "SELECT 1"
        )

        cursor.fetchone()

        return True

    except Error as error:

        print(
            "Database health check error:",
            repr(error)
        )

        return False

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return jsonify({
        "message": "StudyMate backend is running.",
        "status": "online"
    }), 200


@app.route(
    "/api/health",
    methods=["GET"]
)
def health():

    return jsonify({
        "status": "ok",
        "database": (
            "connected"
            if database_is_available()
            else "unavailable"
        ),
        "gemini": (
            "configured"
            if gemini_client is not None
            else "not configured"
        ),
        "model": GEMINI_MODEL
    }), 200

import os
import json
import uuid
import re

from datetime import datetime, timedelta, timezone
from io import BytesIO

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from werkzeug.security import generate_password_hash, check_password_hash

import fitz

from dotenv import load_dotenv
from google import genai
from google.genai import types

import jwt
import mysql.connector
from mysql.connector import Error


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "CHANGE_THIS_SECRET_BEFORE_DEPLOYING"
)

JWT_EXPIRATION_MINUTES = int(
    os.getenv("JWT_EXPIRATION_MINUTES", "1440")
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
# GEMINI CONFIGURATION
# ============================================================

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
)

gemini_client = None

if GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        print(
            "Gemini client initialized successfully."
        )

        print(
            "Gemini model:",
            GEMINI_MODEL
        )

    except Exception as error:
        print(
            "Gemini client initialization error:",
            repr(error)
        )

        gemini_client = None

else:
    print(
        "WARNING: GEMINI_API_KEY is not configured."
    )


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)


# ============================================================
# CORS
# ============================================================

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": "*",
            "methods": [
                "GET",
                "POST",
                "PUT",
                "PATCH",
                "DELETE",
                "OPTIONS"
            ],
            "allow_headers": [
                "Content-Type",
                "Authorization"
            ],
            "expose_headers": [
                "Content-Type",
                "Content-Disposition"
            ]
        }
    },
    supports_credentials=False
)


# Explicit OPTIONS support
@app.route(
    "/api/<path:path>",
    methods=["OPTIONS"]
)
def handle_options(path):
    response = jsonify({
        "message": "CORS preflight successful."
    })

    response.status_code = 200

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization"
    )
    response.headers["Access-Control-Allow-Methods"] = (
        "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    )

    return response


# ============================================================
# PDF CONFIGURATION
# ============================================================

ALLOWED_EXTENSIONS = {
    "pdf"
}

MAX_PDF_SIZE_MB = int(
    os.getenv(
        "MAX_PDF_SIZE_MB",
        "25"
    )
)

MAX_PDF_SIZE_BYTES = (
    MAX_PDF_SIZE_MB * 1024 * 1024
)

app.config[
    "MAX_CONTENT_LENGTH"
] = MAX_PDF_SIZE_BYTES


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
            repr(error)
        )

        return None


def database_is_available():

    connection = get_db_connection()

    if connection is None:
        return False

    cursor = None

    try:

        cursor = connection.cursor()

        cursor.execute(
            "SELECT 1"
        )

        cursor.fetchone()

        return True

    except Error as error:

        print(
            "Database health check error:",
            repr(error)
        )

        return False

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return jsonify({
        "message": "StudyMate backend is running.",
        "status": "online"
    }), 200


@app.route(
    "/api/health",
    methods=["GET"]
)
def health():

    return jsonify({
        "status": "ok",
        "database": (
            "connected"
            if database_is_available()
            else "unavailable"
        ),
        "gemini": (
            "configured"
            if gemini_client is not None
            else "not configured"
        ),
        "model": GEMINI_MODEL
    }), 200

# ============================================================
# AUTHENTICATION HELPERS
# ============================================================

def get_user_by_email(email):

    connection = get_db_connection()

    if connection is None:
        return None

    cursor = None

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
                created_at
            FROM users
            WHERE email = %s
            LIMIT 1
            """,
            (email,)
        )

        user = cursor.fetchone()

        return user

    except Error as error:

        print(
            "Get user by email error:",
            repr(error)
        )

        return None

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


def get_user_by_id(user_id):

    connection = get_db_connection()

    if connection is None:
        return None

    cursor = None

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
                created_at
            FROM users
            WHERE id = %s
            LIMIT 1
            """,
            (user_id,)
        )

        user = cursor.fetchone()

        return user

    except Error as error:

        print(
            "Get user by ID error:",
            repr(error)
        )

        return None

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


def public_user(user):

    if not user:
        return None

    created_at = user.get(
        "created_at"
    )

    if isinstance(
        created_at,
        datetime
    ):

        created_at = (
            created_at.isoformat()
        )

    return {
        "id":
            user.get("id"),
        "name":
            user.get("name"),
        "email":
            user.get("email"),
        "created_at":
            created_at
    }


def create_access_token(user):

    now = datetime.now(
        timezone.utc
    )

    expiration = (
        now
        + timedelta(
            minutes=JWT_EXPIRATION_MINUTES
        )
    )

    payload = {
        "user_id":
            user["id"],
        "email":
            user["email"],
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


def get_current_user():

    authorization = request.headers.get(
        "Authorization",
        ""
    ).strip()

    if not authorization:

        return None, (
            jsonify({
                "error":
                    "Authorization token is required."
            }),
            401
        )

    if not authorization.lower().startswith(
        "bearer "
    ):

        return None, (
            jsonify({
                "error":
                    "Invalid authorization header."
            }),
            401
        )

    token = authorization[7:].strip()

    if not token:

        return None, (
            jsonify({
                "error":
                    "Authorization token is missing."
            }),
            401
        )

    try:

        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=["HS256"]
        )

        user_id = payload.get(
            "user_id"
        )

        if not user_id:

            return None, (
                jsonify({
                    "error":
                        "Invalid authorization token."
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
                    "Invalid authorization token."
            }),
            401
        )

    except Exception as error:

        print(
            "Authentication error:",
            repr(error)
        )

        return None, (
            jsonify({
                "error":
                    "Unable to authenticate your account."
            }),
            401
        )


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/api/auth/register",
    methods=["POST", "OPTIONS"]
)
def register():

    if request.method == "OPTIONS":

        return jsonify({
            "message":
                "CORS preflight successful."
        }), 200

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "error":
                "Please provide your registration details."
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

    if len(password) < 6:

        return jsonify({
            "error":
                "Password must contain at least 6 characters."
        }), 400

    existing_user = get_user_by_email(
        email
    )

    if existing_user:

        return jsonify({
            "error":
                "An account with this email already exists."
        }), 409

    password_hash = generate_password_hash(
        password
    )

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "error":
                "Could not connect to the database."
        }), 500

    cursor = None

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO users (
                name,
                email,
                password_hash
            )
            VALUES (
                %s,
                %s,
                %s
            )
            """,
            (
                name,
                email,
                password_hash
            )
        )

        user_id = cursor.lastrowid

        connection.commit()

        user = get_user_by_id(
            user_id
        )

        if not user:

            return jsonify({
                "error":
                    "Account was created, but could not be loaded."
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
                public_user(user)
        }), 201

    except Error as error:

        print(
            "Registration database error:",
            repr(error)
        )

        try:
            connection.rollback()
        except Exception:
            pass

        return jsonify({
            "error":
                "Could not create your account."
        }), 500

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/api/auth/login",
    methods=["POST", "OPTIONS"]
)
def login():

    if request.method == "OPTIONS":

        return jsonify({
            "message":
                "CORS preflight successful."
        }), 200

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "error":
                "Please provide your login details."
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

    try:

        password_valid = check_password_hash(
            user["password_hash"],
            password
        )

    except Exception as error:

        print(
            "Password verification error:",
            repr(error)
        )

        return jsonify({
            "error":
                "Unable to verify your password."
        }), 500

    if not password_valid:

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
            public_user(user)
    }), 200


# ============================================================
# CURRENT USER
# ============================================================

@app.route(
    "/api/auth/me",
    methods=["GET"]
)
def auth_me():

    user, error_response = get_current_user()

    if error_response:
        return error_response

    return jsonify({
        "user":
            public_user(user)
    }), 200


# ============================================================
# UPLOAD PDF
# ============================================================

@app.route(
    "/api/upload-pdf",
    methods=["POST"]
)
def upload_pdf():

    user, error_response = get_current_user()

    if error_response:
        return error_response

    if "file" not in request.files:

        return jsonify({
            "error":
                "No file was uploaded."
        }), 400

    file = request.files["file"]

    if not file.filename:

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

    original_filename = (
        file.filename.strip()
    )

    try:

        pdf_bytes = file.read()

        if not pdf_bytes:

            return jsonify({
                "error":
                    "The uploaded PDF is empty."
            }), 400

        file_size = len(
            pdf_bytes
        )

        if file_size > MAX_PDF_SIZE_BYTES:

            return jsonify({
                "error":
                    f"PDF files must be smaller than "
                    f"{MAX_PDF_SIZE_MB} MB."
            }), 413

        document = fitz.open(
            stream=pdf_bytes,
            filetype="pdf"
        )

        extracted_parts = []

        for page in document:

            page_text = page.get_text()

            if page_text:

                extracted_parts.append(
                    page_text
                )

        page_count = len(
            document
        )

        document.close()

        extracted_text = (
            "\n\n".join(
                extracted_parts
            )
            .strip()
        )

        if not extracted_text:

            return jsonify({
                "error":
                    "The PDF was uploaded, but no readable text was found."
            }), 400

    except Exception as error:

        print(
            "PDF processing error:",
            repr(error)
        )

        return jsonify({
            "error":
                "Something went wrong while processing the PDF."
        }), 500

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "error":
                "The PDF was processed, but the database is unavailable."
        }), 500

    cursor = None

    try:

        cursor = connection.cursor()

        stored_filename = (
            f"{uuid.uuid4().hex}_"
            f"{original_filename}"
        )

        cursor.execute(
            """
            INSERT INTO study_materials (
                user_id,
                original_filename,
                stored_filename,
                file_data,
                extracted_text,
                page_count,
                file_size
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                user["id"],
                original_filename,
                stored_filename,
                pdf_bytes,
                extracted_text,
                page_count,
                file_size
            )
        )

        pdf_id = cursor.lastrowid

        connection.commit()

        return jsonify({
            "message":
                "PDF uploaded and saved permanently.",
            "id":
                pdf_id,
            "filename":
                stored_filename,
            "original_filename":
                original_filename,
            "pages":
                page_count,
            "file_size":
                file_size,
            "text":
                extracted_text
        }), 200

    except Error as error:

        print(
            "Permanent PDF storage error:",
            repr(error)
        )

        try:
            connection.rollback()
        except Exception:
            pass

        return jsonify({
            "error":
                "The PDF could not be saved permanently."
        }), 500

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# GET SAVED PDFs
# ============================================================

@app.route(
    "/api/pdfs",
    methods=["GET"]
)
def get_saved_pdfs():

    user, error_response = get_current_user()

    if error_response:
        return error_response

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "error":
                "Could not connect to the database."
        }), 500

    cursor = None

    try:

        cursor = connection.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT
                id,
                original_filename,
                stored_filename,
                page_count,
                file_size,
                created_at
            FROM study_materials
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (
                user["id"],
            )
        )

        rows = cursor.fetchall()

        pdfs = []

        for row in rows:

            created_at = row.get(
                "created_at"
            )

            if isinstance(
                created_at,
                datetime
            ):

                created_at = (
                    created_at.isoformat()
                )

            pdfs.append({
                "id":
                    row["id"],
                "original_filename":
                    row["original_filename"],
                "filename":
                    row["stored_filename"],
                "pages":
                    row["page_count"],
                "file_size":
                    row["file_size"],
                "created_at":
                    created_at
            })

        return jsonify({
            "pdfs":
                pdfs
        }), 200

    except Error as error:

        print(
            "Get saved PDFs error:",
            repr(error)
        )

        return jsonify({
            "error":
                "Could not load your saved PDFs."
        }), 500

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# GET SINGLE PDF
# ============================================================

@app.route(
    "/api/pdfs/<int:pdf_id>",
    methods=["GET"]
)
def get_saved_pdf(pdf_id):

    user, error_response = get_current_user()

    if error_response:
        return error_response

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "error":
                "Could not connect to the database."
        }), 500

    cursor = None

    try:

        cursor = connection.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT
                id,
                original_filename,
                file_data
            FROM study_materials
            WHERE id = %s
              AND user_id = %s
            LIMIT 1
            """,
            (
                pdf_id,
                user["id"]
            )
        )

        pdf = cursor.fetchone()

        if not pdf:

            return jsonify({
                "error":
                    "PDF not found."
            }), 404

        return send_file(
            BytesIO(
                pdf["file_data"]
            ),
            mimetype="application/pdf",
            as_attachment=False,
            download_name=pdf[
                "original_filename"
            ]
        )

    except Error as error:

        print(
            "Get PDF error:",
            repr(error)
        )

        return jsonify({
            "error":
                "Could not retrieve the PDF."
        }), 500

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# GET PDF DETAILS
# ============================================================

@app.route(
    "/api/pdfs/<int:pdf_id>/details",
    methods=["GET"]
)
def get_saved_pdf_details(
    pdf_id
):

    user, error_response = get_current_user()

    if error_response:
        return error_response

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "error":
                "Could not connect to the database."
        }), 500

    cursor = None

    try:

        cursor = connection.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT
                id,
                original_filename,
                stored_filename,
                extracted_text,
                page_count,
                file_size,
                created_at
            FROM study_materials
            WHERE id = %s
              AND user_id = %s
            LIMIT 1
            """,
            (
                pdf_id,
                user["id"]
            )
        )

        pdf = cursor.fetchone()

        if not pdf:

            return jsonify({
                "error":
                    "PDF not found."
            }), 404

        created_at = pdf.get(
            "created_at"
        )

        if isinstance(
            created_at,
            datetime
        ):

            created_at = (
                created_at.isoformat()
            )

        return jsonify({
            "id":
                pdf["id"],
            "original_filename":
                pdf["original_filename"],
            "filename":
                pdf["stored_filename"],
            "text":
                pdf["extracted_text"],
            "pages":
                pdf["page_count"],
            "file_size":
                pdf["file_size"],
            "created_at":
                created_at
        }), 200

    except Error as error:

        print(
            "Get PDF details error:",
            repr(error)
        )

        return jsonify({
            "error":
                "Could not load the PDF details."
        }), 500

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# DELETE PDF
# ============================================================

@app.route(
    "/api/pdfs/<int:pdf_id>",
    methods=["DELETE"]
)
def delete_saved_pdf(
    pdf_id
):

    user, error_response = get_current_user()

    if error_response:
        return error_response

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "error":
                "Could not connect to the database."
        }), 500

    cursor = None

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            DELETE FROM study_materials
            WHERE id = %s
              AND user_id = %s
            """,
            (
                pdf_id,
                user["id"]
            )
        )

        deleted_rows = cursor.rowcount

        connection.commit()

        if deleted_rows == 0:

            return jsonify({
                "error":
                    "PDF not found."
            }), 404

        return jsonify({
            "message":
                "PDF deleted successfully."
        }), 200

    except Error as error:

        print(
            "Delete saved PDF error:",
            repr(error)
        )

        try:
            connection.rollback()
        except Exception:
            pass

        return jsonify({
            "error":
                "Could not delete the PDF."
        }), 500

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        try:
            connection.close()
        except Exception:
            pass

# ============================================================
# GEMINI HELPER
# ============================================================

def ask_gemini(
    system_prompt,
    user_prompt,
    json_mode=False
):

    if gemini_client is None:

        return None, (
            "Gemini is not configured on the server."
        )

    full_prompt = (
        system_prompt
        + "\n\n"
        + user_prompt
    )

    try:

        if json_mode:

            config = types.GenerateContentConfig(
                temperature=0.4,
                response_mime_type="application/json"
            )

        else:

            config = types.GenerateContentConfig(
                temperature=0.5
            )

        response = (
            gemini_client
            .models
            .generate_content(
                model=GEMINI_MODEL,
                contents=full_prompt,
                config=config
            )
        )

        content = getattr(
            response,
            "text",
            None
        )

        if content is None:

            content = ""

        content = str(
            content
        ).strip()

        if not content:

            print(
                "Gemini returned an empty response."
            )

            return None, (
                "The AI returned an empty response. "
                "Please try again."
            )

        return content, None

    except Exception as error:

        error_text = str(
            error
        )

        print(
            "Gemini API error:",
            repr(error)
        )

        if (
            "429" in error_text
            or "RESOURCE_EXHAUSTED" in error_text
        ):

            return None, (
                "Gemini's free AI limit has been reached "
                "temporarily. Please wait a little and try again."
            )

        if (
            "401" in error_text
            or "403" in error_text
            or "PERMISSION_DENIED" in error_text
        ):

            return None, (
                "Gemini rejected the API request. "
                "Please check the GEMINI_API_KEY on Render."
            )

        if (
            "404" in error_text
            or "NOT_FOUND" in error_text
        ):

            return None, (
                "The configured Gemini model is unavailable. "
                f"Current model: {GEMINI_MODEL}"
            )

        return None, (
            "The Gemini AI service could not process "
            "your request. Please try again."
        )


# ============================================================
# EXTRACT JSON FROM AI RESPONSE
# ============================================================

def extract_json_from_ai_response(
    response
):

    if not response:
        return None

    text = str(
        response
    ).strip()

    # Remove markdown fences.
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    text = text.strip()

    # Direct parse.
    try:

        return json.loads(
            text
        )

    except Exception:
        pass

    # Try object.
    object_match = re.search(
        r"\{.*\}",
        text,
        flags=re.DOTALL
    )

    if object_match:

        try:

            return json.loads(
                object_match.group(0)
            )

        except Exception:
            pass

    # Try array.
    array_match = re.search(
        r"\[.*\]",
        text,
        flags=re.DOTALL
    )

    if array_match:

        try:

            return json.loads(
                array_match.group(0)
            )

        except Exception:
            pass

    return None


# ============================================================
# GENERATE AI STUDY NOTES
# ============================================================

@app.route(
    "/api/generate-notes",
    methods=["POST"]
)
def generate_notes():

    user, error_response = get_current_user()

    if error_response:
        return error_response

    if gemini_client is None:

        return jsonify({
            "error":
                "Gemini is not configured on the server. "
                "Please add GEMINI_API_KEY to your environment variables."
        }), 500

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

    text = text[:60000]

    system_prompt = """
You are StudyMate, an expert academic study assistant.

Turn the supplied study material into SHORT,
clear and high-quality revision notes.

Rules:

1. Use only information in the supplied material.
2. Do not invent facts.
3. Focus on concepts likely to be examined.
4. Use clear headings.
5. Use bullet points where useful.
6. Explain difficult concepts simply.
7. Include important definitions.
8. Include formulas only when they appear in the material.
9. Remove unnecessary repetition.
10. Make the notes easy to revise quickly.
11. Do not mention that you are an AI.
12. Do not create test questions.
"""

    user_prompt = f"""
Create concise revision notes from this study material.

STUDY MATERIAL:

{text}
"""

    notes, ai_error = ask_gemini(
        system_prompt,
        user_prompt,
        json_mode=False
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
# VALIDATE QUESTION
# ============================================================

def clean_test_question(
    question
):

    if not isinstance(
        question,
        dict
    ):

        return None

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
        return None

    if not isinstance(
        options,
        list
    ):

        return None

    if len(options) != 4:
        return None

    cleaned_options = []

    for option in options:

        option = str(
            option
        ).strip()

        if not option:
            return None

        cleaned_options.append(
            option
        )

    try:

        answer = int(
            answer
        )

    except (
        ValueError,
        TypeError
    ):

        return None

    if answer < 0 or answer > 3:

        return None

    return {
        "question":
            question_text,
        "options":
            cleaned_options,
        "answer":
            answer,
        "explanation":
            explanation
    }


# ============================================================
# GENERATE ONE TEST BATCH
# ============================================================

def generate_test_batch(
    text,
    previous_text,
    number_of_questions
):

    system_prompt = f"""
You are StudyMate's examination generator.

Generate EXACTLY {number_of_questions}
high-quality multiple-choice questions from the
supplied study material.

Return ONLY valid JSON.

The JSON must have exactly this structure:

{{
  "questions": [
    {{
      "question": "Question text",
      "options": [
        "Option A",
        "Option B",
        "Option C",
        "Option D"
      ],
      "answer": 0,
      "explanation": "Short explanation."
    }}
  ]
}}

Rules:

1. Generate exactly {number_of_questions} questions.
2. Every question must have exactly 4 options.
3. Only one option must be correct.
4. answer must be an integer from 0 to 3.
5. 0 means option A.
6. 1 means option B.
7. 2 means option C.
8. 3 means option D.
9. Use ONLY information in the study material.
10. Never invent facts.
11. Never repeat a question.
12. Mix easy, medium and difficult questions.
13. Test understanding and important facts.
14. Keep explanations short.
15. Do not use markdown.
16. Do not add comments outside the JSON.
17. Return valid JSON only.
"""

    user_prompt = f"""
Generate {number_of_questions} questions.

STUDY MATERIAL:

{text}

{previous_text}
"""

    response, ai_error = ask_gemini(
        system_prompt,
        user_prompt,
        json_mode=True
    )

    if ai_error:

        return None, ai_error

    parsed = extract_json_from_ai_response(
        response
    )

    if not parsed:

        print(
            "Could not parse Gemini test response."
        )

        print(
            "Gemini response:"
        )

        print(
            str(response)[:5000]
        )

        return None, (
            "The AI returned an invalid test format. "
            "Please try again."
        )

    if isinstance(
        parsed,
        dict
    ):

        questions = parsed.get(
            "questions",
            []
        )

    elif isinstance(
        parsed,
        list
    ):

        questions = parsed

    else:

        questions = []

    if not isinstance(
        questions,
        list
    ):

        return None, (
            "The AI did not return a valid question list."
        )

    valid_questions = []

    for item in questions:

        cleaned = clean_test_question(
            item
        )

        if cleaned:

            valid_questions.append(
                cleaned
            )

    return valid_questions, None


# ============================================================
# GENERATE 30 QUESTION AI TEST
# ============================================================

@app.route(
    "/api/generate-test",
    methods=["POST"]
)
def generate_test():

    user, error_response = get_current_user()

    if error_response:
        return error_response

    if gemini_client is None:

        return jsonify({
            "error":
                "Gemini is not configured on the server. "
                "Please add GEMINI_API_KEY to your environment variables."
        }), 500

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

    text = text[:60000]

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

    previous_text = ""

    if cleaned_previous:

        previous_text = (
            "\n\n"
            "DO NOT REPEAT THESE PREVIOUS QUESTIONS:\n"
            +
            "\n".join(
                f"- {question}"
                for question
                in cleaned_previous[:50]
            )
        )

    print(
        "Starting AI test generation..."
    )

    # ========================================================
    # FIRST BATCH
    # ========================================================

    questions, ai_error = generate_test_batch(
        text,
        previous_text,
        30
    )

    if ai_error:

        print(
            "First test generation attempt failed:",
            ai_error
        )

        return jsonify({
            "error":
                ai_error
        }), 500

    if not questions:

        return jsonify({
            "error":
                "The AI did not generate any valid questions. "
                "Please try again."
        }), 500

    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

    unique_questions = []

    seen_questions = set()

    for question in questions:

        normalized = re.sub(
            r"\s+",
            " ",
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

    print(
        "First attempt produced",
        len(unique_questions),
        "unique valid questions."
    )

    # ========================================================
    # RETRY IF NECESSARY
    # ========================================================

    if len(unique_questions) < 30:

        missing = (
            30
            - len(unique_questions)
        )

        print(
            "Generating",
            missing,
            "additional questions..."
        )

        existing_text = (
            "\n\n"
            "DO NOT REPEAT THESE QUESTIONS:\n"
            +
            "\n".join(
                f"- {q['question']}"
                for q in unique_questions
            )
        )

        retry_questions, retry_error = (
            generate_test_batch(
                text,
                existing_text + previous_text,
                missing
            )
        )

        if retry_error:

            print(
                "Retry failed:",
                retry_error
            )

        else:

            for question in (
                retry_questions or []
            ):

                normalized = re.sub(
                    r"\s+",
                    " ",
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

    # ========================================================
    # FINAL RESULT
    # ========================================================

    if len(unique_questions) < 30:

        print(
            "Final question count:",
            len(unique_questions)
        )

        return jsonify({
            "error":
                (
                    "The AI could not generate all 30 valid "
                    "questions this time. It generated "
                    f"{len(unique_questions)} valid questions. "
                    "Please click Start test again."
                ),
            "generated":
                len(unique_questions)
        }), 500

    unique_questions = (
        unique_questions[:30]
    )

    print(
        "SUCCESS: 30-question test generated."
    )

    return jsonify({
        "message":
            "30-question test generated successfully.",
        "questions":
            unique_questions
    }), 200

# ============================================================
# HANDLE LARGE UPLOADS
# ============================================================

@app.errorhandler(413)
def request_entity_too_large(error):

    return jsonify({
        "error":
            (
                f"The uploaded file is too large. "
                f"Maximum PDF size is "
                f"{MAX_PDF_SIZE_MB} MB."
            )
    }), 413


# ============================================================
# 404
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return jsonify({
        "error":
            "The requested endpoint was not found.",
        "path":
            request.path
    }), 404


# ============================================================
# 405
# ============================================================

@app.errorhandler(405)
def method_not_allowed(error):

    return jsonify({
        "error":
            "The requested method is not allowed."
    }), 405


# ============================================================
# 500
# ============================================================

@app.errorhandler(500)
def internal_server_error(error):

    print(
        "Unhandled server error:",
        repr(error)
    )

    return jsonify({
        "error":
            "An unexpected server error occurred."
    }), 500


# ============================================================
# INITIALIZE DATABASE
# ============================================================

try:

    initialize_pdf_storage()

except Exception as error:

    print(
        "Startup PDF storage initialization error:",
        repr(error)
    )


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )