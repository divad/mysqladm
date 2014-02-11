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
import MySQLdb as mysql
import requests


def get_server_by_hostname(hostname):
	## Load the dictionary based cursor
	cur = g.db.cursor(mysql.cursors.DictCursor)

	## Execute a SQL select
	cur.execute("SELECT `id`, `hostname`, `alias`, `desc`, `state`, `password` FROM `servers` WHERE `hostname` = %s", (hostname))

	## Get results
	return cur.fetchone()

################################################################################
#### LIST SERVERS

@app.route('/servers')
def server_list():
	## Load the dictionary based cursor
	cur = g.db.cursor(mysql.cursors.DictCursor)

	## Execute a SQL select
	cur.execute("SELECT `id`, `hostname`, `alias`, `desc`, `state`, `password` FROM `servers`")

	## Get results
	rows = cur.fetchall()

	## Iterate through each database and get the statistics
	for row in rows:
		## TODO something???
		try:
			json_response = mysqladm.core.msg_node(row['hostname'], row['password'], 'list')

			if 'status' in json_response:
				if json_response['status'] == 0 and 'list' in json_response:
					row['databases'] = len(json_response['list'])
				else:
					row['databases'] = 'Error: JSON Error returned code: ' + str(json_response['status']) + " message: " + json_response['error']
			else:
				row['databases'] = 'Error: Invalid JSON response'
		except requests.exceptions.RequestException as e:
			row['databases'] = 'Error: ' + str(e)

		## Add the link to the server
		row['link'] = url_for('server_view', server_name=row['hostname'])

	return render_template('servers.html', active='servers',rows=rows)

################################################################################
#### MANAGE SERVER

@app.route('/server/<server_name>', methods=['GET','POST'])
def server_view(server_name):
	if request.method == 'GET':
		## Load the dictionary based cursor
		cur = g.db.cursor(mysql.cursors.DictCursor)

		## Load the server
		server = get_server_by_hostname(server_name)
		if server == None:
			return mysqladm.errors.output_error('No such server','I could not find the server you were looking for! ','')

		## Get the list of databases
		cur.execute("SELECT `id` AS 'id', `name`, `owner`, `description` FROM `databases` WHERE `server` = %s",(server['id']))

		## Get results
		databases = cur.fetchall()

		## ask the server for stats
		try:
			# Query the server for stats
			json_response = mysqladm.core.msg_node(server['hostname'], server['password'], 'stats')

		except Exception, e:
			app.logger.warn(str(e))
			return mysqladm.errors.output_error('Server communication error','An error occured whilst communicating with the remote server: ' + str(e),'mysqladm.core.msg_node')

		# If we have a valid response
		if 'status' in json_response and json_response['status'] == 0 and 'load_avg_1' in json_response:

			## turn date into date string
			json_response['db_sizes_date'] = mysqladm.core.ut_to_string(json_response['db_sizes_timestamp'])

			## create a 'usage' total
			json_response['disk_usage'] = json_response['disk_capacity'] - json_response['disk_free']

			## create a databases url for each one
			db_sizes = json_response['db_sizes']
			for db in databases:
				db['link'] = url_for('database_view',database_id=db['id'])

				## Need to put in a zero byte size or similar for databases listed from 'list' but not in stats view which is only run once in a while
				if db['name'] not in db_sizes:
					db['size'] = 0
				else:
					db['size'] = db_sizes[db['name']]

			return render_template('server.html', active='servers', stats=json_response, server=server, databases=databases)
		else:
			## TODO error
			return mysqladm.errors.output_error('Error querying server','An error occured whilst communicating with the remote server: ' + str(json_response['status']) + " " + json_response['error'],'jason_response handler')

	elif request.method == 'POST':
		## Used to EDIT and DELETE/REMOVE

		## Load the dictionary based cursor
		cur = g.db.cursor(mysql.cursors.DictCursor)

		## Load the server
		server = get_server_by_hostname(server_name)
		if server == None:
			return mysqladm.errors.output_error('No such server','I could not find the server you were looking for! ','')

		if 'delete' in request.form and request.form['delete'] == 'yes':
			# Update details
			cur.execute('DELETE FROM `servers` WHERE `hostname` = %s', (server_name))

			# Commit changes to the database
			g.db.commit()

			# Notify that we've succeeded
			flash('Server successfully deleted', 'alert-success')

			# redirect to server list
			return redirect(url_for('server_list'))

		else:

			## error tracking variable
			had_error = 0

			if 'server_alias' in request.form and len(request.form['server_alias']) > 0:
				alias = request.form['server_alias']
			else:
				had_error = 1
				alias = ''
				flash("You must specify a fully qualified server alias", 'alert-danger')

			if 'server_desc' in request.form and len(request.form['server_desc']) > 0:
				description = request.form['server_desc']
			else:
				had_error = 1
				description = ''
				flash("You must specify a description", 'alert-danger')

			if 'server_state' in request.form and len(request.form['server_state']) > 0:
				state = request.form['server_state']
			else:
				had_error = 1
				state = ''
				flash("You must specify a server status", 'alert-danger')

			if had_error == 1:
				return redirect(url_for('server_view', server_name=server['hostname']))

			# Update details
			cur.execute('UPDATE `servers` SET `alias` = %s, `desc` = %s, `state` = %s WHERE `hostname` = %s', (alias, description, state, server_name))

			# Commit changes to the database
			g.db.commit()

			# Notify that we've succeeded
			flash('Server details successfully changed', 'alert-success')

			# redirect to server view
			return redirect(url_for('server_view', server_name=server['hostname']))

