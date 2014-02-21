import sys
sys.path.insert(0, '/data/mysqladm2/')
from flask.ext.script import Manager
from mysqladm.fapp import WrapFlask

app = WrapFlask(__name__)
manager = Manager(app)

@manager.command
def hello():
	print "hello"

if __name__ == "__main__":
	manager.run()
