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
import ssl

from flask import Flask, request, render_template
app = Flask(__name__)

f = open("secret","r")
rodspassword = f.readline()
f.close()

context = ssl._create_unverified_context(purpose=ssl.Purpose.SERVER_AUTH,
                                     cafile=None, capath=None, cadata=None)
ssl_settings = {'irods_ssl_ca_certificate_file': '/etc/irods/ssl/irods.crt',
                'ssl_context': context }
irods_session = iRODSSession(host='rivm-bioir-l01p.rivm.ssc-campus.nl',
                             port=1247,
                             user='rods',
                             password=rodspassword,
                             zone='rivmZone',
                             **ssl_settings)

ifs = factory.getfs('irods', session = irods_session)

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

def jobdetails(jobfileObject):
    with jobfileObject.open('r+') as f:
        txt = f.read();
        yy = yaml.load(txt)
    md = jobfileObject.metadata
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
        ic = md.get_one('RUN::input_coll').value
    except KeyError:
        ic = ''
    try:
        oc = md.get_one('RUN::output_coll').value
    except KeyError:
        oc = ''
    details = {'name':jobfileObject.name, 'repo' : yy['repo'], 'tag': yy['tag'],
            'exit_code': ec, 'startTime': strSt, 'endTime': strEt, 'input_coll': ic, 'output_coll': oc}
    return details

def joblist(state):
    a = []
    coll = irods_session.collections.get('/rivmZone/system/runsheet/' + state)
    for job in coll.data_objects:
        jd = jobdetails(job)
        jd['state'] = state
        a.append(jd)
    return a

def collist(path):
    cols = []
    objs = []
    for obj in ifs.ls(path):
        objdict = {'name': obj.shortname(), 'path': obj.path}
        if obj.isdir():
            #objdict['create_time'] = obj.create_time()
            #objdict['owner_name'] = obj.owner_name()
            cols.append(objdict)
        else:
            objdict['size'] = obj.filesize()
            objdict['create_time'] = obj.create_time()
            objdict['owner_name'] = obj.owner_name()
            objs.append(objdict)
    print("path: ", path)
    print("ifs.ls(path): ", ifs.ls(path))
    print("cols: ", cols)
    print("objs: ", objs)
    return cols, objs

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/collbrowser')
def collbrowser():
    path = request.args.get('path', '/rivmZone/projects', type=str)
    action = request.args.get('action', 'none', type=str)
    if action == "up":
        path = '/' + '/'.join(path.split('/')[1:-1])
        
    c, o = collist(path)
    return render_template('collbrowser.html', cols = c, objs = o, path=path)

@app.route('/docviewer')
def docviewer():
    path = request.args.get('path', '/', type=str)
    action = request.args.get('action', 'none', type=str)
    filename, file_extension = os.path.splitext( path.lower() )
    fn = os.path.basename( path.lower() )
        
    print("path, filename, file_extension: ", path, fn, file_extension)
    #obj = fs_irods.fs_irods( path ).getfile( path )
    obj = ifs.getfile(path)
    with obj.open('r') as f:
        a = f.read( 500000 )
    #print (a)
    try:
        doc = a.decode('utf-8')
    except:
        f = open("static/images/pic_trulli" + file_extension, "wb")
        f.write(a)
        f.close()
        doc="Deze file kan niet gelezen worden"
    return render_template('docviewer.html', doc = doc, path = path, fn = fn, file_extension = file_extension)

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

    bjobs=getinfo("bjobs -u svc-sscc-irods -o \"JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME   SUBMIT_TIME: delimiter='^'\"", "^")
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

@app.route('/jobdetails')
def show_jobdetails():
    jobnaam = request.args.get('name', '', type=str)
    # We want the full path to the job runsheet object
    query = irods_session.query(Collection.name).filter(Criterion('=', DataObject.name, jobnaam))
    jobpath = [ coll[Collection.name] for coll in query]
    runsheet = jobpath[0] + '/' + jobnaam
    jobObj = irods_session.data_objects.get(runsheet)
    jd = jobdetails(jobObj)
    D = {}
    D['Runsheet File'] = "<a href='/docviewer?path=" + runsheet + "'>" + jobnaam + "</a>"
    D['Job Start Time'] = jd['startTime']
    D['Job End   Time'] = jd['endTime']
    D['Input  collection'] = "<a href='/collbrowser?path={0}'>{0}</a>".format(jd['input_coll'])
    D['Output collection'] = "<a href='/collbrowser?path={0}'>{0}</a>".format(jd['output_coll'])
    D['Git repository'] = "<a href='{0}'>{0} TAG {1}</a>".format(jd['repo'].replace('.git',''), jd['tag'])
    return render_template('jobdetails.html', details=D, jobnaam = jobnaam)

#    details = {'name':jobfileObject.name, 'repo' : yy['repo'], 'tag': yy['tag'],
#            'exit_code': ec, 'startTime': strSt, 'endTime': strEt, 'output_coll': oc}