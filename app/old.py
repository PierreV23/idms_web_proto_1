from irods.column import Criterion
from irods.session import iRODSSession
from irods.models import Collection, CollectionMeta, DataObject, User, UserGroup, UserMeta
from irods.query import SpecificQuery
import os
from datetime import datetime
import tempfile
import time
import yaml
import json
from fs_base import factory
import fs_irods
import sys
import subprocess
import ssl

from flask import Flask, request, render_template, redirect, Blueprint
from flask import jsonify
#app = Flask(__name__)

bp = Blueprint('old', __name__, url_prefix='/old')

f = open("secret","r")
rodspassword = f.readline()
f.close()

context = ssl._create_unverified_context(purpose=ssl.Purpose.SERVER_AUTH,
                                     cafile=None, capath=None, cadata=None)
ssl_settings = {'irods_ssl_ca_certificate_file': '/etc/irods/ssl/irods.crt',
                'ssl_context': context }
#ssl_settings = {'irods_ssl_ca_certificate_file': 'irods.test.crt',
#                'ssl_context': context }
#irods_session = iRODSSession(host='rivm-bioir-l01p.rivm.ssc-campus.nl',
#                             port=1247,
#                             user='rods',
#                             password=rodspassword,
#                             zone='rivmZone',
#                             **ssl_settings)

#ifs = factory.getfs('irods', session = irods_session)

def sortKey(X):
    return(X['startTime'])

def test_if_lsf_installed():
    try:
       subprocess.getoutput("bhosts -h")
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
        st = 0
    try:
        et = int(md.get_one('TIME::finishTime').value)
        strEt = datetime.utcfromtimestamp(et).strftime('%Y-%m-%d %H:%M:%S')
    except KeyError:
        strEt = "-"
        et = 0
    try:
        ic = md.get_one('RUN::input_coll').value
    except KeyError:
        ic = ''
    try:
        oc = md.get_one('RUN::output_coll').value
    except KeyError:
        oc = ''
    try:
        nextproj = yy['next_projectID']
    except:
        nextproj = ''
    try:
        description = yy['description']
    except:
        description = ''
    try:
        repo = yy['repo']
    except:
        repo = ''
    try:
        tag = yy['tag']
    except:
        tag = ''    
    details = {'name':jobfileObject.name, 'description': description, 'repo' : repo, 'tag': tag,
            'exit_code': ec, 'startTime': strSt, 'endTime': strEt, 'input_coll': ic, 'output_coll': oc, 'startTimestamp': st, 'next_projectID': nextproj}
    return details

def joblist(state):
    a = []
    b = []
    coll = irods_session.collections.get('/rivmZone/system/runsheet/' + state)
    for job in coll.data_objects:
        jd = jobdetails(job)
        jd['state'] = state
        a.append({'start':jd['startTimestamp'], 'details':jd})
    for job  in sorted(a, key = lambda x: x['start'], reverse = True):    
        b.append(job['details'])
    return b

def collist(path):
    avu=[]
    query = irods_session.query(CollectionMeta.name, CollectionMeta.value, CollectionMeta.units).filter(Criterion('=', Collection.name, path))
    for result in query:
         name = result[CollectionMeta.name]
         value = result[CollectionMeta.value]
         units = result[CollectionMeta.units]
         avu.append({'name': name, 'value': value,'units': units})
         print(name,value,units)
    cols = []
    objs = []
    for obj in ifs.ls(path):
        objdict = {'name': obj.shortname(), 'path': obj.path}
        if obj.isdir():
            query = irods_session.query(Collection.create_time, Collection.owner_name).filter(Criterion('=', Collection.name, obj.path))
            for result in query:
                ct = result[Collection.create_time]
                on = result[Collection.owner_name]
                objdict['datetime'] = ct
                objdict['ownername'] = on
            cols.append(objdict)
            #print ("cols is nu:", cols)
        else:
            objdict['size'] = obj.filesize()
            objdict['create_time'] = obj.create_time()
            objdict['owner_name'] = obj.owner_name()
            objs.append(objdict)
    print("path: ", path)
    #print("ifs.ls(path): ", ifs.ls(path))
    print("cols: ", cols)
    print("objs: ", objs)
    return cols, objs, avu

@bp.route('/')
def home():
    return render_template('home.html')

