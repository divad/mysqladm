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

################################################################################
#### UTILITY FUNCTIONS

def get_server_by_hostname(hostname):
	"""Utility funtion to return a server by passing it the full hostname.
	"""
	
	if not mysqladm.core.is_valid_hostname(hostname):
		abort(400)
	
	## Load the dictionary based cursor
	cur = g.db.cursor(mysql.cursors.DictCursor)

	## Execute a SQL select
	cur.execute("SELECT `id`, `hostname`, `alias`, `desc`, `state`, `password`, `sslverify` FROM `servers` WHERE `hostname` = %s", (hostname))

	## Get results
	return cur.fetchone()
	
def get_all_servers():
	"""Utility funtion to return all server objects.
	"""	
	
	## Load the dictionary based cursor
	cur = g.db.cursor(mysql.cursors.DictCursor)

	## Execute a SQL select
	cur.execute("SELECT `servers`.`id` AS `id`, `servers`.`hostname` AS `hostname`, `servers`.`sslverify` AS `sslverify`, `servers`.`alias` AS `alias`, `servers`.`desc` AS `desc`, `servers`.`state` AS `state`, `servers`.`password` AS `password`, COUNT(`databases`.`id`) AS `databases` FROM `servers` LEFT JOIN `databases` ON databases.server = servers.id GROUP BY `servers`.`id`;");

	## Get results
	rows = cur.fetchall()
	
	return rows
	
def get_server_databases(server_id):
	"""Utility funtion to return all databases from a particular server
	"""	
	
	try:
		server_id = int(server_id)
	except ValueError:
		abort(400)
	
	## Load the dictionary based cursor
	cur = g.db.cursor(mysql.cursors.DictCursor)
	
	## Get the list of databases
	cur.execute("SELECT `id` AS 'id', `name`, `owner`, `description` FROM `databases` WHERE `server` = %s",(server_id))

	## Get result
	return cur.fetchall()

################################################################################
#### LIST SERVERS

@app.route('/servers')
@mysqladm.core.login_required
def server_list():
	"""View function to list all servers in a basic table
	"""		
	
	## Load servers
	rows = get_all_servers()
	
	## Create link for each server 
	for row in rows:
		row['link'] = url_for('server_view', server_name=row['hostname'])

	return render_template('servers.html', active='servers',rows=rows)
	
	
################################################################################
#### SERVER STATUS

@app.route('/server_status')
@mysqladm.core.login_required
def server_status():
	"""View function to list all servers with a status output too
	"""		
	
	## Load servers
	rows = get_all_servers()

	## Iterate through each database and get the statistics
	for row in rows:
		server_error = False
		serror = ''

		## Add the link to the server
		row['link'] = url_for('server_view', server_name=row['hostname'])
		
		try:
			json_response = mysqladm.core.msg_node(row, 'stats')

			if 'status' in json_response:
				if json_response['status'] == 0 and 'load_avg_1' in json_response:
					pass
					## no error
				else:
					row['error'] = "Error contacting agent: Invalid JSON response from server"
					continue
			else:
				row['error'] = "Error contacting agent: Invalid JSON response from server"
				continue
				
		except Exception as e:
			row['error'] = "Error contacting agent: " + str(e)
			continue
		
		row['load'] = json_response['load_avg_1'] + ' ' + json_response['load_avg_5'] + ' ' + json_response['load_avg_15']
		row['disk_usage'] = json_response['disk_capacity'] - json_response['disk_free']
		row['disk_capacity'] = json_response['disk_capacity']
		row['disk_free'] = json_response['disk_free']
		row['uptime'] = json_response['db_uptime']

	return render_template('server_status.html', active='server_status',rows=rows)
	
################################################################################
#### SERVER ISOTOPE

@app.route('/isotope')
@mysqladm.core.login_required
def isotope():
	"""View function to list all servers via the isotope grid
	"""		
	
	## Load servers
	rows = get_all_servers()

	## Iterate through each database and get the statistics
	for row in rows:
		server_error = False
		serror = ''
		
		## Add the link to the server
		row['link'] = url_for('server_view', server_name=row['hostname'])
		
		## Add the short form of the database hostname
		short,sep,after = row['hostname'].partition('.')
		row['shortname'] = short
		
		try:
			json_response = mysqladm.core.msg_node(row, 'stats')

			if 'status' in json_response:
				if json_response['status'] == 0 and 'load_avg_1' in json_response:
					pass
					## no error
				else:
					row['error'] = "Error contacting agent: Invalid JSON response from server"
					continue
			else:
				row['error'] = "Error contacting agent: Invalid JSON response from server"
				continue
				
		except Exception as e:
			row['error'] = "Error contacting agent: " + str(e)
			continue
			
		row['load'] = json_response['load_avg_1'] + ' ' + json_response['load_avg_5'] + ' ' + json_response['load_avg_15']
		row['disk_usage'] = json_response['disk_capacity'] - json_response['disk_free']
		row['disk_capacity'] = json_response['disk_capacity']
		row['disk_free'] = json_response['disk_free']
		row['uptime'] = json_response['db_uptime']

	return render_template('server_isotope.html', active='server_isotope',rows=rows)

