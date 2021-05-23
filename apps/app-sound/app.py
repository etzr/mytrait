########################## CONFIGURATIONS ##########################
import configparser
import ast
import os
import json
import pickle

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

NOTES_FP = os.path.join(THIS_FOLDER, 'static/audio/notes')
NOTES = os.listdir(NOTES_FP)
NOTES.sort()
NOTES_LOOKUP_FP = os.path.join(THIS_FOLDER, 'static/note_lookup.json')
NOTES_LOOKUP = json.load(open(NOTES_LOOKUP_FP, 'r'))

SCORE_DIST_FP = os.path.join(THIS_FOLDER, 'static/score_distribution.pkl')
SCORE_DIST = pickle.load(open(SCORE_DIST_FP, 'rb'))

########################## HELPER FUNCTIONS ##########################
import collections.abc
from datetime import timedelta
import requests
import numpy as np

def update(d, u):
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = update(d.get(k, {}), v)
        else:
            d[k] = v
    return d

def score2PercRank(score, level):
    return len(np.where(score > np.array(SCORE_DIST[level]))[0]) / 1000

########################### FLASK ################################
from flask import Flask, render_template, redirect, url_for, session, request, jsonify
from flask_dance.contrib.facebook import make_facebook_blueprint, facebook
from flask_dance.contrib.google import make_google_blueprint, google
from flaskext.autoversion import Autoversion

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
    return render_template('login.html', level="Sign In")

@app.route("/profile")
def profile():
    name=session.get('user_name', 'UNKNOWN')
    login_choice=session.get('login-choice')

    # CHURN RESULTS
    image = ["img/tone_deaf.png", "img/insensitive.png", "img/normal.png", "img/sensitive.png", "img/savant.png"]
    ranks = ["Tone Deaf", "Pitch Insensitive", "Normal", "Pitch Sensitive", "Pitch Savant"]
    ranks_num = np.array([15, 35, 70, 90, 100])

    default_score = {
        'listen': {
            '1': [0], '2': [0], '3': [0]
        }
    }
    scores = update(default_score, session.get('scores', {}))['listen']
    agg_score = {"Level {}".format(k): round(np.mean(v)*100, 2) for k,v in scores.items()}
    overall_score = agg_score['Level 1'] * 0.5 + agg_score['Level 2'] * 0.4 + agg_score['Level 3'] * 0.1

    return render_template(
        'profile.html', name=name, login_choice=login_choice, level="Profile",
        scores={k: '{} %'.format(v) for k,v in agg_score.items()},
        overall_score='{} %'.format(overall_score)
    )


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

    return render_template('index.html', name=session.get('user_name', 'UNKNOWN'), level="Introduction")

@app.route("/level1")
def level1():
    return render_template('level1.html', name=session.get('user_name', 'UNKNOWN'), level="Level 1/3")

@app.route("/level2")
def level2():
    return render_template('level2.html', name=session.get('user_name', 'UNKNOWN'), level="Level 2/3")

@app.route("/level3")
def level3():
    return render_template('level3.html', name=session.get('user_name', 'UNKNOWN'), level="Final Level")

@app.route("/report")
def report():
    image = ["img/tone_deaf.png", "img/insensitive.png", "img/normal.png", "img/sensitive.png", "img/savant.png"]
    ranks = ["Tone Deaf", "Pitch Insensitive", "Normal", "Pitch Sensitive", "Pitch Savant"]
    ranks_num = np.array([15, 35, 70, 90, 100])

    default_score = {
        'listen': {
            '1': [0], '2': [0], '3': [0]
        }
    }
    scores = update(default_score, session.get('scores', {}))['listen']
    agg_score = {"Level {}".format(k): round(np.mean(v)*100, 2) for k,v in scores.items()}

    overall_score = agg_score['Level 1'] * 0.5 + agg_score['Level 2'] * 0.4 + agg_score['Level 3'] * 0.1
    evaluation = np.where(ranks_num > overall_score)[0]
    if len(evaluation) == 0:
        image = image[-1]
        evaluation = ranks[-1]
    else:
        image = image[min(evaluation)]
        evaluation = ranks[min(evaluation)]

    return render_template(
        'report.html', 
        name=session.get('user_name', 'UNKNOWN'), 
        level="Report Card",
        evaluation=evaluation,
        scores={k: '{} %'.format(v) for k,v in agg_score.items()},
        overall_score='{} %'.format(overall_score),
        image=image)

##############
# API ROUTES #
##############
C5_IDX = NOTES.index('60.wav')
LL_MIN = 0
UL_MAX = len(NOTES)
@app.route("/api/get_note")
def api_get_note():
    difficulty = float(request.args.get('difficulty', 1))
    difficulty = int(difficulty * 12)

    numOfNotes = int(request.args.get('num', 1))

    ll = 0
    ul = min([C5_IDX + difficulty, UL_MAX])

    if ll != ul:
        note_idx = np.random.choice(range(ll, ul), min([numOfNotes, ul-ll-1]), replace=False)
    else:
        note_idx = C5_IDX

    files = [NOTES[idx] for idx in note_idx]
    notes = [NOTES_LOOKUP[file[:-4]]['note'] for file in files]
    return jsonify({"files":files, "notes":notes})

@app.route("/api/get_score")
def api_get_score():
    correct_note = request.args.get('correct_note')
    guessed_note = request.args.get('guessed_note')

    notes = ["C","C#", "D", "D#", "E", "F", "F#" ,"G", "G#", "A", "A#", "B"]
    numOfNotes = 12
    maxDist = 6

    correct_idx = notes.index(correct_note)
    guessed_idx = notes.index(guessed_note)

    dist_i = (correct_idx - guessed_idx) % numOfNotes
    dist_j = (guessed_idx - correct_idx) % numOfNotes

    raw_score = 1 -  min([dist_i,  dist_j]) / maxDist
    fin_score = score2PercRank(raw_score, 1)

    return jsonify({"score": fin_score})

@app.route("/api/post_multi_score", methods=['POST'])
def api_post_multi_score():
    resp = request.json
    if resp:
        correct_notes = resp.get('correct_notes', [])
        guessed_notes = resp.get('guessed_notes', [])
        guessed_notes = guessed_notes[-len(correct_notes):]
    else:
        return jsonify({"score": 0})
    
    notes = ["C","C#", "D", "D#", "E", "F", "F#" ,"G", "G#", "A", "A#", "B"]
    numOfNotes = 12
    maxDist = 6

    correct_idxs = [notes.index(correct_note) for correct_note in correct_notes]
    guessed_idxs = [notes.index(guessed_note) for guessed_note in guessed_notes]

    dist = []
    for c_idx in correct_idxs:
        _dist = []
        for g_idx in guessed_idxs:  
            dist_i = (c_idx - g_idx) % numOfNotes
            dist_j = (g_idx - c_idx) % numOfNotes
            _dist.append(min([dist_i,  dist_j]))        
        dist.append(min(_dist))

    raw_score = 1 -  np.mean(dist)/ maxDist
    fin_score = score2PercRank(raw_score, len(correct_idxs))
    return jsonify({"score": fin_score})

@app.route("/api/submit_scores", methods=['POST'])
def api_submit_scores():
    if 'scores' not in session:
        session['scores'] = dict()
    session['scores'] = update(session['scores'], request.json)
    return jsonify({"status": "submitted"})

@app.route("/api/report_score")
def api_report_score():
    return jsonify(session.get('scores', {}))

if __name__ == '__main__':
    app.run(debug=DEBUG, ssl_context='adhoc')