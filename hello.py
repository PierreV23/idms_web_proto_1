from irods.column import Criterion
from irods.session import iRODSSession
from irods.models import Collection, CollectionMeta, DataObject, User, UserGroup
from irods.query import SpecificQuery
import os
from datetime import datetime
import time
import yaml
from fs_base import factory
import fs_irods
import sys
import subprocess

from flask import Flask, request, render_template
app = Flask(__name__)

try:
    env_file = os.environ['IRODS_ENVIRONMENT_FILE']
except KeyError:
    env_file = os.path.expanduser('~/.irods/irods_environment.json')
irods_session = iRODSSession(irods_env_file=env_file)

ifs = factory.getfs('irods')

def sortKey(X):
    return(X['startTime'])

def test_if_lsf_installed():
    try:
       subprocess.getoutput("xbhosts -h")
    except:
       sys.exit("LFS is not installed")

def getinfo(command, splitchar):
    z=subprocess.getoutput(command)
    output=[]
    for regel in z.split("\n"):
        if splitchar=="":
            output.append(regel.split())
        else:
            output.append(regel.split(splitchar))
    return(output)

def joblist(state):
    a = []
    coll = irods_session.collections.get('/rivmZone/home/rods/runsheet/' + state)
    for job in coll.data_objects:
        with job.open('r+') as f:
            txt = f.read();
            yy = yaml.load(txt)
        md = job.metadata
        print(md.items())
        try: 
            ec = md.get_one('RUN::exit_code').value
        except KeyError:
            ec = -1
        try:
            st = int(md.get_one('TIME::startTime').value)
            strSt = datetime.utcfromtimestamp(st).strftime('%Y-%m-%d %H:%M:%S')
        except KeyError:
            strSt = "-"
        try:
            et = int(md.get_one('TIME::finishTime').value)
            strEt = datetime.utcfromtimestamp(et).strftime('%Y-%m-%d %H:%M:%S')
        except KeyError:
            strEt = "-"
        try:
            od = md.get_one('RUN::output_dir').value
        except KeyError:
            od = ''
        a.append({'name':job.name, 'repo' : yy['repo'], 'tag': yy['tag'], 'state': state,
            'exit_code': ec, 'startTime': strSt, 'endTime': strEt, 'output_dir': od})
        a.sort(key = sortKey, reverse = True)
    return a

def collist(path):
    cols = []
    objs = []
    for obj in ifs.ls(path):
        objdict = {'name': obj.shortname(), 'path': obj.path}
        if obj.isdir():
            cols.append(objdict)
        else:
            objdict['size'] = obj.filesize()
            objs.append(objdict)
    return cols, objs


@app.route('/')
def home():
    return render_template('home.html')

@app.route('/collbrowser')
def collbrowser():
    path = request.args.get('path', '/', type=str)
    action = request.args.get('action', 'none', type=str)
    if action == "up":
        path = '/' + '/'.join(path.split('/')[1:-1])
        
    c, o = collist(path)
    return render_template('collbrowser.html', cols = c, objs = o, path=path)


@app.route('/jobs')
def show_jobs():
    l = []
    for a in [ 'incoming', 'queued', 'active', 'done' ]:
        l = l + joblist(a)
    return render_template('jobs.html', joblist=l)

@app.route('/jobs2')
def show_jobs2():
    x = request.args.get('items', 'all', type=str)
    l = []
    for a in [ 'incoming', 'queued', 'active', 'done' ]:
        if x in [ 'all', a]:
            l = l + joblist(a)
    return render_template('jobs2.html', joblist=l, items=x)

@app.route('/clusterinfo')
def show_clusterinfo():
    test_if_lsf_installed()
    bhosts=getinfo("bhosts -w bioinfo", "")
    bhostsh=bhosts[0]
    bhosts.pop(0)

    busers=getinfo("busers all", "")
    busers_active=[]
    for teller in range(len(busers)):
        if busers[teller][3] != "0" and busers[teller][3] != "-":
            busers_active.append((busers[teller]))
    busersh=busers[0]
    busers.pop(0)
    busers_active.pop(0)

    bjobs=getinfo("bjobs -uall -o \"JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME   SUBMIT_TIME: delimiter='^'\"", "^")
    bjobsh=bjobs[0]
    bjobs.pop(0)

    lsload=getinfo("lsload -w| grep -e rivm.ssc-campus.nl -e HOST_NAME| sort -n","")
    lsloadh=lsload[0]
    lsload.pop(0)

    return render_template('clusterinfo.html', bhostsh=bhostsh, bhosts=bhosts, busersh=busersh, busers=busers_active, bjobsh=bjobsh, bjobs=bjobs, lsloadh=lsloadh, lsload=lsload, items="all")

def user_metadata(username):
    r = {}
    sql = "select META_USER_ATTR_NAME, META_USER_ATTR_VALUE where USER_NAME = '" + username + "'"
    print(sql)
    query = SpecificQuery(irods_session, sql=sql)
    _ = query.register()
    for result in query:
        print(result)
#        r[result['META_USER_ATTR_NAME']] = result['META_USER_ATTR_VALUE']
    _ = query.remove()
    return r

@app.route('/hpcinfo')
def show_hpcinfo():
    x=1
    with open('/data/BioGrid/verhager/HPCrapport/rapport_twohago.txt', encoding='utf8') as f:
            text = f.read()
            if x==1:
                print(text)
            x+=1
    return render_template('hpcinfo.html', text=text)

@app.route('/list', methods=['GET', 'POST'])
def login():
    coll = irods_session.collections.get('/rivmZone/home/rods')
    A = [ entry.path for entry in coll.data_objects ]
    print(A)
    return render_template('hello.html', objects=A)

@app.route('/users')
def show_users():
    query = irods_session.query(User.name).order_by(User.name).filter(Criterion('!=', User.type, "rodsgroup"))
    U = [u[User.name] for u in query]
    return render_template('userlist.html', users=U)

@app.route('/groups')
def show_groups():
    groupq = irods_session.query(UserGroup.name).order_by(UserGroup.name).filter(Criterion('=', User.type, "rodsgroup"))
    G = [ group[UserGroup.name] for group in groupq ]
    for g in G:
        ig = user_metadata(g)
        print(ig)
    return render_template('grouplist.html', groups=G)