################################################################################
#### MANAGE SERVER

@app.route('/server/<server_name>', methods=['GET','POST'])
@mysqladm.core.login_required
def server_view(server_name):
	"""View function to view a servers details
	"""		
	
	if request.method == 'GET':
		## Load the dictionary based cursor
		cur = g.db.cursor(mysql.cursors.DictCursor)

		## Load the server
		server = get_server_by_hostname(server_name)
		if server == None:
			return mysqladm.errors.output_error('No such server','I could not find the server you were looking for! ','')

		## Get list of databases for the server
		databases = get_server_databases(server['id'])
		
		## Error handling
		server_error = False

		## ask the server for stats
		try:
			# Query the server for stats
			json_response = mysqladm.core.msg_node(server, 'stats')
			
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
						db['unsized'] = 1
					else:
						db['size'] = db_sizes[db['name']]
						
			else:
				flash('The MySQL agent returned an error: ' + json_response['error'],'alert-danger')
				server_error = True

		except Exception, e:
			flash('An error occured whilst communicating with the MySQL agent: ' + str(e),'alert-danger')
			server_error = True
			
		if server_error:
			errorstr = 'N/A'
			json_response = {
				'db_version': errorstr,
				'disk_mount_point': errorstr,
				}
				
			for db in databases:
				db['size'] = 0
			
		return render_template('server.html', active='servers', stats=json_response, server=server, databases=databases, server_error = server_error)

	elif request.method == 'POST':
		## Used to EDIT and DELETE/REMOVE

		## Load the dictionary based cursor
		cur = g.db.cursor(mysql.cursors.DictCursor)

		## Load the server
		server = get_server_by_hostname(server_name)
		
		if server == None:
			return mysqladm.errors.output_error('No such server','I could not find the server you were looking for! ','')

		if 'delete' in request.form and request.form['delete'] == 'yes':
			## DELETE
			
			# Update details
			cur.execute('DELETE FROM `servers` WHERE `hostname` = %s', (server_name))

			# Commit changes to the database
			g.db.commit()

			# Notify that we've succeeded
			flash('Server successfully deleted', 'alert-success')

			# redirect to server list
			return redirect(url_for('server_list'))

		else:
			## EDIT

			## error tracking variable
			had_error = 0

			if 'server_alias' in request.form and len(request.form['server_alias']) > 0:
				alias = request.form['server_alias']
				if not mysqladm.core.is_valid_hostname(alias):
					return mysqladm.errors.output_error('Invalid alias','That server alias is invalid. ','')
			else:
				had_error = 1
				alias = ''
				flash("You must specify a fully qualified server alias", 'alert-danger')

			if 'server_desc' in request.form and len(request.form['server_desc']) > 0:
				description = request.form['server_desc']
				if not mysqladm.core.is_valid_desc(description):
					return mysqladm.errors.output_error('Invalid description','That server description is invalid. ','')
			else:
				had_error = 1
				description = ''
				flash("You must specify a description", 'alert-danger')

			if 'server_state' in request.form and len(request.form['server_state']) > 0:
				state = request.form['server_state']
				if not mysqladm.core.is_valid_env(state):
					return mysqladm.errors.output_error('Invalid environment','That server status/environment is invalid. ','')	
			else:
				had_error = 1
				state = ''
				flash("You must specify a server status", 'alert-danger')
				
			if 'server_sslverify' in request.form:
				sslverify = int(request.form['server_sslverify'])
				if sslverify < 0 or sslverify > 1:
					return mysqladm.errors.output_error('Invalid ssl verify flag','That ssl verify flag is invalid','')
			else:
				had_error = 1
				state = ''
				flash("You must specify a ssl verify flag", 'alert-danger')

			if had_error == 1:
				return redirect(url_for('server_view', server_name=server['hostname']))

			# Update details
			cur.execute('UPDATE `servers` SET `alias` = %s, `desc` = %s, `state` = %s, `sslverify` = %s WHERE `hostname` = %s', (alias, description, state, sslverify, server_name,))

			# Commit changes to the database
			g.db.commit()

			# Notify that we've succeeded
			flash('Server details successfully changed', 'alert-success')

			# redirect to server view
			return redirect(url_for('server_view', server_name=server['hostname']))

