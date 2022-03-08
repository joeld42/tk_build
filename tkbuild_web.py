# flask_web/app.py
import os, sys
import datetime, pytz
from functools import wraps

from flask import Flask, render_template, redirect, url_for, request, abort

app = Flask("tk_build",
            template_folder="./webapp/templates",
            static_folder="./webapp/static/")

from flask.logging import default_handler
app.logger.removeHandler(default_handler)

from google.auth.transport import requests
from google.cloud import datastore
import google.oauth2.id_token
from firebase_admin import auth

from tkbuild.agent import TKBuildAgent
from tkbuild.cloud import connectCloudStuff
from tkbuild.job import TKBuildJob, TKWorkstepDef, ActiveStatus
from tkbuild.user import TKBuildUser, UserRole, validateRole
from tkbuild.project import TKBuildProject
from tkbuild.artifact import TKArtifact
from tkbuild.friendlyname import friendlyName
from tkbuild.agentinfo import TKAgentInfo, AgentStatus, DEFAULT_AGENT_TIMESTAMP

import logging

agent = None
PST = pytz.timezone('US/Pacific')

firebase_request_adapter = requests.Request()

@app.template_filter('timestamp')
def format_datetime(date, fmt="%a, %m/%d/%Y %I:%M%p"):
    return date.astimezone(PST).strftime(fmt)

# Formats a timestamp as a readable age, such as "5 minutes ago"
# or " `Date`". Times before the existance of tk_build are
# considered "Never"
@app.template_filter('agestamp')
def format_agestamp( date ):
    if date <= DEFAULT_AGENT_TIMESTAMP:
        return "Never"
    else:
        tdelta = datetime.datetime.now().astimezone(pytz.UTC) - date
        if tdelta.seconds >= 3600:
            # if more than an hour has passed, show it as a regular timestamp
            return date.astimezone(PST).strftime("%a, %m/%d/%Y %I:%M%p")
        else:
            if tdelta.seconds > 60:
                return f"{ round(tdelta.seconds / 60) } minutes ago"
            elif tdelta.seconds >= 10:
                return f"{ round(tdelta.seconds) } seconds ago"
            else:
                return "just now"




@app.template_filter('friendly')
def format_friendly( idstr ):
    return friendlyName( idstr )

# Helper decorator for pages we want behind a login wall
def require_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check auth
        id_token = request.cookies.get("token")
        error_message = None
        login_data = None

        if id_token:
            try:
                # Verify the token against the firebase auth api
                login_data = google.oauth2.id_token.verify_firebase_token(id_token, firebase_request_adapter)
            except ValueError as exc:
                error_message = str(exc)

        # If we have validated login data, call the underlying function
        if login_data:
            return f(login_data, *args, **kwargs)
        else:
            # Redirect to the login page
            return redirect(url_for('login', next=request.url))

    return decorated_function

def require_role( role = UserRole.TESTER ):
    def require_role_decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check auth
            id_token = request.cookies.get("token")
            error_message = None
            login_data = None

            if id_token:
                try:
                    # Verify the token against the firebase auth api
                    login_data = google.oauth2.id_token.verify_firebase_token(id_token, firebase_request_adapter)
                except ValueError as exc:
                    error_message = str(exc)

            #print("require_role, login data is ", login_data, "id token is ", id_token )

            # If we have validated login data, call the underlying function
            if login_data:
                # if this requires a specific role, validate that role first
                if validateRole( login_data, role ):
                    return f(login_data, *args, **kwargs)
                else:
                    # Redirect to the main page
                    return redirect(url_for('index'))
            else:
                # Redirect to the login page
                return redirect( url_for('login', next=request.url ))

        return decorated_function
    return require_role_decorator