################################################################################
#### ADD SERVER

@app.route('/servers/add', methods=['GET','POST'])
def server_add():
	if request.method == 'GET':
		return render_template('server_add.html', active='server_add')
	elif request.method == 'POST':
		# Set a flag to determine if we'd had an error
		had_error = 0

		# Grab the fields
		if 'server_hostname' in request.form and len(request.form['server_hostname']) > 0:
			hostname = request.form['server_hostname']
		else:
			had_error = 1
			hostname = ''
			flash("You must specify a fully qualified hostname", 'alert-danger')

		if 'server_alias' in request.form and len(request.form['server_alias']) > 0:
			alias = request.form['server_alias']
		else:
			had_error = 1
			alias = ''
			flash("You must specify a fully qualified server alias", 'alert-danger')

		if 'server_desc' in request.form and len(request.form['server_desc']) > 0:
			description = request.form['server_desc']
		else:
			had_error = 1
			description = ''
			flash("You must specify a description", 'alert-danger')

		if 'server_state' in request.form and len(request.form['server_state']) > 0:
			state = request.form['server_state']
		else:
			had_error = 1
			state = ''
			flash("You must specify a server status", 'alert-danger')

		if 'server_password' in request.form and len(request.form['server_password']) > 0:
			password = request.form['server_password']
		else:
			had_error = 1
			password = ''
			flash("You must specify a password", 'alert-danger')

		# If we had an error, just render the server_add page with whatever fields filled in
		if had_error == 1:
			return render_template('server_add.html', active='servers', hostname=hostname, alias=alias, description=description, state=state)
 
		## Talk to the server via HTTPS
		try:
			json_response = mysqladm.core.msg_node(hostname,password,'list')

			if 'status' not in json_response:
				return mysqladm.errors.output_error('Unable to add server', 'The given MySQL node responded with something unexpected: ' + str(json_response), '')

			if json_response['status'] != 0:
				if 'error' in json_response:
					flash("Error adding server: " + str(json_response['error']), 'alert-danger')
				else:
					flash("Error adding server: " + str(json_response['error']), 'alert-danger')

				return render_template('server_add.html', active='servers', hostname=hostname, alias=alias, description=description, state=state)
				
		except requests.exceptions.RequestException as e:
			return mysqladm.errors.output_error('Unable to add server','An error occured when communicating with the MySQL node: ' + str(e),'')	

		# Get a cursor to the database
		cur = g.db.cursor()
		
		# Ensure that the hostname doesn't already exist
		cur.execute('SELECT 1 FROM `servers` WHERE `hostname` = %s;', (hostname,))
		if cur.fetchone() is not None:
			flash('Error: The specified MySQL server is already managed by this server', 'alert-danger')
			return render_template('server_add.html', active='servers', hostname=hostname, alias=alias, description=description, state=state)
	
		# Insert the server into the database
		cur.execute('INSERT INTO `servers` (`hostname`, `alias`, `desc`, `state`, `password`) VALUES (%s, %s, %s, %s, %s)', (hostname, alias, description, state, password))

		# Commit changes to the database
		g.db.commit()

		## Last insert ID
		server_id = cur.lastrowid

		# Add database instances
		if 'list' in json_response:
			for instance in json_response['list']:
				cur.execute('INSERT INTO `databases` (`server`, `name`, `owner`, `description`) VALUES (%s, %s, %s, %s)', (server_id,instance,'N/A','N/A'))
				g.db.commit()

		# Notify that we've succeeded
		flash('MySQL Server added to database', 'alert-success')

		# redirect to server list
		return redirect(url_for('server_view',server_name=hostname))