################################################################################
#### ADD SERVER

@app.route('/servers/add', methods=['GET','POST'])
@mysqladm.core.login_required
def server_add():
	"""View function to add a new server
	"""	
	
	if request.method == 'GET':
		return render_template('server_add.html', active='server_add')
	elif request.method == 'POST':
		# Set a flag to determine if we'd had an error
		had_error = 0

		# Grab the fields
		if 'server_hostname' in request.form and len(request.form['server_hostname']) > 0:
			hostname = request.form['server_hostname']
			if not mysqladm.core.is_valid_hostname(hostname):
				return mysqladm.errors.output_error('Invalid hostname','That server hostname is invalid.','')
		else:
			had_error = 1
			hostname = ''
			flash("You must specify a fully qualified hostname", 'alert-danger')

		if 'server_alias' in request.form and len(request.form['server_alias']) > 0:
			alias = request.form['server_alias']
			if not mysqladm.core.is_valid_hostname(alias):
				return mysqladm.errors.output_error('Invalid alias','That server alias is invalid.','')
		else:
			had_error = 1
			alias = ''
			flash("You must specify a fully qualified server alias", 'alert-danger')

		if 'server_desc' in request.form and len(request.form['server_desc']) > 0:
			description = request.form['server_desc']
			if not mysqladm.core.is_valid_desc(description):
				return mysqladm.errors.output_error('Invalid description','That server description is invalid. ','')
		else:
			had_error = 1
			description = ''
			flash("You must specify a description", 'alert-danger')

		if 'server_state' in request.form and len(request.form['server_state']) > 0:
			state = request.form['server_state']
			if not mysqladm.core.is_valid_env(state):
				return mysqladm.errors.output_error('Invalid environment','That server status/environment is invalid. ','')			
		else:
			had_error = 1
			state = ''
			flash("You must specify a server status/environment", 'alert-danger')

		if 'server_password' in request.form and len(request.form['server_password']) > 0:
			password = request.form['server_password']
		else:
			had_error = 1
			password = ''
			flash("You must specify a password", 'alert-danger')
			
		if 'server_sslverify' in request.form:
			sslverify = int(request.form['server_sslverify'])
			if sslverify < 0 or sslverify > 1:
				return mysqladm.errors.output_error('Invalid ssl verify flag','That ssl verify flag is invalid','')
		else:
			had_error = 1
			state = ''
			flash("You must specify a ssl verify flag", 'alert-danger')

		# If we had an error, just render the server_add page with whatever fields filled in
		if had_error == 1:
			return render_template('server_add.html', active='servers', hostname=hostname, alias=alias, description=description, state=state, sslverify=sslverify)
 
		## Talk to the server via HTTPS
		try:
			serverobj = {'hostname': hostname, 'password': password, 'sslverify': sslverify}
			json_response = mysqladm.core.msg_node(serverobj,'list')

			if 'status' not in json_response:
				return mysqladm.errors.output_error('Unable to add server', 'The given MySQL node responded with something unexpected: ' + str(json_response), '')

			if json_response['status'] != 0:
				if 'error' in json_response:
					flash("Error adding server: " + str(json_response['error']), 'alert-danger')
				else:
					flash("Error adding server, code: " + str(json_response['status']), 'alert-danger')

				return render_template('server_add.html', active='servers', hostname=hostname, alias=alias, description=description, state=state, sslverify=sslverify)
				
		except requests.exceptions.RequestException as e:
			return mysqladm.errors.output_error('Unable to add server','An error occured when communicating with the MySQL node: ' + str(e),'')	

		# Get a cursor to the database
		cur = g.db.cursor()
		
		# Ensure that the hostname doesn't already exist
		cur.execute('SELECT 1 FROM `servers` WHERE `hostname` = %s;', (hostname,))
		if cur.fetchone() is not None:
			flash('Error: The specified MySQL server is already managed by this server', 'alert-danger')
			return render_template('server_add.html', active='servers', hostname=hostname, alias=alias, description=description, state=state, sslverify=sslverify)
			
		sslverify = str(sslverify)
	
		# Insert the server into the database
		cur.execute('INSERT INTO `servers` (`hostname`, `alias`, `desc`, `state`, `password`, `sslverify`) VALUES (%s, %s, %s, %s, %s)', (hostname, alias, description, state, password, sslverify))

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
