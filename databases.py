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
import re

################################################################################
#### UTILITY FUNCTIONS

def get_database(db_name,server_id):
	"""Return a database instance. db_name is the name of the database and 
	server_id the numerical ID of the server the database resides on.
	"""
	try:
		server_id = int(server_id)
	except ValueError:
		abort(400)

	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute("SELECT * FROM `databases` WHERE `name` = %s AND `server` = %s", (db_name,server_id))
	return cur.fetchone()
	
def get_database_by_id(database_id):
	"""Return a database instance. database_id is the numerical ID of the the
	representing the database. 
	"""
	try:
		database_id = int(database_id)
	except ValueError:
		abort(400)
		
	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute("SELECT `databases`.`id` AS 'id', `servers`.`hostname` AS `server`, `databases`.`create_date` AS `create_date`, `databases`.`name` AS 'name', `databases`.`owner` AS 'owner', `databases`.`description` AS 'description' FROM `databases` LEFT JOIN `servers` ON `servers`.`id` = `databases`.`server` WHERE `databases`.`id` = %s",(database_id))
	return cur.fetchone()
	
def insert_database_record(server_id,name,owner,description):
	"""Insert a record into the database of a database on a mysql server and returns the ID"""

	## Get a cursor
	cur = g.db.cursor()

	# Create a record of the database in the database
	cur.execute('INSERT INTO `databases` (`server`, `name`, `owner`, `description`, `create_date`) VALUES (%s, %s, %s, %s, UNIX_TIMESTAMP(NOW()))', (server_id, name, owner, description))
	
	# Commit changes to the database
	g.db.commit()

	## Last insert ID
	return cur.lastrowid
	
def delete_database_record(database_id):
	"""Delete a record of a database - does not delete from actual server"""

	cur = g.db.cursor()
	cur.execute('DELETE FROM `databases` WHERE `id` = %s', (database_id))
	g.db.commit()
	
def get_all_databases(cmd_line=False):
	"""Return a list of databases"""

	## Load the dictionary based cursor
	cur = g.db.cursor(mysql.cursors.DictCursor)

	## Execute a SQL select
	cur.execute("""
		SELECT 
		
			`databases`.`id` AS `id`, 
			`databases`.`create_date` AS `create_date`, 
			`servers`.`hostname` AS `server`, 
			`servers`.`id` AS `server_id`,
			`databases`.`name` AS 'name', 
			`databases`.`owner` AS 'owner', 
			`databases`.`description` AS 'description' 
			
		FROM `databases`
		
		LEFT OUTER JOIN 
			`servers` ON `servers`.`id` = `databases`.`server`
			
		ORDER BY `servers`.`hostname` """)

	## Get results
	rows = cur.fetchall()

	for row in rows:
		short,sep,after = row['server'].partition('.')
		row['shortserver'] = short
		
		if not cmd_line:
			row['link'] = url_for('database_view', database_id = row['id'])
		
	return rows

################################################################################
#### LIST DATABASES

@app.route('/databases')
@mysqladm.core.login_required
def database_list():
	"""View function to return a simple list of databases.
	"""
	
	rows = get_all_databases()

	if not session['admin']:
		databases = []
		
		for db in rows:
			if mysqladm.servers.user_is_delegate(db['server_id']):
				databases.append(db)
	else:
		databases = rows

	return render_template('databases.html', active='databases', rows=databases)
	
################################################################################
#### SYNC DATABASES

@app.route('/databases/sync', methods=['GET','POST'])
@mysqladm.core.login_required
@mysqladm.core.admin_required
def database_sync():
	"""View function to check the differences between what the server has and what our database records indicate.
	"""
	
	## Load a cursor
	cur = g.db.cursor()

	## Load servers
	servers = mysqladm.servers.get_servers()
	
	## Rows to return
	rows = []
	
	for server in servers:

		try:
			json_response = mysqladm.core.msg_node(server,'list')

			if 'status' not in json_response:
				flash('Error from agent: Invalid response from ' + server['hostname'], 'alert-warning')
				continue

			if json_response['status'] != 0:
				if 'error' in json_response:
					flash('Error from agent on server ' + server['hostname'] + ': ' + json_response['error'], 'alert-warning')
					continue
				else:
					flash('Error from agent on server ' + server['hostname'] + ' code returned: ' + json_response['code'], 'alert-warning')
					continue

		except requests.exceptions.RequestException as e:
			flash('Error contacting agent on server ' + server['hostname'] + ': ' + str(e), 'alert-warning')
			continue
		
		databases = mysqladm.servers.get_server_databases(server['id'])
		dblist = []
		for db in databases:
			dblist.append(db['name'])

		## Check to see if any databases have been created without us knowing about it
		if 'list' in json_response:
			for instance in json_response['list']:
				if instance not in dblist:
					
					if request.method == 'GET':
						rows.append('Database "' + instance + '" exists on server ' + server['hostname'] + ' but is not recorded within MySQL Manager')

					elif request.method == 'POST':
						## create database record
						database_id = mysqladm.databases.insert_database_record(server['id'], instance, 'N/A', 'N/A')
						rows.append('Created record of database "' + instance + '" on server "' + server['hostname']) 
					
		## Check to see if any databases appear to have been deleted without us knowing about it
		for db in databases:
			if db['name'] not in json_response['list']:
				if request.method == 'GET':
					rows.append('Database "' + db['name'] + '" is recorded within MySQL Manager but is no longer present on ' + server['hostname'])

				elif request.method == 'POST':
					## delete database record
					mysqladm.databases.delete_database_record(db['id'])
					rows.append('Database "' + db['name'] + '" was removed from records as it was not found on server ' + server['hostname'])
					
	return render_template('sync.html', active='other', rows=rows)

