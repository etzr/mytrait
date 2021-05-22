import configparser
import ast
import os
THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))
config_fp = os.path.join(THIS_FOLDER, 'config.ini')

config = configparser.ConfigParser()
config.read(config_fp)

SECRET_KEY = ast.literal_eval(config.get("flask", "SECRET_KEY"))
DEBUG = ast.literal_eval(config.get("flask", "DEBUG"))
SESSION_LIFETIME_DAYS = ast.literal_eval(config.get('flask', 'SESSION_LIFETIME_DAYS'))

FACEBOOK_OAUTH_CLIENT_ID = ast.literal_eval(config.get("facebook", "FACEBOOK_OAUTH_CLIENT_ID"))
FACEBOOK_OAUTH_CLIENT_SECRET = ast.literal_eval(config.get("facebook", "FACEBOOK_OAUTH_CLIENT_SECRET"))

GOOGLE_OAUTH_CLIENT_ID = ast.literal_eval(config.get("google", "GOOGLE_OAUTH_CLIENT_ID"))
GOOGLE_OAUTH_CLIENT_SECRET = ast.literal_eval(config.get("google", "GOOGLE_OAUTH_CLIENT_SECRET"))

from flask import Flask, render_template, redirect, url_for, session, request, Blueprint
from flask_dance.contrib.facebook import make_facebook_blueprint, facebook
from flask_dance.contrib.google import make_google_blueprint, google
from flaskext.autoversion import Autoversion
from datetime import timedelta
import requests

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=SESSION_LIFETIME_DAYS)
app.autoversion = True
Autoversion(app)

###################
# AUTHENTICATIONS #
###################
# FACEBOOK OAUTH
app.config["FACEBOOK_OAUTH_CLIENT_ID"] = FACEBOOK_OAUTH_CLIENT_ID
app.config["FACEBOOK_OAUTH_CLIENT_SECRET"] = FACEBOOK_OAUTH_CLIENT_SECRET
facebook_bp = make_facebook_blueprint()
app.register_blueprint(facebook_bp, url_prefix="/login")

app.config["GOOGLE_OAUTH_CLIENT_ID"] = GOOGLE_OAUTH_CLIENT_ID
app.config["GOOGLE_OAUTH_CLIENT_SECRET"] = GOOGLE_OAUTH_CLIENT_SECRET
google_bp = make_google_blueprint()
app.register_blueprint(google_bp, url_prefix="/login")


WEB_ROUTES = ['profile', 'index', 'level1', 'level2']
@app.before_request
def auth(): 
    if 'login-choice' not in session and request.endpoint in WEB_ROUTES:
        return redirect(url_for("login_choice"))

    if session.get('login-choice') == 'fb':
        if request.endpoint in WEB_ROUTES and not facebook.authorized:
            return redirect(url_for("login_choice"))

    if session.get('login-choice') == 'gg':
        if request.endpoint in WEB_ROUTES and not google.authorized:
            return redirect(url_for("login_choice"))

################
# ADMIN ROUTES #
################
@app.route("/login_choice")
def login_choice():
    return render_template('login.html')

@app.route("/profile")
def profile():
    name=session.get('user_name', 'UNKNOWN')
    login_choice=session.get('login-choice')

    return render_template('profile.html', name=name, login_choice=login_choice)


#################
# WEBAPP ROUTES #
#################
@app.route("/")
@app.route("/start")
def index():
    if session.get('login-choice') == 'gg':
        resp = google.get("/oauth2/v1/userinfo")
        """in case user removed app from facebook, but session still cached as facebook.authorized == True"""
        if google.authorized and not resp.ok:
            return redirect(url_for("gg_login"))

        user_info = resp.json()
        session['user_name'] = user_info['name']
        session['user_id'] = user_info['id']

    if session.get('login-choice') == 'fb':
        resp = facebook.get("/me")
        """in case user removed app from facebook, but session still cached as facebook.authorized == True"""
        if facebook.authorized and not resp.ok:
            return redirect(url_for("fb_login"))

        user_info = resp.json()
        session['user_name'] = user_info['name']
        session['user_id'] = user_info['id']

    return render_template('index.html', name=session.get('user_name', 'UNKNOWN'))#"You are {name} on Facebook".format(name=session.get('user_name', 'UNKNOWN'))
    
@app.route("/level1")
def level1():
    return "You are {name} on Facebook".format(name=session.get('user_name', 'UNKNOWN'))

@app.route("/level2")
def level2():
    return "You are {name} on Facebook".format(name=session.get('user_name', 'UNKNOWN'))

################
# LOGIN ROUTES #
################
@app.route('/fb_login')
def fb_login():
    session['login-choice'] = 'fb'
    if not facebook.authorized:
        return redirect(url_for("facebook.login"))
    return redirect(url_for('index'))


@app.route('/gg_login')
def gg_login():
    session['login-choice'] = 'gg'
    if not google.authorized:
        return redirect(url_for("google.login"))
    return redirect(url_for('index'))


@app.route('/remove_app')
def remove_app():
    if session.get('login-choice') == 'fb':
        access_token = facebook_bp.token["access_token"]
        user_id = session.get('user_id')
        url = "https://graph.facebook.com/{user_id}/permissions?access_token={access_token}"
        requests.delete(url.format(user_id=user_id, access_token=access_token))

    if session.get('login-choice') == 'gg':
        access_token = google_bp.token["access_token"]
        user_id = session.get('user_id')
        print(user_id)
        requests.post('https://oauth2.googleapis.com/revoke',
            params={'token': access_token},
            headers = {'content-type': 'application/x-www-form-urlencoded'})
    session.clear()
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=DEBUG, ssl_context='adhoc')