@app.route('/')
@require_login
def index( login_data  ):

    projs = agent.orderedProjects()

    # Get all the project info and fetch latest job info
    lastjob = {}
    for proj in projs:
        buildNum, jobKey = proj.getBuildNumberAndJob( agent.db )

        if jobKey:
            jobRef = agent.db.collection(u'jobs').document(jobKey).get()
            if jobRef.exists:
                job = TKBuildJob.createFromFirebaseDict(proj, jobKey, jobRef)
                lastjob[ proj.projectId ] = job


    return render_template('index.html', projects=projs, active='projects', lastjob = lastjob,
                           user_data = login_data )

@app.route('/login')
def login():

    # Check auth -- this is the same thing that @require_login does but doesn't fail
    # if not logged in.
    id_token = request.cookies.get("token")
    error_message = None
    login_data = None

    if id_token:
        try:
            # Verify the token against the firebase auth api
            login_data = google.oauth2.id_token.verify_firebase_token( id_token, firebase_request_adapter )
        except ValueError as exc:
            error_message = str(exc)

    return render_template('login.html', user_data=login_data, error_message=error_message)


@app.route('/users')
@require_role( role=UserRole.ADMIN )
def users( login_data ):

    users = []
    for authUser in auth.list_users().iterate_all():
        user = TKBuildUser( authUser )
        users.append( user )

    users.sort( key=lambda u: u.authUser.display_name )

    return render_template('users.html',
                           user_data=login_data,
                           active='users',
                           users = users );

@app.route('/user/<userId>/edit', methods=[ 'POST', 'GET'])
@require_role( role=UserRole.ADMIN )
def edit_user( login_data, userId ):
    error_message = None
    success_message = None
    user = None
    authUser = auth.get_user(userId)
    if authUser:
        user = TKBuildUser( authUser )


    if request.method == 'POST':
        userRole = request.form.get('radioUserRole')

        if not userRole in [ UserRole.GUEST, UserRole.TESTER, UserRole.ADMIN ]:
            error_message = "Unknown user role : " + str(userRole)
            print( "WARN: " + error_message )
        else:
            auth.set_custom_user_claims( user.authUser.uid, { 'role' : userRole } )
            success_message = f"Set role to '{userRole}' for {user.authUser.display_name}"

    return render_template('edit_user.html',
                           active='users',
                           user = user,
                           error_message = error_message,
                           success_message=success_message,
                           user_data=login_data );

@app.route('/agents')
@require_login
def agents_overview( login_data ):

    agents = []

    agentsData = agent.db.collection(u'agents').get()
    print("Agents data", agentsData )
    for agentData in agentsData:
        agentInfo = TKAgentInfo.createFromFirebaseDict( agentData.id, agentData )

        agents.append(  agentInfo )

    return render_template( 'agents.html',
                            user_data=login_data,
                            active='agents',
                            agents=agents )

@app.route('/jobs')
@require_login
def jobs_overview( login_data ):

    jobs_active = []
    jobs_inactive = []
    jobsData = agent.db.collection(u'jobs').get()
    for jobData in jobsData:
        project = agent.projects[ jobData.get('projectId') ]
        job = TKBuildJob.createFromFirebaseDict( project, jobData.id, jobData )

        if job.activeStatus()==ActiveStatus.ACTIVE:
            jobs_active.append( job )
        else:
            jobs_inactive.append( job )

    wsstyles = { 'done': 'bg-success',
                'todo' : 'bg-secondary',
                'fail' : 'bg-warning text-dark',
                'skip' : 'bg-light text-dark',
                'cancel' : 'bg-warning text-dark',
                'run' : 'bg-info text-dark' }

    allwsnames = []
    for p in agent.projects.values():
        for wsdef in p.workstepDefs:
            if not wsdef.stepname in allwsnames:
                allwsnames.append( wsdef.stepname )

    jobs_active.sort( key=lambda a: a.timestamp, reverse=True )
    jobs_inactive.sort(key=lambda a: a.timestamp, reverse=True)

    return render_template('jobs.html',
                           user_data=login_data,

                           jobs_active=jobs_active,

                           jobs_inactive=jobs_inactive,
                           projects=agent.projects.keys(),
                           wsstyles=wsstyles, agent=agent, allwsnames = allwsnames,
                           active='jobs')

