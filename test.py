#!/usr/bin/python

import requests
payload = {'function': 'list', 'password': 'redhat'}
r = requests.get('https://uos-app00302-vs.soton.ac.uk:1337/', params=payload, verify=False)
print r.text
