from flask import jsonify, Blueprint, request
from app.messages import load_headermessages, write_headermessages

bp = Blueprint('messages', __name__, url_prefix='/messages')

@bp.route('/api', methods=['GET', 'POST'])
def message_api():
    if request.method == 'GET':
        msgs = load_headermessages()
        return jsonify(msgs)
    elif request.method == 'POST':
        requestdata = request.form.to_dict()
        messages = {}
        for k, v in requestdata.items():
            i, tag = k.split('_')
            if tag == 'time':
                times = v.split(' - ')
                if len(times) == 2:
                    start, end = times
                    messages.setdefault(i, {})['start'] = start
                    messages.setdefault(i, {})['end'] = end
            else:
                messages.setdefault(i, {})[tag] = v
        messagelist = list(messages.values())
        write_headermessages(messagelist)
    return messagelist