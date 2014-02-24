#!/usr/bin/python
#
# This file is part of mysqladm.
#
# mysqladm is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# mysqladm is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with mysqladm.  If not, see <http://www.gnu.org/licenses/>.

from mysqladm import app
import mysqladm.errors
from werkzeug.urls import url_encode	
from flask import Flask, g, request, redirect, session, url_for, abort, render_template, flash
from functools import wraps
import random
import base64
import os
import string
import json
import MySQLdb as mysql
import requests 
import datetime

def db_connect():
	conn = mysql.connect(app.config['DB_SERV'],app.config['DB_USER'],app.config['DB_PASS'],app.config['DB_NAME'])
	conn.errorhandler = mysqladm.errors.db_error_handler
	return conn

################################################################################

def login_required(f):
	"""This is a decorator function that when called ensures the user has logged in.
	Usage is as such: @bargate.core.login_required
	"""
	@wraps(f)
	def decorated_function(*args, **kwargs):
		if session.get('logged_in',False) is False:
			flash('<strong>Oops!</strong> You must login first.','alert-danger')
			## TODO take the next code from sysman - much improved over this.
			args = url_encode(request.args)
			return redirect(url_for('default', next=request.script_root + request.path + "?" + args))
		return f(*args, **kwargs)
	return decorated_function

################################################################################

@app.before_request
def before_request():
	"""This function is run before the request is handled by Flask. At present it checks
	to make sure a valid CSRF token has been supplied if a POST request is made and 
	connects to the database
	"""
	## Connect to the database
	g.db = db_connect()

	## Check CSRF key is valid
	if request.method == "POST":
		## check csrf token is valid
		token = session.get('_csrf_token')
		if not token or token != request.form.get('_csrf_token'):
			if 'username' in session:
				app.logger.warning('CSRF protection alert: %s failed to present a valid POST token',session['username'])
			else:
				app.logger.warning('CSRF protection alert: a non-logged in user failed to present a valid POST token')

			### the user cannot have accidentally triggered this
			### so just throw a 403.
			abort(403)

################################################################################

@app.teardown_request
def teardown_request(exception):
	db = getattr(g, 'db', None)
	if db is not None:
		db.close()

################################################################################

def generate_csrf_token():
	"""This function is used in __init__.py to generate a CSRF token for use
	in templates.
	"""

	if '_csrf_token' not in session:
		session['_csrf_token'] = pwgen(32)
	return session['_csrf_token']

################################################################################

def pwgen(length=16):
	"""This is crude password generator.
	"""

	urandom = random.SystemRandom()
	alphabet = string.ascii_letters + string.digits
	return str().join(urandom.choice(alphabet) for _ in range(length))

################################################################################

def poperr_set(title,message):
	"""This function will create and show a
	popup dialog error on the next time a page
	is loaded. Use this before running a redirect.
	"""

	session['popup_error'] = True
	session['popup_error_title'] = title
	session['popup_error_message'] = message

################################################################################

def poperr_clear():
	"""This function clears any currently set error popup. It is only to be
	called from inside a jinja template
	"""

	session['popup_error'] = False
	session['popup_error_title'] = ""
	session['popup_error_message'] = ""
	## this function is called inside jinja templates.
	## if you return nothing, it prints "None", so we return empty string!
	return ""

################################################################################

def msg_node(hostname, agent_password, function, **kwargs):
	payload = {'function': function, 'agent_password': agent_password}

	# Put the keyword arguments into the payload
	for arg in kwargs:
		payload[arg] = kwargs[arg]

	## TODO turn verification back on once SSL in place
	r = requests.post('https://' + hostname + ':1337/', data=payload, verify=app.config['AGENT_SSL_VERIFY'])
	if r.status_code == requests.codes.ok:
		return json.loads(r.text)
	else:
		r.raise_for_status()

		## throw a node exception

def ut_to_string(ut):
	"""Converts unix time to a formatted string for human consumption
	Used by smb.py for turning fstat results into human readable dates.
	"""
	return datetime.datetime.fromtimestamp(int(ut)).strftime('%Y-%m-%d %H:%M:%S %Z')
