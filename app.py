import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secret-key"

DATABASE = "users.db"

# --------------------DB stuff--------------------

#connects to DB for the current req.
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

#closes DB after each req.
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

#initializes/creates DB if it doesn't exist
def init_db():
    with app.app_context():
        get_db().execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)
        get_db().commit()

# -------------------- routes --------------------

#displays homepage and shows user if logged in
@app.route("/")
def index():
    user = None
    if "user_id" in session:
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    return render_template("index.html", user=user)


#lets users create new account, adds user to db upon acc. creation and hashes passwords
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        db = get_db()
        if db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
            flash("Username already taken.")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.")
        else:
            db.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                       (username, generate_password_hash(password)))
            db.commit()
            flash("Account created! Please log in.")
            return redirect(url_for("login"))
    return render_template("register.html")


#lets a user log in, checks to make sure passwords are correct or if user exists
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            return redirect(url_for("index"))
        flash("Invalid username or password.")
    return render_template("login.html")


#logs user out, clears session data and kicks back to home page
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

#runs when file is executed, initializes db and starts the server
if __name__ == "__main__":
    init_db()
    app.run(debug=True)