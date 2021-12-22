import json
import os
from flask import current_app
from flask_login import current_user

def maxid_key():
    return f"{current_app.config.get('ENV', 'none')}::maxmsgid"

def read_messagefile():
    msgfile = os.path.join(current_app.instance_path, 'messages.json')
    if os.path.isfile(msgfile):
        with open(msgfile, 'r') as f:
            return json.load(f)
    else:
        return None

def getmessages():
    login_messages = read_messagefile()
    max_id = current_user.settings.setdefault(maxid_key(), 0)
    if login_messages:
        messagelist = sorted(login_messages.get('messages', []), key=lambda x: x['id'])
        return [ message.get('txt') for message in messagelist if message.get('id', 0) > max_id ]
    else:
        return []

def confirm():
    login_messages = read_messagefile()
    max_id = max([ m.get('id', 0) for m in login_messages.get('messages') ])
    current_user.settings[maxid_key()] =  max_id