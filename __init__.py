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

from flask import Flask
import logging
from logging.handlers import SMTPHandler
from logging.handlers import RotatingFileHandler
from logging import Formatter
from mysqladm.fapp import WrapFlask

################################################################################
#### Default config options

## Debug mode. This engages the web-based debug and disables logging.
DEBUG = False

## Session signing key
# Key used to sign/encrypt session data stored in cookies.
SECRET_KEY = ''

## Kerberos configuration
KRB5_SERVICE = 'krbtgt/localdomain'
KRB5_DOMAIN  = 'localhost.localdomain'

## Logging and alerts
LOG_DIR='logs'
LOG_FILE='mysqladm.log'
EMAIL_ALERTS=False
ADMINS=['root']
SMTP_SERVER='localhost'
EMAIL_FROM='root'

## Database connection
DB_SERV='localhost'
DB_NAME='mysqladm'
DB_USER='mysqladm'
DB_PASS='mysqladm'
DB_PORT='3306'

################################################################################


# set up our application
app = WrapFlask(__name__)

# load default config
app.config.from_object(__name__)

# try to load config from various paths 
app.config.from_pyfile('/etc/mysqladm2.conf', silent=True)
app.config.from_pyfile('/etc/mysqladm2/master.conf', silent=True)
app.config.from_pyfile('/opt/mysqladm2/mysqladm2.conf', silent=True)
app.config.from_pyfile('/data/mysqladm2/mysqladm2.conf', silent=True)
app.config.from_envvar('MYSQLADM_CONFIG_FILE', silent=True)

# set up e-mail alert logging
if not app.debug:
	if app.config['EMAIL_ALERTS'] == True:

		mail_handler = SMTPHandler(app.config['SMTP_SERVER'],
			app.config['EMAIL_FROM'],
			app.config['ADMINS'], 
			'MySQLadm Application Error')

		mail_handler.setLevel(logging.ERROR)
		mail_handler.setFormatter(Formatter("""
A fatal error occured in mysqladm.

Message type:       %(levelname)s
Location:           %(pathname)s:%(lineno)d
Module:             %(module)s
Function:           %(funcName)s
Time:               %(asctime)s
Logger Name:        %(name)s
Process ID:         %(process)d

Further Details:

%(message)s

"""))

		app.logger.addHandler(mail_handler)
	
	## Set up file logging as well
	file_handler = RotatingFileHandler(app.config['LOG_DIR'] + '/' + app.config['LOG_FILE'], 'a', 1 * 1024 * 1024, 10)
	file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
	app.logger.setLevel(logging.INFO)
	file_handler.setLevel(logging.INFO)
	app.logger.addHandler(file_handler)
	app.logger.info('mysqladm2 started up')


################################################################################

# load core functions
import mysqladm.core

# load anti csrf function reference into template engine
app.jinja_env.globals['csrf_token'] = core.generate_csrf_token 

# import modules
import mysqladm.errors
import mysqladm.views
import mysqladm.servers
import mysqladm.databases