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
import re
import pwd
import grp

################################################################################

def db_connect():
	"""This function connects to the DB via parameters stored in the config file.
	"""
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
			flash('You must be logged in to do that!','alert-danger')
			args = url_encode(request.args)
			return redirect(url_for('default', next=request.script_root + request.path + "?" + args))
		return f(*args, **kwargs)
	return decorated_function
	
################################################################################

def admin_required(f):
	"""This is a decorator function that when called ensures the user is an admin.
	Usage is as such: @bargate.core.admin_required
	"""
	@wraps(f)
	def decorated_function(*args, **kwargs):
		if session.get('admin',False) is False:
			flash('You must be an administrator to do that!','alert-danger')
			return redirect(url_for('database_list'))
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

			### the user cannot have accidentally triggered this (?)
			### so just throw a 403.
			abort(403)

################################################################################

@app.teardown_request
def teardown_request(exception):
	"""This function closes the DB connection as the app stops.
	"""
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
	"""This is very crude password generator.
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

def msg_node(serverobj, function, **kwargs):
	"""This function communicates via HTTPS to a mysqlagent
	running on a mysql server. Serverobj is a hash containing hostname,
	password and optionally an sslverify boolean.
	"""
	
	## create a payload to send to the server
	payload = {'function': function, 'agent_password': serverobj['password']}

	## Put the keyword arguments into the payload
	for arg in kwargs:
		payload[arg] = kwargs[arg]

	## Shall we verify the SSL cert of the node?
	if 'sslverify' in serverobj:
		verify = bool(serverobj['sslverify'])
	else:
		verify = bool(app.config['AGENT_SSL_VERIFY_DEFAULT'])
		
	if verify == False:
		if app.config['AGENT_SSL_VERIFY_ALERT']:
			flash('Warning: Connected to ' + serverobj['hostname'] + ' without SSL verification enabled','alert-warning')
		
	app.logger.debug("Messaging " + serverobj['hostname'] + " with ssl verify set to: " + str(verify))


	## Use SSL certificate authority bundle file from config file
	if verify:
		verify = app.config['AGENT_SSL_VERIFY_CA_FILE']
	
	## Send request
	r = requests.post('https://' + serverobj['hostname'] + ':1337/', data=payload, verify=verify)
	
	## Deal with the response
	if r.status_code == requests.codes.ok:
		return json.loads(r.text)
	else:
		r.raise_for_status()

################################################################################

def ut_to_string(ut):
	"""Converts unix time to a formatted string for human consumption
	Used by smb.py for turning fstat results into human readable dates.
	"""
	return datetime.datetime.fromtimestamp(int(ut)).strftime('%Y-%m-%d %H:%M:%S %Z')
	
################################################################################

def is_valid_hostname(hostname):
	"""Validated a string as a hostname.
	"""
	
	if len(hostname) > 255:
		return False
		
	if hostname[-1] == ".":
		hostname = hostname[:-1] # strip exactly one dot from the right, if present
		
	allowed = re.compile("(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
	return all(allowed.match(x) for x in hostname.split("."))
    
def is_valid_desc(desc):
	if re.search(r'^[A-Za-z0-9_\s\-\.\&\@\\/\:]*$', desc) == None:
		return False
	return True
	
def is_valid_env(str):
	
	if str == 'Production':
		return True
	elif str == 'Pre-Production':
		return True
	elif str == 'Development':
		return True
	elif str == 'Training':
		return True
	elif str == 'Other':
		return True

	return False

def is_valid_username(username):
	"""Validate a string as a username
	"""
	
	try:
		pwd.getpwnam(username)
	except KeyError as ex:
		return False
		
	return True

def get_user_details(username):
	
	try:
		return pwd.getpwnam(username)
	except KeyError as ex:
		return None

def get_group_name(gid):
	
	try:
		group = grp.getgrgid(gid)	
		return group.gr_name
	except KeyError as ex:
		return "Unknown - GID not found"