@app.route('/job_details/<jobkey>' )
@require_login
def job_details( login_data, jobkey ):

    jobRef = agent.db.collection(u'jobs').document( jobkey ).get()

    jobDict = jobRef.to_dict()
    proj = agent.projects.get( jobDict['projectId'] )
    logs = {} # Logs for the worksteps we know about
    extra_logs = {} # These are logs that don't match a workstep that we expect

    # See if there's an artifact for this job
    artifact = None
    artsRef = agent.db.collection(u'artifacts')
    for artifactData in artsRef.where( u'jobKey', u'==', jobkey ).get():
        
        artifact = TKArtifact.createFromFirebaseDict( artifactData.id, artifactData.to_dict() )

    wsnames = []
    for wsdef in proj.workstepDefs:
        wsnames.append(wsdef.stepname)
    if proj.bucketName:
        storage_client = google.cloud.storage.Client()
        logPath = os.path.join(proj.projectId, jobkey, "logs/" )
        blobs = storage_client.list_blobs( proj.bucketName, prefix=logPath, delimiter='/')
        blobs = list(blobs)
        #print("Bucket", proj.bucketName, "log path", logPath )
        #print("Blobs:", blobs)

        for blob in blobs:
            logname = blob.name
            #logUrl = f"https://storage.googleapis.com/{proj.bucketName}/{blob.name}"
            logUrl = f"https://{proj.bucketName}.storage.googleapis.com/{blob.name}"

            # Simplify the logfile name if it matches our expected convention
            # of project_jobkey_workstep, we can strip the project and jobkey
            jobKeyPos = logname.rfind( jobkey )
            if jobKeyPos >= 0:
                logname = logname[ jobKeyPos + len(jobkey) + 1 :]

            if logname in wsnames:
                logs[logname] = logUrl
            else:
                # this is either an extra file in the log dir or a workstep log that
                # isn't defined in the project
                extra_logs[logname] = logUrl
            #print("Log:", logname )

    job = TKBuildJob.createFromFirebaseDict( proj, jobRef.id, jobRef )
    return render_template( 'job_details.html', user_data = login_data, proj=proj, job=job, artifact=artifact, logfiles = logs, extralogs = extra_logs  )

@app.route('/del_job/<jobkey>' )
@require_login
def del_job( login_data, jobkey ):

    agent.db.collection(u'jobs').document( jobkey ).delete()
    return redirect(url_for('jobs_overview'))

@app.route('/builds')
@require_login
def builds_overview( login_data ):

    # Fetch the build artifacts
    artifacts = {}
    artifactsData = agent.db.collection(u'artifacts').get()
    for artifactData in artifactsData:

        #print( "ArtifactData is ", artifactData.to_dict() )

        artifact = TKArtifact.createFromFirebaseDict( artifactData.id, artifactData.to_dict() )
        if not artifact.project in artifacts:
            artifacts[ artifact.project ] = []

        artifacts[artifact.project].append( artifact )

    # print("All Artifacts", artifacts)
    for pk in artifacts.keys():
        artifacts[ pk ].sort( key=lambda a: a.timestamp, reverse=True )

    return render_template('builds.html', user_data = login_data, projects=agent.orderedProjects(), artifacts=artifacts, active='builds' )

@app.route('/project/<project_id>' )
@require_login
def project_overview( project_id ):
    proj = agent.projects.get(project_id)
    if proj == None:
        abort(404, description=f"Project '{project_id}' does not exist.")

    return

@app.route('/project/<project_id>/refresh_repo' )
@require_login
def project_refresh_repo( login_data, project_id ):

    proj = agent.projects.get( project_id )
    if proj == None:
        abort(404, description=f"Project '{project_id}' does not exist.")

    wsdef = proj.getFetchWorkstep()
    agent.updatePristineRepo( proj, wsdef, None )

    return redirect(url_for('project_add_job',  user_data = login_data, project_id=project_id) )


