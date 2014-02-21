import sys
sys.path.insert(0, '/data/mysqladm2/')
from flask import Flask, g
from flask.ext.script import Manager
from mysqladm.fapp import WrapFlask
import mysqladm.servers
import mysqladm.core

app = WrapFlask(__name__)
manager = Manager(app,help='test2')

@manager.command
@manager.option('-s', '--server', help='What server to sync from, default all',required=False)
def agentsync(server=''):
	g.db = mysqladm.core.db_connect()

	## Load servers
	rows = mysqladm.servers.get_all_servers()
	
	for row in rows:
		print row['hostname']
		
@manager.command
def listservers():
	g.db = mysqladm.core.db_connect()

	## Load servers
	rows = mysqladm.servers.get_all_servers()
	
	for row in rows:
		print row['hostname']
		
@manager.command
def initdb():
	print "Function not implemented (yet)"
    
if __name__ == "__main__":
	manager.run()