################################################################################
#### VIEW/EDIT DATABASE INSTANCE

@app.route('/database/<database_id>', methods=['GET','POST'])
@mysqladm.core.login_required
def database_view(database_id):
	"""View function to show the details of a database (via GET) or save changes 
	to it (via POST).
	"""
	
	## Get database
	database = get_database_by_id(database_id)
	if database == None:
		return mysqladm.errors.output_error('No such database','I could not find the database you were looking for! ','')

	## Get the server which hosts the database
	server = mysqladm.servers.get_server_by_hostname(database['server'])
	if server == None:
		return mysqladm.errors.output_error('No such server','I could not find the server the database resides on!','')

	## Check permissions to the server
	if not session['admin']:
		if not mysqladm.servers.user_is_delegate(server['id']):
			abort(403)
		

	if request.method == 'GET':
		
		db_size = "Unknown"
		db_size_available = False
			
		try:
			json_response = mysqladm.core.msg_node(server, 'stats')

			if 'status' not in json_response:
				flash('Error from server agent: Invalid response from ' + server['hostname'], 'alert-warning')
			else:
				if json_response['status'] != 0:
					if 'error' in json_response:
						flash('Error from agent on server ' + server['hostname'] + ': ' + json_response['error'], 'alert-warning')
					else:
						flash('Error code from agent on server ' + server['hostname'] + ': ' + json_response['code'], 'alert-warning')
				else:
					db_sizes = json_response['db_sizes']
					if database['name'] not in db_sizes:
						db_size = "Size not yet calculated"
					else:
						db_size = db_sizes[database['name']]
						db_size_available = True

		except requests.exceptions.RequestException as e:
			flash('Error contacting agent on server ' + server['hostname'] + ': ' + str(e), 'alert-warning')
			
		try:
			database['create_date'] = mysqladm.core.ut_to_string(database['create_date'])
		except TypeError:
			database['create_date'] = 'Unknown'
	
		return render_template('database.html', active='databases', server=server, db=database, db_size=db_size,db_size_available=db_size_available)
		
	elif request.method == 'POST':
		## Edit the database details
		
		if 'database_desc' in request.form and len(request.form['database_desc']) > 0:
			database_desc = request.form['database_desc']
			if not mysqladm.core.is_valid_desc(database_desc):
				return mysqladm.errors.output_error('Unable to save database details', 'Invalid character(s) in description','')
		else:
			flash('Database description must not be empty', 'alert-danger')
			return redirect(url_for('database_view', database_id=database_id))
			
		if 'database_owner' in request.form and len(request.form['database_owner']) > 0:
			database_owner = request.form['database_owner']
			if re.search(r'^[A-Za-z0-9_\s\-\.\@\&\\/\(\)\[\]]*$', database_owner) == None:
				return mysqladm.errors.output_error('Unable to save detabase details', 'Invalid character(s) in owner','')
		else:
			flash('Database description must not be empty', 'alert-danger')
			return redirect(url_for('database_view', database_id=database_id))

		# Update details
		cur = g.db.cursor(mysql.cursors.DictCursor)
		cur.execute('UPDATE `databases` SET `description` = %s, `owner` = %s WHERE `id` = %s', (database_desc, database_owner, database_id))
		g.db.commit()
		
		## Now try to change password, if required
		if 'database_passwd' in request.form and len(request.form['database_passwd']) > 0:
			
			## Talk to the server via HTTPS
			try:
				json_response = mysqladm.core.msg_node(server,'passwd',name=database['name'], passwd=request.form['database_passwd'])
	
				if 'status' not in json_response:
					return mysqladm.errors.output_error('Unable to change database password', 'The mysql server responded with something unexpected: ' + str(json_response), '')
	
				if json_response['status'] != 0:
					if 'error' in json_response:
						return mysqladm.errors.output_error('Unable to change database password','The mysql server responded with an error: ' + str(json_response['error']),'core.msg_node error')
					else:
						return mysqladm.errors.output_error('Unable to change database password','The mysql server responded with an error status code: ' + str(json_response['status']),'core.msg_node status no error')
	
				flash('Database details successfully changed', 'alert-success')
				session['dbpasswd'] = request.form['database_passwd']
				return redirect(url_for('database_details',database_id=database_id))
	
			except requests.exceptions.RequestException as e:
				return mysqladm.errors.output_error('Unable to change database password','An error occured when communicating with the MySQL node: ' + str(e),'')	

		# Notify that we've succeeded
		flash('Database details successfully changed', 'alert-success')

		# redirect to server view
		return redirect(url_for('database_view', database_id=database_id))
		