@app.route('/project/<project_id>/add_job', methods=[ 'POST', 'GET'])
@require_login
def project_add_job( login_data, project_id ):

    proj = agent.projects.get( project_id )
    if proj == None:
        abort(404, description=f"Project '{project_id}' does not exist.")

    # TODO: Get the from, the config somehow
    # Internally, platform tags are just regular tags but we make the UI expect
    # exactly one platform tag and the misc tags con from the config
    PLATFORM_TAGS = ['win', 'mac', 'ios']
    MISC_TAGS = ['testing', 'blarg', 'foo']

    if request.method == 'POST':
        commit = request.form.get('commit')
        if commit:
            # Submitting, add the project
            addJob = TKBuildJob(proj)
            addJob.commitVer = commit.split()[0]

            # Set Tags
            ptag = request.form.get("platform-tag")
            jobTags = [ ptag ]

            # Set tags
            for tagname in MISC_TAGS:
                if request.form.get("tag-"+tagname):
                    jobTags.append( tagname )

            addJob.tags = jobTags

            # Set worksteps
            addJob.worksteps = {}
            for wsname in addJob.wsnames:
                addJob.worksteps[wsname] = request.form.get("wscheck-" + wsname, "skip");

            testJobRef = agent.db.collection(u'jobs').document()
            testJobRef.set(addJob.toFirebaseDict())

            # And go back to the jobs overview page
            return redirect(url_for('jobs_overview'))

        else:
            return ("TODO: you need to pick a commit version")

    # Populate the add_job form
    commitList = agent.getRecentCommits( proj )
    print( "COMMIT LIST IS ", commitList )

    wsnames = []
    for wsdef in proj.workstepDefs:
        wsnames.append( wsdef.stepname )

    return render_template( "project_add_job.html",
                            user_data=login_data,
                            active='jobs',
                            platform_selected = "win",
                            platform_tags = PLATFORM_TAGS,
                            tags = MISC_TAGS,
                            project=proj, commits=commitList, wsnames=wsnames )


@app.route('/add_test_job', methods=[ 'POST'])
@require_login
def add_test_job():

    print("ADD JOB: will add ", request.form.to_dict() )

    commit = request.form.get('commit')
    if commit:
        projId = request.form.get('project', "missing" )
        proj = agent.projects[ projId ]
        if not proj:
            return ( f"ERROR: no project named '{projId}'." )

        addJob = TKBuildJob( proj )
        addJob.commitVer = commit.split()[0]

        # Set worksteps
        addJob.worksteps = {}
        for wsname in addJob.wsnames:
            addJob.worksteps[ wsname ] = request.form.get( "wscheck-" + wsname, "skip" );

        print(f"AddTestJob: {addJob}")
        testJobRef = agent.db.collection(u'jobs').document()
        testJobRef.set(addJob.toFirebaseDict())

    return redirect(url_for('jobs_overview'))

def page_not_found(e):
  return render_template('error404.html', description=e.description ), 404



def makeReadyWebApp( cfgFile, do_cloud_logging ):

    global agent
    agent = TKBuildAgent.createFromConfigFile(cfgFile)

    db = connectCloudStuff(agent, do_cloud_logging)
    if not db:
        logging.error("Connecting to cloud stuff failed.")
        sys.exit(1)

    agent.db = db

    app.register_error_handler(404, page_not_found)
    logging.info("Tkbuild web ready.")


if __name__ == '__main__':

    # TODO get this from environment or args
    #agentCfgFile = "/opt/tkbuild/tkbuild_agent.yml"
    agentCfgFile = "c:/Toolkits/tk_build/cfg/tapnik/tkbuild_agent_win_test.yml"
    makeReadyWebApp( agentCfgFile, False )
    app.run(debug=True, host='0.0.0.0')
