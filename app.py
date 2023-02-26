import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # get users id
    user_id = session["user_id"]

    # select stock info and users balance
    stocks = db.execute("SELECT symbol, name, price, SUM(shares) AS total_shares FROM portfolio WHERE user_id = ? GROUP BY symbol", user_id)
    cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
    cash = cash[0]["cash"]

    # users balance
    total = cash
    for stock in stocks:
        total += stock["price"] * stock["total_shares"]
        int(total)

    return render_template("index.html", stocks = stocks , cash=usd(cash), total=int(total))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        # get stock ticker from our user
        symbol = request.form.get("symbol").upper()

        # lookup symbol and retunr invalid if ticker doesnt exist
        stock = lookup(symbol)
        if not symbol:
            return apology("invalid stock ticker")
        if not stock:
            return apology("Ivalid symbol")
        # check if user entered a number
        try:
            shares = int(request.form.get("shares"))
        except:
            return apology("Enter a valid number of shares")
        #check for positive number
        if shares <= 0:
            return apology("Enter a valid number of shares")

        # get users balance
        user_id = session["user_id"]
        cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        # get just users money
        cash = cash[0]["cash"]

        # get stocks name, price and total
        stock_name = stock["name"]
        stock_price = stock["price"]
        total = stock_price * shares

        # put users stock to hit portfolio and update his balance
        if cash < total:
            return apology("Insufitient balance")
        else:
            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash - total, user_id)
            db.execute("INSERT INTO portfolio (user_id, name, shares, price, type, symbol) VALUES (?, ?, ?, ?, ?, ?)", user_id, stock_name, shares, stock_price, 'Buy', symbol)

        return redirect("/")
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]
    history = db.execute("SELECT type, symbol,  price, shares, time FROM portfolio WHERE user_id = ?", user_id)

    return render_template("history.html", history=history, usd=usd)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():

    if request.method == "POST":
        # get symbol from html quote page
        symbol = request.form.get("symbol")
        symbol.upper()

        if not symbol:
            return apology("Enter a stock ticker")

        # lookup stock
        stock = lookup(symbol)

        if not stock:
            return apology("enter a valid stock ticker")
        # return stock price
        return render_template("quoted.html", stock=stock, usd=usd)

    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    # register user
    if (request.method == "POST"):
        # get users credentials from html register page
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # chect if user entered id password and confirmation
        if not username:
            return apology("You have to choose a username!")
        elif not password:
            return apology("password is required!")
        elif not confirmation:
            return apology("confirm your password")
        elif password != confirmation:
            return apology("Passwords do not match")

        # hash password
        hash = generate_password_hash(password)

        # check if username in our database
        try:
            # insert username and hash to database
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hash)
            return redirect("/")
        except:
            return apology("username already exists")
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    if request.method == "POST":
        # get user
        user_id = session["user_id"]
        # get number of shares user wants to sell and what stock he wants to sell
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))

        if shares <= 0:
            return apology("Please enter a valid number of shares")

        stock_price = lookup(symbol)['price']
        stock_name = lookup(symbol)['name']
        value = shares * stock_price

        # check how many shares user has
        shares_owned = db.execute("SELECT SUM(shares) FROM portfolio WHERE user_id = ? AND symbol = ? GROUP BY symbol", user_id, symbol)[0]['SUM(shares)']
        # return apology if user doesnt have enough shares of that stock
        if shares_owned < shares:
            return apology("You dont have that many shares.")

        current_cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]['cash']

        # updates users balance and porfoloio
        db.execute("UPDATE users SET cash = ? WHERE id = ?", current_cash + value, user_id)

        db.execute("INSERT INTO portfolio (user_id, name, shares, price, type, symbol) VALUES (?, ?, ?, ?, ?, ?)", user_id, stock_name, -shares, stock_price, 'Sell', symbol)

        return redirect("/")

    else:
        # get user
        user_id = session["user_id"]
        symbols = db.execute("SELECT symbol FROM portfolio WHERE user_id = ? GROUP BY symbol", user_id)
        return render_template("sell.html", symbols=symbols)
Footer
© 2023 GitHub, Inc.
Footer navigation

    Terms
    Privacy
    Security
    Status
    Docs
    Contact GitHub
    Pricing
    API
    Training
    Blog
    About

