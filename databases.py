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


def get_database(db_name,server_id):
	## Load the dictionary based cursor
	cur = g.db.cursor(mysql.cursors.DictCursor)

	## Execute a SQL select
	cur.execute("SELECT * FROM `databases` WHERE `name` = %s AND `server` = %s", (db_name,server_id))

	## Get results
	return cur.fetchone()

################################################################################
#### LIST DATABASES

@app.route('/databases')
def database_list():
	## Load the dictionary based cursor
	cur = g.db.cursor(mysql.cursors.DictCursor)

	## Execute a SQL select
	cur.execute("SELECT `databases`.`id` AS 'id', `servers`.`hostname` AS `server`, `databases`.`name` AS 'name', `databases`.`owner` AS 'owner', `databases`.`description` AS 'description' FROM `databases` LEFT JOIN `servers` ON `servers`.`id` = `databases`.`server`")

	## Get results
	rows = cur.fetchall()

	for row in rows:
		row['link'] = url_for('database_view', database_id = row['id'])

	return render_template('databases.html', active='databases', rows=rows)

@app.route('/database/<database_id>')
def database_view(database_id):
	## Load the dictionary based cursor
	cur = g.db.cursor(mysql.cursors.DictCursor)

	## Execute a SQL select
	cur.execute("SELECT `databases`.`id` AS 'id', `servers`.`hostname` AS `server`, `databases`.`name` AS 'name', `databases`.`owner` AS 'owner', `databases`.`description` AS 'description' FROM `databases` LEFT JOIN `servers` ON `servers`.`id` = `databases`.`server` WHERE `databases`.`id` = %s",(database_id))

	## Get results
	database = cur.fetchone()

	## Return an error if there was no database
	if database == None:
		return mysqladm.errors.output_error('No such database','I could not find the database you were looking for! ','')

	return render_template('database.html', active='databases', db=database)

################################################################################
#### CREATE DATABASE

@app.route('/databases/create', methods=['GET','POST'])
def database_create():
	if request.method == 'GET':
		return render_template('database_create.html', active='database_create')
	elif request.method == 'POST':
	    
	    # Get a cursor to the database
		cur = g.db.cursor()

		# Grab the fields
		#### TODO VALIDATE THESE FIELDS
		if 'server_hostname' in request.form and len(request.form['server_hostname']) > 0:
			hostname = request.form['server_hostname']
		else:
			return mysqladm.errors.output_error('Unable to create database', 'You must specify a server to create the database on','')

		if 'database_name' in request.form and len(request.form['database_name']) > 0:
			name = request.form['database_name']
		else:
			return mysqladm.errors.output_error('Unable to create database', 'You must specify a database name','')

		# TODO verify and valdidate field contents are VALID

		if 'database_desc' in request.form and len(request.form['database_desc']) > 0:
			description = request.form['database_desc']
		else:
			return mysqladm.errors.output_error('Unable to create database', 'You must specify a database de   scription','')

		if 'database_owner' in request.form and len(request.form['database_owner']) > 0:
			owner = request.form['database_owner']
		else:
			return mysqladm.errors.output_error('Unable to create database', 'You must specify a database owner','')

        genpasswd = False

        if 'database_passwd' in request.form and len(request.form['database_passwd']) > 0:
			passwd = request.form['database_passwd']
		else:
			## Generate a password if one was not sent
			passwd = mysqladm.core.pwgen()
			   genpasswd = True

		## Try to load the server details
		server = mysqladm.servers.get_server_by_hostname(hostname)
		if server == None:
			return mysqladm.errors.output_error('No such server','I could not find the server you were looking for! ','')

		## Check to make sure a database instance doesn't already exist on the server according to our database
        existing_db = get_database(name,server['id'])
        if not existing_db == None:
           return mysqladm.errors.output_error('Database already exists','There is already a database of that name residing on the selected server ','get_database returned true') 
 
		## Talk to the server via HTTPS
		try:
			json_response = mysqladm.core.msg_node(server['hostname'],server['password'],'create',name=name, passwd=passwd)

			if 'status' not in json_response:
				return mysqladm.errors.output_error('Unable to create database', 'The mysql server responded with something unexpected: ' + str(json_response), '')

			if json_response['status'] != 0:
				if 'error' in json_response:
                    return mysqladm.errors.output_error("Unable to create database','The mysql server responded with an error: ' + str(json_response['error']),'core.msg_node error')
				else:
					return mysqladm.errors.output_error("Unable to create database','The mysql server responded with an error status code: ' + str(json_response['status']),'core.msg_node status no error')

		except requests.exceptions.RequestException as e:
			return mysqladm.errors.output_error('Unable to create database','An error occured when communicating with the MySQL node: ' + str(e),'')	

		# Create a record of the database in the database (yo dawg)
		cur.execute('INSERT INTO `databases` (`server`, `name`, `owner`, `description`) VALUES (%s, %s, %s, %s)', (server['id'], name, owner, description))

		# Commit changes to the database
		g.db.commit()

		## Last insert ID
		server_id = cur.lastrowid

		# Notify that we've succeeded
		if genpasswd:
		    flash("Database instance successfully created with generated password '" + passwd + "'",'alert-success')
		else:
		    flash('Database instance successfully created', 'alert-success')

		# redirect to server list
		return redirect(url_for('server_view',server_name=hostname))

