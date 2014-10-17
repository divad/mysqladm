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
	curd = g.db.cursor(mysql.cursors.DictCursor)

	## Execute a SQL select
	curd.execute("SELECT `id`, `name`, `hostname`, `alias`, `desc`, `state`, `password`, `sslverify`, `type` FROM `servers` WHERE `hostname` = %s", (hostname))

	## Get results
	return curd.fetchone()
	
def get_all_servers():
	"""Utility funtion to return all server objects.
	"""	
	
	## Load the dictionary based cursor
	curd = g.db.cursor(mysql.cursors.DictCursor)

	## Execute a SQL select
	curd.execute("SELECT `servers`.`id` AS `id`, `servers`.`name` AS `name`, `servers`.`hostname` AS `hostname`, `servers`.`sslverify` AS `sslverify`, `servers`.`type` as `type`, `servers`.`alias` AS `alias`, `servers`.`desc` AS `desc`, `servers`.`state` AS `state`, `servers`.`password` AS `password`, COUNT(`databases`.`id`) AS `databases` FROM `servers` LEFT JOIN `databases` ON databases.server = servers.id GROUP BY `servers`.`id`;");

	## Get results
	rows = curd.fetchall()
	
	return rows

def get_farm_servers():
	"""Utility funtion to return all farm server objects.
	"""	
	
	## Load the dictionary based cursor
	curd = g.db.cursor(mysql.cursors.DictCursor)

	## Execute a SQL select
	curd.execute("SELECT `servers`.`id` AS `id`, `servers`.`name` AS `name`, `servers`.`hostname` AS `hostname`, `servers`.`sslverify` AS `sslverify`, `servers`.`type` as `type`, `servers`.`alias` AS `alias`, `servers`.`desc` AS `desc`, `servers`.`state` AS `state`, `servers`.`password` AS `password`, COUNT(`databases`.`id`) AS `databases` FROM `servers` LEFT JOIN `databases` ON databases.server = servers.id WHERE servers.type = '1' GROUP BY `servers`.`id`;");

	## Get results
	rows = curd.fetchall()
	
	return rows

def get_standalone_servers():
	"""Utility funtion to return all standalone server objects.
	"""	
	
	## Load the dictionary based cursor
	curd = g.db.cursor(mysql.cursors.DictCursor)

	## Execute a SQL select
	curd.execute("SELECT `servers`.`id` AS `id`, `servers`.`name` AS `name`, `servers`.`hostname` AS `hostname`, `servers`.`sslverify` AS `sslverify`, `servers`.`type` as `type`, `servers`.`alias` AS `alias`, `servers`.`desc` AS `desc`, `servers`.`state` AS `state`, `servers`.`password` AS `password`, COUNT(`databases`.`id`) AS `databases` FROM `servers` LEFT JOIN `databases` ON databases.server = servers.id WHERE servers.type = '0' GROUP BY `servers`.`id`;");

	## Get results
	rows = curd.fetchall()
	
	return rows
	
	
def get_server_databases(server_id):
	"""Utility funtion to return all databases from a particular server
	"""	
	
	try:
		server_id = int(server_id)
	except ValueError:
		abort(400)
	
	## Load the dictionary based cursor
	curd = g.db.cursor(mysql.cursors.DictCursor)
	
	## Get the list of databases
	curd.execute("SELECT `id` AS 'id', `name`, `owner`, `description` FROM `databases` WHERE `server` = %s",(server_id))

	## Get result
	return curd.fetchall()
	
def get_server_permissions(server_id):

	try:
		server_id = int(server_id)
	except ValueError:
		abort(400)
	
	## Load the dictionary based cursor
	curd = g.db.cursor(mysql.cursors.DictCursor)
	
	## Get the list of permissions
	curd.execute("SELECT `name` FROM `permissions` WHERE `server` = %s",(server_id))

	## Get result
	return curd.fetchall()
	
def user_is_delegate(server_id):
	## Load the dictionary based cursor
	curd = g.db.cursor(mysql.cursors.DictCursor)

	## Execute a SQL select
	curd.execute("SELECT * FROM `permissions` WHERE `name` = %s AND `server` = %s", (session['username'],server_id))

	## Get results
	result = curd.fetchone()
	
	if result != None:
		return True
	else:
		return False
	
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
		
	if not session['admin']:
	## rows is a tuple, so we'll create a list to replace it
		servers = []
	
		## Check the user has permission to the server
		for row in rows:
			if user_is_delegate(row['id']):
				servers.append(row)
	else:
		servers = rows

	return render_template('servers.html', active='servers',rows=servers)