################################################################################
#### PRINT DATABASE DETAILS AFTER CREATION OR PASSWORD CHANGE

@app.route('/database/<database_id>/details', methods=['GET'])
@mysqladm.core.login_required
def database_details(database_id):
	"""View function to print the connection-string like view for easy pasting
	into tickets or e-mails.
	"""
	## Get database
	database = get_database_by_id(database_id)
	if database == None:
		return mysqladm.errors.output_error('No such database','I could not find the database you were looking for! ','')

	## Get the server which hosts the database
	server = mysqladm.servers.get_server_by_hostname(database['server'])
	if server == None:
		return mysqladm.errors.output_error('No such server','I could not find the server the database resides on! ','')	

	## Check permissions to the server
	if not session['admin']:
		if not mysqladm.servers.user_is_delegate(server['id']):
			abort(403)
			
	dbpasswd = 'N/A - Only available when setting or changing password'
	if 'dbpasswd' in session:
		if len(session['dbpasswd']) > 0:
			dbpasswd = session['dbpasswd']
			session['dbpasswd'] = ''
	
	return render_template('database_created.html', active='databases', db=database, server=server, passwd=dbpasswd)
		
################################################################################
#### RESET DATABASE PASSWORD TO RANDOM PASSWORD

@app.route('/database/<database_id>/passwd', methods=['POST'])
@mysqladm.core.login_required
def database_passwd_rng(database_id):
	"""View function to change the password of a DB to a random password.
	"""
	
	database = get_database_by_id(database_id)
	if database == None:
		return mysqladm.errors.output_error('No such database','I could not find the database you were trying to edit! ','')

	## Load the server for the database
	server = mysqladm.servers.get_server_by_hostname(database['server'])
	if server == None:
		return mysqladm.errors.output_error('No such server','I could not find the server the database resides on! ','')

	## Check permissions to the server
	if not session['admin']:
		if not mysqladm.servers.user_is_delegate(server['id']):
			abort(403)		

	## Now try to change password
	new_passwd = mysqladm.core.pwgen()
	
	try:
		json_response = mysqladm.core.msg_node(server,'passwd',name=database['name'], passwd=new_passwd)

		if 'status' not in json_response:
			return mysqladm.errors.output_error('Unable to change database password', 'The mysql server responded with something unexpected: ' + str(json_response), '')

		if json_response['status'] != 0:
			if 'error' in json_response:
				return mysqladm.errors.output_error('Unable to change database password','The mysql server responded with an error: ' + str(json_response['error']),'core.msg_node error')
			else:
				return mysqladm.errors.output_error('Unable to change database password','The mysql server responded with an error status code: ' + str(json_response['status']),'core.msg_node status no error')

	except requests.exceptions.RequestException as e:
		return mysqladm.errors.output_error('Unable to change database password','An error occured when communicating with the MySQL node: ' + str(e),'')	

	# redirect to details view
	session['dbpasswd'] = new_passwd
	flash('Database password successfully changed', 'alert-success')
	return redirect(url_for('database_details',database_id=database_id))
		
################################################################################
#### DELETE DATABASE INSTANCE

