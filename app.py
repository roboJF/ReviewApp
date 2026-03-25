import sqlite3
import requests
from google import genai
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secret-key"

DATABASE = "bookie.db"
GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"
GOOGLE_BOOKS_API_KEY = "books-api-key"
GEMINI_API_KEY = "gemini-api-key"

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

#initializes/creates DB if it doesn't exist, the 2 tables are the users table and the reviews table
def init_db():
    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id TEXT NOT NULL,
                book_title TEXT NOT NULL,
                book_author TEXT,
                rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                review_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, book_id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        db.commit()

# -------------------- authentication --------------------

#retrieves the currently logged in user
def current_user():
    if "user_id" not in session:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()

#makes it so that users are restricted from doing certain things unless logged in (leaving reviews)
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# -------------------- routes --------------------

#displays homepage and shows user if logged in
@app.route("/")
def index():
    return render_template("index.html", user=current_user())

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

#uses google books API to search for books based on the given query, i set it to 5 results to not max out the free API keys but it can be changed if needed
@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    results = []
    if query:
        try:
            resp = requests.get(GOOGLE_BOOKS_API, params={"q": query, "maxResults": 5, "key": GOOGLE_BOOKS_API_KEY}, timeout=8)
            resp.raise_for_status()
            for item in resp.json().get("items", []):
                info = item.get("volumeInfo", {})
                results.append({
                    "id":      item["id"],
                    "title":   info.get("title", "Unknown Title"),
                    "authors": ", ".join(info.get("authors", ["Unknown Author"])),
                    "year":    info.get("publishedDate", "")[:4],
                })
        except requests.exceptions.RequestException as e:
            flash(f"Search error: {e}")
    return render_template("search.html", results=results, query=query, user=current_user())

#retrieves book info using google books API using the book ID from search, also displays reviews regardless of login status
@app.route("/book/<book_id>")
def book(book_id):
    try:
        resp = requests.get(f"{GOOGLE_BOOKS_API}/{book_id}", params={"key": GOOGLE_BOOKS_API_KEY}, timeout=8)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        flash(f"Could not load book: {e}")
        return redirect(url_for("index"))
    info = resp.json().get("volumeInfo", {})
    book_data = {
        "id":          book_id,
        "title":       info.get("title", "Unknown Title"),
        "authors":     ", ".join(info.get("authors", ["Unknown Author"])),
        "year":        info.get("publishedDate", "")[:4],
        "description": info.get("description", ""),
        "pages":       info.get("pageCount", ""),
    }
    db = get_db()
    reviews = db.execute("""
        SELECT r.*, u.username FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.book_id = ? ORDER BY r.created_at DESC
    """, (book_id,)).fetchall()
    user_review = None
    if "user_id" in session:
        user_review = db.execute(
            "SELECT * FROM reviews WHERE user_id = ? AND book_id = ?",
            (session["user_id"], book_id)
        ).fetchone()
    return render_template("book.html", book=book_data, reviews=reviews, user_review=user_review, user=current_user())


#lets users write/edit and post reviews if logged in, adds review to DB afterwards
@app.route("/review/<book_id>", methods=["POST"])
@login_required
def write_review(book_id):
    rating      = int(request.form["rating"])
    review_text = request.form["review_text"].strip()
    book_title  = request.form["book_title"]
    book_author = request.form["book_author"]
    db = get_db()
    existing = db.execute(
        "SELECT id FROM reviews WHERE user_id = ? AND book_id = ?",
        (session["user_id"], book_id)
    ).fetchone()
    if existing:
        db.execute("UPDATE reviews SET rating=?, review_text=? WHERE id=?",
                   (rating, review_text, existing["id"]))
    else:
        db.execute(
            "INSERT INTO reviews (user_id, book_id, book_title, book_author, rating, review_text) VALUES (?,?,?,?,?,?)",
            (session["user_id"], book_id, book_title, book_author, rating, review_text)
        )
    db.commit()
    flash("Review saved.")
    return redirect(url_for("book", book_id=book_id))

#allows users to delete reviews if a review has been posted, and if they're logged in as well
@app.route("/review/delete/<int:review_id>", methods=["POST"])
@login_required
def delete_review(review_id):
    db = get_db()
    review = db.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
    if review and review["user_id"] == session["user_id"]:
        book_id = review["book_id"]
        db.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
        db.commit()
        return redirect(url_for("book", book_id=book_id))
    return redirect(url_for("index"))

#uses gemini api (gemini flash 2.5) to get book recommendations based on the last 5 reviews made, its slow but does work
@app.route("/recommendations")
@login_required
def recommendations():
    db = get_db()
    recent_reviews = db.execute("""
        SELECT book_title, book_author, rating, review_text
        FROM reviews
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 5
    """, (session["user_id"],)).fetchall()
    if not recent_reviews:
        flash("You need to write at least one review before getting recommendations.")
        return redirect(url_for("index"))
    review_lines = []
    for r in recent_reviews:
        line = f'- "{r["book_title"]}" by {r["book_author"]} — rated {r["rating"]}/5'
        if r["review_text"]:
            line += f': "{r["review_text"]}"'
        review_lines.append(line)
    reviews_text = "\n".join(review_lines)
    prompt = f"""Based on the following book reviews a user has written, suggest 5 books they might enjoy.
For each recommendation give the title, author, and a one sentence reason why they'd like it based on their reading history.
Their recent reviews:
{reviews_text}
Format your response as a simple numbered list like:
1. Title by Author — Reason
2. ...and so on."""
    recs_text = None
    error = None
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        recs_text = response.text
    except Exception as e:
        error = str(e)
    return render_template("recommendations.html",
                           recent_reviews=recent_reviews,
                           recs_text=recs_text,
                           error=error,
                           user=current_user())

#runs when file is executed, initializes db and starts the server
if __name__ == "__main__":
    init_db()
    app.run(debug=True)