################################################################################
#### LIST STANDALONE SERVERS

@app.route('/standalone')
@mysqladm.core.login_required
@mysqladm.core.admin_required
def server_list_standalone():
	"""View function to list all servers in a basic table (standalone only)
	"""		
	
	## Load servers
	rows = get_standalone_servers()
	
	## Create link for each server 
	for row in rows:
		row['link'] = url_for('server_view', server_name=row['hostname'])

	return render_template('servers_standalone.html', active='servers',rows=rows)
	
	
################################################################################
#### SERVER STATUS

@app.route('/server_status')
@mysqladm.core.login_required
def server_status():
	"""View function to list all servers with a status output too
	"""		
	
	## Load servers
	rows = get_all_servers()
	
	## A list to put them in
	servers = []

	## Iterate through each database and get the statistics
	for row in rows:
		server_error = False
		serror = ''
		
		if not session['admin']:
		
		## Check the user has permission to the server
			if user_is_delegate(row['id']):
				servers.append(row)
			else:
				continue
		else:
			servers.append(row)

		## Add the link to the server
		row['link'] = url_for('server_view', server_name=row['hostname'])
		
		try:
			json_response = mysqladm.core.msg_node(row, 'stats')

			if 'status' in json_response:
				if json_response['status'] == 0 and 'load_avg_1' in json_response:
					pass
					## no error
				else:
					if 'error' in json_response:
						row['error'] = "Agent reported an error: " + json_response['error']
					else:
						row['error'] = "Agent reported an error: status number " + str(json_response['status'])

					continue

			else:
				row['error'] = "Error contacting agent: Invalid response from server"
				continue
				
		except Exception as e:
			row['error'] = "Error contacting agent: " + str(e)
			continue
		
		row['load'] = json_response['load_avg_1'] + ' ' + json_response['load_avg_5'] + ' ' + json_response['load_avg_15']
		row['disk_usage'] = json_response['disk_capacity'] - json_response['disk_free']
		row['disk_capacity'] = json_response['disk_capacity']
		row['disk_free'] = json_response['disk_free']
		row['uptime'] = json_response['db_uptime']
		row['disk_pc'] = int( ( float(row['disk_usage']) / float(row['disk_capacity']) ) * 100 )
	
		row['disk_status'] = 'success'
		if row['disk_pc'] >= 30:
			if row['disk_pc'] <= 75:
				row['disk_status'] = 'info'		
			elif row['disk_pc'] <= 85:
				row['disk_status'] = 'warning'
			else:
				row['disk_status'] = 'danger'
				
		row['disk_pc'] = str(row['disk_pc'])

	return render_template('server_status.html', active='servers',rows=servers)
	
################################################################################
#### SERVER ISOTOPE

@app.route('/grid')
@mysqladm.core.login_required
@mysqladm.core.admin_required
def isotope():
	"""View function to list all servers via the isotope grid
	"""		
	
	## Load servers
	rows = get_farm_servers()

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
					if 'error' in json_response:
						row['error'] = "Agent reported an error: " + json_response['error']
					else:
						row['error'] = "Agent reported an error: status number " + str(json_response['status'])
					continue
			else:
				row['error'] = "Error contacting agent: Invalid response from server"
				continue
				
		except Exception as e:
			row['error'] = "Error contacting agent: " + str(e)
			continue
			
		row['load'] = json_response['load_avg_1'] + ' ' + json_response['load_avg_5'] + ' ' + json_response['load_avg_15']
		row['disk_usage'] = json_response['disk_capacity'] - json_response['disk_free']
		row['disk_capacity'] = json_response['disk_capacity']
		row['disk_free'] = json_response['disk_free']
		row['uptime'] = json_response['db_uptime']

	return render_template('server_isotope.html', active='servers',rows=rows)

################################################################################
#### MANAGE SERVER