@app.route('/database/<database_id>/delete', methods=['POST'])
@mysqladm.core.login_required
def database_delete(database_id):
	"""View function to delete a database.
	"""
	
	database = get_database_by_id(database_id)
	if database == None:
		return mysqladm.errors.output_error('No such database','I could not find the database you were trying to edit! ','')

	## Try to load the server
	server = mysqladm.servers.get_server_by_hostname(database['server'])
	if server == None:
		return mysqladm.errors.output_error('No such server','I could not find the server the database resides on! ','')

	## Check permissions to the server
	if not session['admin']:
		if not mysqladm.servers.user_is_delegate(server['id']):
			abort(403)		

	try:
		json_response = mysqladm.core.msg_node(server,'drop',name=database['name'])

		if 'status' not in json_response:
			return mysqladm.errors.output_error('Unable to delete database instance', 'The mysql server responded with something unexpected: ' + str(json_response), '')

		if json_response['status'] != 0:
			if 'error' in json_response:
				return mysqladm.errors.output_error('Unable to delete database instance','The mysql server responded with an error: ' + str(json_response['error']),'core.msg_node error')
			else:
				return mysqladm.errors.output_error('Unable to delete database instance','The mysql server responded with an error status code: ' + str(json_response['status']),'core.msg_node status no error')

	except requests.exceptions.RequestException as e:
		return mysqladm.errors.output_error('Unable to change database password','An error occured when communicating with the MySQL node: ' + str(e),'')	

	## Delete the database record
	mysqladm.databases.delete_database_record(database_id)
		
	flash('Database instance deleted successfully', 'alert-success')
	return redirect(url_for('server_view', server_name=database['server']))

################################################################################
#### CREATE DATABASE

@app.route('/databases/create', methods=['GET','POST'])
@mysqladm.core.login_required
def database_create():
	"""View function to create a new database instance on a server.
	"""	

	if request.method == 'GET':
		flash('To create a database first choose a server to create the database on. Use the filters and sorting options to choose the right place to put the database','alert-info')
		return redirect(url_for('isotope'))
		
	else:

		# Grab the fields
		if 'server_hostname' in request.form and len(request.form['server_hostname']) > 0:
			hostname = request.form['server_hostname']
		else:
			return mysqladm.errors.output_error('Unable to create database', 'You must specify a server to create the database on','')

		if 'database_name' in request.form and len(request.form['database_name']) > 0:
			name = request.form['database_name']
			if re.search('^[A-Za-z_][A-Za-z0-9_]*$', name) == None:
				return mysqladm.errors.output_error('Unable to create database', 'Invalid character(s) in database name','')	
		else:
			return mysqladm.errors.output_error('Unable to create database', 'You must specify a database name','')

		if 'database_desc' in request.form and len(request.form['database_desc']) > 0:
			description = request.form['database_desc']
			if not mysqladm.core.is_valid_desc(description):
				return mysqladm.errors.output_error('Unable to create database', 'Invalid character(s) in description','')
		else:
			return mysqladm.errors.output_error('Unable to create database', 'You must specify a database description','')

		if 'database_owner' in request.form and len(request.form['database_owner']) > 0:
			owner = request.form['database_owner']
			if re.search(r'^[A-Za-z0-9_\s\-\.\@\&\\/\(\)\[\]]*$', owner) == None:
				return mysqladm.errors.output_error('Unable to create database', 'Invalid character(s) in owner field','')
		else:
			return mysqladm.errors.output_error('Unable to create database', 'You must specify a database owner','')

		genpasswd = False

		if 'database_passwd' in request.form and len(request.form['database_passwd']) > 0:
			passwd = request.form['database_passwd']
			## dont validate the password. There really is not point even trying.
		else:
			## Generate a password if one was not sent
			passwd = mysqladm.core.pwgen()
		
			## Remember we set a password randomly
			genpasswd = True
		
		## Try to load the server details
		server = mysqladm.servers.get_server_by_hostname(hostname)
		if server == None:
			return mysqladm.errors.output_error('No such server','I could not find the server you were looking for! ','')

		## Check permissions to the server
		if not session['admin']:
			if not mysqladm.servers.user_is_delegate(server['id']):
				abort(403)
			
		## Check to make sure a database instance doesn't already exist on the server according to our database
		existing_db = get_database(name,server['id'])
		if not existing_db == None:
			return mysqladm.errors.output_error('Database already exists','There is already a database of that name residing on the selected server ','get_database returned true') 

		## Talk to the server via HTTPS
		try:
			json_response = mysqladm.core.msg_node(server,'create',name=name, passwd=passwd)

			if 'status' not in json_response:
				return mysqladm.errors.output_error('Unable to create database', 'The mysql server responded with something unexpected: ' + str(json_response), '')

			if json_response['status'] != 0:
				if 'error' in json_response:
					return mysqladm.errors.output_error('Unable to create database','The mysql server responded with an error: ' + str(json_response['error']),'core.msg_node error')
				else:
					return mysqladm.errors.output_error('Unable to create database','The mysql server responded with an error status code: ' + str(json_response['status']),'core.msg_node status no error')

		except requests.exceptions.RequestException as e:
			return mysqladm.errors.output_error('Unable to create database','An error occured when communicating with the MySQL node: ' + str(e),'')	

		## create database record
		database_id = mysqladm.databases.insert_database_record(server['id'], name, owner, description)

		# redirect to database details view
		session['dbpasswd'] = passwd
		flash('Database successfully created', 'alert-success')
		return redirect(url_for('database_details',database_id=database_id))

