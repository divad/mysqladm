import sys
sys.path.insert(0, '/data/mysqladm2/')
from flask import Flask, g
from flask.ext.script import Manager
from mysqladm.fapp import WrapFlask
import mysqladm.servers
import mysqladm.core

app = WrapFlask(__name__)
manager = Manager(app)

@manager.command
@manager.option('-s', '--server', help='What server to sync from, default all',required=False)
def agentsync(server=''):
	## Load servers
	rows = mysqladm.servers.get_all_servers()
	
	for row in rows:
		print row['hostname']
		
@manager.command
def initdb():
	print "Function not implemented (yet)"
    
if __name__ == "__main__":
	g.db = mysqladm.core.db_connect()	
	manager.run()