@app.route('/server/<server_name>', methods=['GET','POST'])
@mysqladm.core.login_required
def server_view(server_name):
	"""View function to view a servers details
	"""

	## Load the dictionary based cursor
	cur = g.db.cursor(mysql.cursors.DictCursor)

	## Load the server
	server = get_server_by_hostname(server_name)
	
	if server == None:
		return mysqladm.errors.output_error('No such server','I could not find the server you were looking for! ','')
		
	## Check permissions to the server
	if not session['admin']:
		if not user_is_delegate(server['id']):
			abort(403)
	
	if request.method == 'GET':

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
				
				## create a percentage
				json_response['disk_pc'] = int( ( float(json_response['disk_usage']) / float(json_response['disk_capacity']) ) * 100 )
	
			
				json_response['disk_status'] = 'success'
				if json_response['disk_pc'] >= 30:
					if json_response['disk_pc'] <= 75:
						json_response['disk_status'] = 'info'		
					elif json_response['disk_pc'] <= 85:
						json_response['disk_status'] = 'warning'
					else:
						json_response['disk_status'] = 'danger'
						
				json_response['disk_pc'] = str(json_response['disk_pc'])
						
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
				if 'error' in json_response:
					flash('The MySQL agent returned an error: ' + json_response['error'],'alert-danger')
				elif 'status' in json_response:
					flash('The MySQL agent returned an error code: ' + str(json_response['status']),'alert-danger')
				else:
					flash('The MySQL agent returned an invalid response','alert-danger')

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
	
		## You must be an admin to do these functions, even if you're a delegate
		if not session['admin']:
			abort(403)
	
		## Used to EDIT and DELETE/REMOVE

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

		if 'passwd' in request.form and request.form['passwd'] == 'yes':
			## SET AGENT PASSWORD

			if 'agent_password' in request.form and len(request.form['agent_password']) > 0:

				# Update details
				cur.execute('UPDATE `servers` SET `password` = %s WHERE `hostname` = %s', (request.form['agent_password'], server_name))

				# Commit changes to the database
				g.db.commit()

				# Notify that we've succeeded
				flash('Server agent password successfully changed', 'alert-success')

				# redirect to server view
				return redirect(url_for('server_view', server_name=server['hostname']))	

			else:
				flash("Invalid agent password", 'alert-danger')
				return redirect(url_for('server_view', server_name=server['hostname']))

		else:
			## EDIT

			## error tracking variable
			had_error = 0

			if 'server_name' in request.form and len(request.form['server_name']) > 0:
				name = request.form['server_name']
				if not mysqladm.core.is_valid_hostname(name):
					return mysqladm.errors.output_error('Invalid name','That server name is invalid. ','')
			else:
				had_error = 1
				name = ''
				flash("You must specify a valid server name", 'alert-danger')
 
			if 'server_alias' in request.form and len(request.form['server_alias']) > 0:
				alias = request.form['server_alias']
				if not alias == 'N/A':
					if not mysqladm.core.is_valid_hostname(alias):
						return mysqladm.errors.output_error('Invalid alias','That server alias is invalid. ','')
			else:
				# alias is optional
				alias = 'N/A'

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

			if 'server_type' in request.form:
				server_type = int(request.form['server_type'])
				if server_type < 0 or server_type > 1:
					return mysqladm.errors.output_error('Invalid server type','That server type is invalid','')
			else:
				had_error = 1
				state = ''
				flash("You must specify a server type flag", 'alert-danger')

			if had_error == 1:
				return redirect(url_for('server_view', server_name=server['hostname']))

			# Update details
			cur.execute('UPDATE `servers` SET `name` = %s, `alias` = %s, `desc` = %s, `state` = %s, `sslverify` = %s, `type` = %s WHERE `hostname` = %s', (name, alias, description, state, sslverify, server_type,server_name))

			# Commit changes to the database
			g.db.commit()

			# Notify that we've succeeded
			flash('Server details successfully changed', 'alert-success')

			# redirect to server view
			return redirect(url_for('server_view', server_name=server['hostname']))
			
################################################################################
#### SERVER DELEGATE PERMISSIONS

