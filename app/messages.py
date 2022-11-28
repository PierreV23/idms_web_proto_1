import json
import os
from flask import current_app
from flask_login import current_user

def maxid_key():
    return f"{current_app.config.get('ENV', 'none')}::maxmsgid"

def read_messagefile():
    messages = []
    messageobject = os.path.join('/', current_user.irods_zone, current_app.config.get("MESSAGES_OBJECT","none"))
    if current_user.ifs.fileexists(messageobject):
        obj = current_user.ifs.getfile(messageobject)
        messages_json = obj.open('r').read().decode('utf-8')
        messages = json.loads(messages_json)
    return messages

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