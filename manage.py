import sys
sys.path.insert(0, '/data/mysqladm2/')
from flask.ext.script import Manager
from mysqladm.fapp import WrapFlask

app = WrapFlask(__name__)
manager = Manager(app)

@manager.command
def agentsync():
	option_list = ( Option('--server', '-s', dest='server_name'))
    
	## Load servers
	rows = mysqladm.servers.get_all_servers()
	
	for row in rows:
		print row['name']
    
	print "hello"

if __name__ == "__main__":
	manager.run()
