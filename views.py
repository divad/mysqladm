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
import mysqladm.core
import mysqladm.errors
from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash
import kerberos
import pwd
import grp

################################################################################
#### HOME PAGE

@app.route('/')
def default():
	if 'username' in session:
		return redirect(url_for('isotope'))
	else:
		next = request.args.get('next',default=None)
		return render_template('default.html', active='default',next=next)

################################################################################
#### ABOUT 

@app.route('/about')
@mysqladm.core.login_required
def about():
	return render_template('about.html', active='about')

################################################################################
#### STATS

@app.route('/stats')
@mysqladm.core.login_required
def stats():
	## Load the dictionary based cursor
	cur = g.db.cursor()

	## Execute a SQL select
	cur.execute("SELECT COUNT(*) FROM `servers`");
	servers_row = cur.fetchone()
	cur.execute("SELECT COUNT(*) FROM `databases`");
	databases_row = cur.fetchone()
	cur.execute("SELECT `hostname`, `password` FROM `servers`");

	# Average up servers
	count = 0
	load_sum = 0.0
	capacity_size = 0
	usage_size = 0
	row = cur.fetchone()
	while row != None:
		try:
			# Query the server for stats
			json_response = mysqladm.core.msg_node(row[0], row[1], 'stats')

			# If we have a valid response
			if 'status' in json_response and json_response['status'] == 0 and 'load_avg_1' in json_response:
				count         = count + 1
				load_sum      = load_sum + float(json_response['load_avg_1'])
				capacity_size = capacity_size + json_response['disk_capacity']
				usage_size    = usage_size + (json_response['disk_capacity'] - json_response['disk_free'])
		except Exception, e:
			app.logger.warn(str(e))
			# We ignore exceptions here
			pass

		# Iterate to the next row
		row = cur.fetchone()

	# Calculate the load average
	if count > 0:
		loadavg = load_sum / count
	else:
		loadavg = 0

	return render_template('stats.html', active='stats', servers=servers_row[0], databases=databases_row[0], loadavg="%.2f" % loadavg, capacity=capacity_size, usage=usage_size)

################################################################################
#### LOGIN

@app.route('/login', methods=['GET','POST'])
def login():

	try:
		## Check password with kerberos
		kerberos.checkPassword(request.form['username'], request.form['password'], app.config['KRB5_SERVICE'], app.config['KRB5_DOMAIN'])
	except kerberos.BasicAuthError as e:
		flash('<strong>Error</strong> - Incorrect username and/or password','alert-danger')
		return redirect(url_for('default'))
	except kerberos.KrbError as e:
		flash('<strong>Unexpected Error</strong> - Kerberos Error: ' + e.__str__(),'alert-danger')
		return redirect(url_for('default'))
	except kerberos.GSSError as e:
		flash('<strong>Unexpected Error</strong> - GSS Error: ' + e.__str__(),'alert-danger')
		return redirect(url_for('default'))
	except Exception as e:
		mysqladm.errors.fatal(e)

	## Ensure user is in mysqladm management group
	group = grp.getgrnam(app.config['ACCESS_GROUP'])
	if not request.form['username'] in group.gr_mem:
		flash('<strong>Access Denied</strong> - You must be a member of the Linux group ' + app.config['ACCESS_GROUP'] + ' to use this service','alert-danger')
		return redirect(url_for('default'))

	## Set logged in (if we got this far)
	session['logged_in'] = True
	session['username'] = request.form['username']

	## Check if the user selected "Log me out when I close the browser"
	permanent = request.form.get('sec',default="")

	## Set session as permanent or not
	if permanent == 'sec':
		session.permanent = True
	else:
		session.permanent = False

	## Set defaults for hidden files
	session['hidden_files'] = 'hide'

	## Log a successful login
	app.logger.info('User "' + session['username'] + '" logged in from "' + request.remote_addr + '" using ' + request.user_agent.string)

	## determine if "next" variable is set (the URL to be sent to)
	next = request.form.get('next',default=None)

	if next == None:
		return redirect(url_for('about'))
	else:
		return redirect(next)

################################################################################
#### LOGOUT

@app.route('/logout')
@mysqladm.core.login_required
def logout():
	app.logger.info('User "' + session['username'] + '" logged out from "' + request.remote_addr + '" using ' + request.user_agent.string)

	session.pop('logged_in', None)
	session.pop('username', None)

	flash('You have been logged out. Goodbye.','alert-success')

	return redirect(url_for('default'))