@app.route('/serverperms/<server_name>', methods=['GET','POST'])
@mysqladm.core.login_required
@mysqladm.core.admin_required
def server_permissions(server_name):
	"""Function to manage server delegate permissions
	"""		
	
	## Load the server
	server = get_server_by_hostname(server_name)

	if server == None:
		return mysqladm.errors.output_error('No such server','I could not find the server you were looking for! ','')

	if request.method == 'GET':
		## Load permissions
		rows = get_server_permissions(server['id'])

		return render_template('permissions.html', active='servers',rows=rows,server=server)
		
	elif request.method == 'POST':
	
		if 'action' in request.form:
		
			if 'name' in request.form and len(request.form['name']) > 0:
				name = request.form['name']
				if not mysqladm.core.is_valid_username(name):
					flash('That username is invalid','alert-danger')
					return(redirect(url_for('server_permissions',server_name=server['hostname'])))
			else:
				flash("You must specify a valid username", 'alert-danger')			
				return(redirect(url_for('server_permissions',server_name=server['hostname'])))
		
			if request.form['action'] == 'add':
					
				# Insert the server into the database
				cur = g.db.cursor()
				cur.execute('INSERT INTO `permissions` (`name`, `server`) VALUES (%s, %s)', (name, server['id']))
				g.db.commit()
				flash("Permissions added successfully", 'alert-success')
				return(redirect(url_for('server_permissions',server_name=server['hostname'])))

			elif request.form['action'] == 'delete':

				# Delete
				cur = g.db.cursor()
				cur.execute('DELETE FROM `permissions` WHERE `name` = %s AND `server` = %s', (name, server['id']))
				g.db.commit()
				flash("Permissions removed successfully", 'alert-success')	
				return(redirect(url_for('server_permissions',server_name=server['hostname'])))		
				
			else:
				abort(400)
		else:
			abort(400)
		

################################################################################
#### ADD SERVER

@app.route('/servers/add', methods=['GET','POST'])
@mysqladm.core.login_required
@mysqladm.core.admin_required
def server_add():
	"""View function to add a new server
	"""	
	
	if request.method == 'GET':
		return render_template('server_add.html', active='servers')
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

		if 'server_name' in request.form and len(request.form['server_name']) > 0:
			name = request.form['server_name']
			if not mysqladm.core.is_valid_hostname(name):
				return mysqladm.errors.output_error('Invalid name','That server name is invalid. ','')
		else:
			had_error = 1
			name = ''
			flash("You must specify a valid server name", 'alert-danger')

		if 'server_alias' in request.form and len(request.form['server_alias']) > 0:
			alias = request.form['server_alias']
			if not mysqladm.core.is_valid_hostname(alias):
				return mysqladm.errors.output_error('Invalid alias','That server alias is invalid.','')
		else:
			# alias is optional
			alias = 'N/A'

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

		if 'server_type' in request.form:
			server_type = int(request.form['server_type'])
			if server_type < 0 or server_type > 1:
				return mysqladm.errors.output_error('Invalid server type','That server type is invalid','')
		else:
			had_error = 1
			state = ''
			flash("You must specify a server type flag", 'alert-danger')

		# If we had an error, just render the server_add page with whatever fields filled in
		if had_error == 1:
			return render_template('server_add.html', active='servers', hostname=hostname, alias=alias, description=description, state=state, sslverify=sslverify, server_type=server_type, name=name)
 
		## Talk to the server via HTTPS
		try:
			serverobj = {'hostname': hostname, 'password': password, 'sslverify': sslverify}
			json_response = mysqladm.core.msg_node(serverobj,'list')

			if 'status' not in json_response:
				return mysqladm.errors.output_error('Unable to add server', 'The given MySQL agent responded with something unexpected: ' + str(json_response), '')

			if json_response['status'] != 0:
				if 'error' in json_response:
					flash("Error adding server: " + str(json_response['error']), 'alert-danger')
				else:
					flash("Error adding server, code: " + str(json_response['status']), 'alert-danger')

				return render_template('server_add.html', active='servers', hostname=hostname, alias=alias, description=description, state=state, sslverify=sslverify)
				
		except requests.exceptions.RequestException as e:
			return mysqladm.errors.output_error('Unable to add server','An error occured when communicating with the MySQL agent: ' + str(e),'')	

		# Get a cursor to the database
		cur = g.db.cursor()
		
		# Ensure that the hostname doesn't already exist
		cur.execute('SELECT 1 FROM `servers` WHERE `hostname` = %s;', (hostname,))
		if cur.fetchone() is not None:
			flash('Error: The specified MySQL server is already managed by this server', 'alert-danger')
			return render_template('server_add.html', active='servers', hostname=hostname, alias=alias, description=description, state=state, sslverify=sslverify)
			
		# Insert the server into the database
		cur.execute('INSERT INTO `servers` (`name`, `hostname`, `alias`, `desc`, `state`, `password`, `sslverify`, `type`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)', (name, hostname, alias, description, state, password, sslverify, server_type))

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
