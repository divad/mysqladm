import sys
sys.path.insert(0, '/data/mysqladm2/')
from flask.ext.script import Manager
from mysqladm.fapp import WrapFlask

app = WrapFlask(__name__)
manager = Manager(app)

@manager.command
@manager.option('-s', '--server', help='What server to sync from, default all',required=False)
def agentsync(server):
	## Load servers
	rows = mysqladm.servers.get_all_servers()
	
	for row in rows:
		print row['name']
    
if __name__ == "__main__":
	manager.run()
