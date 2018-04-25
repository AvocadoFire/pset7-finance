import os
import datetime
import time

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import *


# Ensure environment variable is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Think dicts in a list...
    txns = db.execute("SELECT symbol, shares FROM transactions WHERE user_id = :id", id=session["user_id"])

    # Add the symbols of the stocks on hand to a list
    basket = get_basket(txns)

    # Build a portfolio of the stocks on hand
    portfolio = get_portfolio(basket)

    gtotal = 0.0
    for i in range(len(portfolio)):
        for j in range(len(portfolio[i])):
            # Get current symbol fields
            symbol = lookup(portfolio[i][j]["symbol"])
            # Assign price to portfolio
            portfolio[i][j].update({"price" : symbol["price"]})
            # Calculate current value of each holding, remove any 0'd lines
            portfolio[i][j].update({"total" : symbol["price"] * portfolio[i][j]["shares"]})
            # GranD total = cash + value of stocks
            gtotal = gtotal + portfolio[i][j]["total"]
            # Transfer the basket to the portfolio


    # Get users balance
    cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
    cash = cash[0]["cash"]
    # Get total balance
    total = cash + gtotal


    # Pass: stocks, # shares, price per stock, total value of each holding, cash bal, g-total
    return render_template("index.html",portfolio=portfolio, cash=cash, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        symbol = lookup(request.form.get("symbol"))
        # Get and validate symbol
        if symbol == None:
            return apology("invalid symbol", 400)

        # Get and validate shares
        shares = request.form.get("shares")
        try:
            shares = float(shares)
        except ValueError:
            return apology("Not a number", 400)

        # Ensure a number is entered and it is positve
        if request.form.get("shares") == None or float(request.form.get("shares")) < 0:
            return apology("invalid number", 400)

        # Check that the number entered is whole
        if is_whole(request.form.get("shares")) == False:
            return apology("must be a whole number", 400)

        # Get cash on hand
        cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])

        # Check if user can afford to buy requested shares
        if cash[0]["cash"] - (symbol["price"] * shares) < 0:
            return apology("Cannot Afford",400)

        # Add shares to DB and update cash etc.
        else:
            db.execute("INSERT INTO transactions (symbol, user_id, at_price, time_date,shares) \
            VALUES (:symbol, :user_id, :at_price, :time_date,:shares)", \
            symbol=symbol["symbol"],
            user_id=session["user_id"],
            at_price=float(symbol["price"]),
            time_date=datetime.datetime.now().strftime("%d-%m-%y %H:%M"),
            shares=request.form.get("shares"))

            # Update user's cash
            db.execute("UPDATE users SET cash = cash - :price WHERE id = :user_id", \
            price=float(symbol["price"]) * float(request.form.get("shares")), user_id=session["user_id"])

            remaining_cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])

            return render_template("bought.html",symbol=symbol["symbol"], price=float(symbol["price"]), value_of_holding=shares * float(symbol["price"]), cash=float(remaining_cash[0]["cash"]))


    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Get the
    txns = db.execute("SELECT symbol, shares FROM transactions WHERE user_id = :id",id=session["user_id"])

    # Add the symbols of the stocks on hand to a list
    basket = get_basket(txns)
    portfolio = get_portfolio(basket)

    # Pass the template the portfolio
    return render_template("history.html",portfolio=portfolio)


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect(url_for("index"))

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect(url_for("index"))


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        quote = lookup(request.form.get("symbol"))

        if quote == None:
            return apology("invalid ticker",400)
        else:
            return render_template("quoted.html", symbol=quote['symbol'], price=usd(quote['price']))

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    # Forget any user_id OK
    session.clear()

    # User reached route via POST (as by submitting a form via POST) OK
    if request.method == "POST":

        user = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Check for blank fields
        if not user or not password or not confirmation:
            return apology("blank fields", 400)

        # Ensure passwords match
        elif not password == confirmation:
            return apology("passwords do not match", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username=:user", user=user)


        # Ensure username exists and password is correct
        if len(rows) == 1:
            return apology("username already exists ", 400)

        # Insert new user into database, hash the pw
        elif len(rows) == 0:
            db.execute("INSERT INTO users (username,hash) VALUES (:username, :hash)", \
            username=user,hash=generate_password_hash(password))

            # Re-direct to log in screen
            return redirect(url_for("index"))

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Reached via GET
    if request.method == "GET":
        txns = db.execute("SELECT symbol, shares FROM transactions WHERE user_id = :id",id=session["user_id"])
        basket = get_basket(txns)
        return render_template("sell.html",list=basket)

    # Reached via POST
    else:

        # Re-direct to index
        flash('Sold!')
        return redirect(url_for("index"))

def errorhandler(e):
    """Handle error"""
    return apology(e.name, e.code)


# listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