@bp.route('/collbrowser')
def collbrowser():
    path = request.args.get('path', '/rivmZone/projects', type=str)
    action = request.args.get('action', 'none', type=str)
    if action == "up":
        path = '/' + '/'.join(path.split('/')[1:-1])
        
    query = irods_session.query(Collection.name).filter(
            Criterion('=', CollectionMeta.name, 'RUN::input_coll')).filter(
                    Criterion('=', CollectionMeta.value, path))
    rel_colls = [ c[Collection.name] for c in query]
    print("rel_cols", rel_colls)

    c, o, a = collist(path)
    return render_template('collbrowser.html', cols = c, objs = o, avu = a, path=path, rel_colls = rel_colls)

@bp.route('/docviewer')
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

@bp.route('/jobs')
def show_jobs():
    l = []
    for a in [ 'waiting', 'incoming', 'queued', 'active', 'done']:
        l = l + joblist(a)
    return render_template('jobs.html', joblist=l)

@bp.route('/jobs2')
def show_jobs2():
    x = request.args.get('items', 'all', type=str)
    l = []
    for a in [ 'waiting', 'incoming', 'queued', 'active', 'done' ]:
        if x in [ 'all', a]:
            l = l + joblist(a)
    return render_template('jobs2.html', joblist=l, items=x)

@bp.route('/clusterinfo')
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
    meta = irods_session.query(UserMeta.name, UserMeta.value).filter(Criterion('=', User.name, username))
    for m in meta:
        r[m[UserMeta.name]] = m[UserMeta.value]
    return r

def coll_metadata(coll):
    r = {}
    meta = irods_session.query(CollectionMeta.name, CollectionMeta.value).filter(Criterion('=', Collection.name, coll))
    for m in meta:
        r[m[CollectionMeta.name]] = m[CollectionMeta.value]
    return r


@bp.route('/hpcinfo')
def show_hpcinfo():
    x=1
    with open('/data/BioGrid/verhager/HPCrapport/rapport_twohago.txt', encoding='utf8') as f:
            text = f.read()
            if x==1:
                print(text)
            x+=1
    return render_template('hpcinfo.html', text=text)

@bp.route('/list', methods=['GET', 'POST'])
def login():
    coll = irods_session.collections.get('/rivmZone/home/rods')
    A = [ entry.path for entry in coll.data_objects ]
    print(A)
    return render_template('hello.html', objects=A)

@bp.route('/users')
def show_users():
    query = irods_session.query(User.name).order_by(User.name).filter(Criterion('!=', User.type, "rodsgroup"))
    U = [u[User.name] for u in query]
    return render_template('userlist.html', users=U)

@bp.route('/groups')
def show_groups():
    groupq = irods_session.query(User.name).order_by(User.name).filter(Criterion('!=', User.type, "rodsuser"))
    G = [ group[User.name] for group in groupq ]
    print(G)
    
#    for g in G:
#        ig = user_metadata(g)
#        print(ig)
    return render_template('grouplist.html', groups=G)

@bp.route('/groupdetails')
def show_groupdetails():
    groupnaam = request.args.get('group', '', type=str)
    group = irods_session.query(User.name).filter(Criterion('=', User.name, groupnaam))
    D = {}
    D['name'] = groupnaam
    meta = user_metadata(groupnaam)
    if 'projectID' in meta:
        D['projectID'] = meta['projectID']
    try:
        D['adgroup'] = meta['SYNC::adgroup']
    except:
        D['adgroup'] = ''
        
    return render_template('groupdetails.html', details=D)

@bp.route('/jobdetails')
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
    D['Next projectID'] = "<a href='/projectdetails?name={0}'>{0}</a>".format(jd['next_projectID'])
    return render_template('jobdetails.html', details=D, jobnaam = jobnaam)

@bp.route('/projects')
def show_projects():
    P = {}
    obj = ifs.getfile('/rivmZone/system/files/pipelinesettings.json')
    with obj.open('r') as f:
        pl = json.load(f)
    for project in sorted(pl):
        P[project] = {'name': project, 'details': pl[project]}   
    return render_template('projects.html', projects=P)

@bp.route('/datasets')
def show_datasets():
    ds = []
    query = irods_session.query(Collection.name).filter(
            Criterion('=',CollectionMeta.name, 'projectID'))
    for q in query:
        X = {'name': q[Collection.name]}
        meta = coll_metadata(X['name'])
        X.update(meta)
        print(X)
        ds.append(X)
    return render_template('datasets.html', datasets=ds)
    
