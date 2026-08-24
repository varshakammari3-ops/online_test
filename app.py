from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = "online_exam_secret_key"

DATABASE = "exam.db"


# =========================
# DATABASE CONNECTION
# =========================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# =========================
# INITIALIZE DATABASE
# =========================

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Students table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # Questions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            answer TEXT NOT NULL
        )
    """)

    # Results table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    """)

    conn.commit()
    conn.close()


# =========================
# HOME PAGE
# =========================

@app.route("/")
def index():
    return render_template("index.html")


# =========================
# STUDENT REGISTER
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        hashed_password = generate_password_hash(password)

        conn = get_db()

        try:
            conn.execute(
                "INSERT INTO students (name, email, password) VALUES (?, ?, ?)",
                (name, email, hashed_password)
            )

            conn.commit()
            conn.close()

            flash("Registration successful. Please login.")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            conn.close()
            flash("Email already registered.")
            return redirect(url_for("register"))

    return render_template("register.html")


# =========================
# STUDENT LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()

        student = conn.execute(
            "SELECT * FROM students WHERE email = ?",
            (email,)
        ).fetchone()

        conn.close()

        if student and check_password_hash(student["password"], password):

            session["student_id"] = student["id"]
            session["student_name"] = student["name"]

            return redirect(url_for("student_dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


# =========================
# STUDENT DASHBOARD
# =========================

@app.route("/student/dashboard")
def student_dashboard():

    if "student_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "student_dashboard.html",
        name=session["student_name"]
    )


# =========================
# START EXAM
# =========================

@app.route("/exam")
def exam():

    if "student_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    # Check if student already attempted the exam
    existing_result = conn.execute(
        "SELECT id FROM results WHERE student_id = ?",
        (session["student_id"],)
    ).fetchone()

    if existing_result:
        conn.close()
        flash("You have already attempted the exam.")
        return redirect(url_for("student_dashboard"))

    questions = conn.execute(
        "SELECT * FROM questions"
    ).fetchall()

    conn.close()

    if len(questions) == 0:
        flash("No questions available.")
        return redirect(url_for("student_dashboard"))

    return render_template(
        "exam.html",
        questions=questions
    )


# =========================
# SUBMIT EXAM
# =========================

@app.route("/submit_exam", methods=["POST"])
def submit_exam():

    if "student_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    questions = conn.execute(
        "SELECT * FROM questions"
    ).fetchall()

    score = 0

    for question in questions:

        selected_answer = request.form.get(
            f"question_{question['id']}"
        )

        if selected_answer == question["answer"]:
            score += 1

    total = len(questions)

    conn.execute(
        """
        INSERT INTO results (student_id, score, total)
        VALUES (?, ?, ?)
        """,
        (session["student_id"], score, total)
    )

    conn.commit()
    conn.close()

    return render_template(
        "result.html",
        score=score,
        total=total
    )


# =========================
# STUDENT RESULT HISTORY
# =========================

@app.route("/my_results")
def my_results():

    if "student_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    results = conn.execute(
        """
        SELECT * FROM results
        WHERE student_id = ?
        ORDER BY date DESC
        """,
        (session["student_id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "result.html",
        history=results,
        score=None,
        total=None
    )


# =========================
# STUDENT LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("index"))


# ==================================================
# ADMIN LOGIN
# ==================================================

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


@app.route("/admin", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:

            session["admin"] = True

            return redirect(url_for("admin_dashboard"))

        flash("Invalid admin username or password.")

    return render_template("admin_login.html")


# =========================
# ADMIN DASHBOARD
# =========================

@app.route("/admin/dashboard")
def admin_dashboard():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    conn = get_db()

    questions = conn.execute(
        "SELECT * FROM questions"
    ).fetchall()

    results = conn.execute(
        """
        SELECT
            results.id,
            students.name,
            students.email,
            results.score,
            results.total,
            results.date
        FROM results
        JOIN students
        ON results.student_id = students.id
        ORDER BY results.date DESC
        """
    ).fetchall()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        questions=questions,
        results=results
    )


# =========================
# ADD QUESTION
# =========================

@app.route("/admin/add_question", methods=["GET", "POST"])
def add_question():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    if request.method == "POST":

        question = request.form["question"]
        option_a = request.form["option_a"]
        option_b = request.form["option_b"]
        option_c = request.form["option_c"]
        option_d = request.form["option_d"]
        answer = request.form["answer"]

        conn = get_db()

        conn.execute(
            """
            INSERT INTO questions
            (question, option_a, option_b, option_c, option_d, answer)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                question,
                option_a,
                option_b,
                option_c,
                option_d,
                answer
            )
        )

        conn.commit()
        conn.close()

        flash("Question added successfully.")

        return redirect(url_for("admin_dashboard"))

    return render_template("add_question.html")


# =========================
# DELETE QUESTION
# =========================

@app.route("/admin/delete_question/<int:question_id>")
def delete_question(question_id):

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    conn = get_db()

    conn.execute(
        "DELETE FROM questions WHERE id = ?",
        (question_id,)
    )

    conn.commit()
    conn.close()

    flash("Question deleted.")

    return redirect(url_for("admin_dashboard"))


# =========================
# ADMIN LOGOUT
# =========================

@app.route("/admin/logout")
def admin_logout():

    session.pop("admin", None)

    return redirect(url_for("index"))


# =========================
# RUN APPLICATION
# =========================

if __name__ == "__main__":

    init_db()

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True
    )