@bp.route('/projectdetails')
def show_projectdetails():
    PD = {}
    projectnaam = request.args.get('name', '', type=str)
    processnaam = request.args.get('process', '', type=str)
    obj = ifs.getfile('/rivmZone/system/files/pipelinesettings.json')
    with obj.open('r') as f:
        config = json.load(f)
    # Retrieve grousp associated with project
    query = irods_session.query(User.name).filter(
            Criterion('!=', User.type, "rodsuser")).filter(
                    Criterion('=', UserMeta.name, "projectID")).filter(
                            Criterion('=', UserMeta.value, projectnaam)).order_by(User.name)
    groups = [u[User.name] for u in query]    
    PD['name'] = projectnaam
    for attr in ['description', 'default_collection','service_account']:
        try:
            PD[attr] = config[projectnaam]['settings'][attr]
        except:
            PD[attr] = ''
    PD['groups'] = groups
    PD['conf'] = config[projectnaam]
    PD['processes'] = [proc for proc in sorted(config[projectnaam]['processes'])]

    # Retrieve collections associated with project
    query = irods_session.query(Collection.name).filter(
            Criterion('=',CollectionMeta.name, 'projectID')).filter(
                    Criterion('=',CollectionMeta.value, projectnaam))
    PD['colls'] = [q[Collection.name] for q in query]
    return render_template('projectdetails.html', PD = PD, conf = config, processnaam = processnaam)

def write_jsonfile(filepath, jsondict):
    jsonstr = json.dumps(jsondict, sort_keys = True, indent = 4)
    obj = ifs.getfile(filepath)
    with obj.open('w') as f:
            f.write(jsonstr.encode())

def read_jsonfile(filepath):
    obj = ifs.getfile(filepath)
    with obj.open('r') as f:
            pl = json.load(f)
    return pl


@bp.route('/update_project', methods=['GET','POST'])
def update_projectsettings():
    
    def add_checkbox(data, attr, name):
        if name in attr:
            data[name] = 'true'
        else:
            data[name] = 'false'
        return data
    
    requestdata = request.form.to_dict()
    viewProcess=''
    project = requestdata['project']
    try:
        process = requestdata['process']
    except:
        process = 'none'

    print(requestdata)
    config = read_jsonfile('/rivmZone/system/files/pipelinesettings.json')
    if requestdata['action'] == 'update_process':
        processConfig = config[project]['processes'][process]
        for attr in ['description', 'repo', 'tag', 'output_prefix', 'next_projectID', 'next_processID' ]:
            processConfig[attr] = requestdata[attr]
        add_checkbox(processConfig, requestdata, 'modify_in_place')
        add_checkbox(processConfig, requestdata, 'restartable')
        add_checkbox(processConfig, requestdata, 'distribution')
        viewProcess = process
    elif requestdata['action'] == 'add_process':
        if requestdata['process']:
            newProcess = requestdata['process']
            config[project]['processes'][newProcess] = {'next_projectID': 'none', 'next_processID': 'none'}
            viewProcess = newProcess
    elif requestdata['action'] == 'delete_process':
        del config['project']['processes'][process]
        viewProcess = 'none'
    elif requestdata['action'] == 'update_project':
        if not 'settings' in config[project]:
            config[project]['settings'] = {}
        projectSettings = config[project]['settings']
        for attr in ['description', 'default_collection','service_account']:
            projectSettings[attr] = requestdata[attr]
    write_jsonfile('/rivmZone/system/files/pipelinesettings.json', config)
    return("<script> window.location.href ='/projectdetails?name={0}&process={1}'; </script>".format(requestdata['project'], viewProcess))


@bp.route('/get_process', methods=['GET','POST'])
def get_process():
    data = request.form.to_dict()
    pl = read_jsonfile('/rivmZone/system/files/pipelinesettings.json')
    processes = [ p for p in pl.get(data['project']['processes']) ]
    return(jsonify(processes))


@bp.route('/submit_runsheet', methods=['POST'])
def submit_runsheet():
    """Write a runsheet.yml file to the incoming collection with data from the
    request (i.e. form submission)."""
    data = request.form.to_dict()

    # Handle checkboxes
    for field in ('modify_in_place', 'restartable', 'distribution'):
        if field not in data:
            data[field] = 'false'

    # Write runsheet to a temporary location. Note: we cannot write
    # to the /incoming collection directly, as it renames the data
    # object before we can write its contents.
    fd, temppath = tempfile.mkstemp()
    with open(fd, 'w') as f:
        f.write(yaml.dump(data, explicit_start=True, default_flow_style=False))
    runsheet_location = '/rivmZone/system/runsheet/incoming/runsheet.yaml'
    irods_session.data_objects.put(temppath, runsheet_location)
    
    # Cleanup temp file.
    os.unlink(temppath)

    return redirect('/old/jobs2')

