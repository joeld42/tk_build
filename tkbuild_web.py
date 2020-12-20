# flask_web/app.py
import os, sys

from flask import Flask, render_template, redirect, url_for, request, abort

app = Flask("tk_build",
            template_folder="./webapp/templates",
            static_folder="./webapp/static/")

from flask.logging import default_handler
app.logger.removeHandler(default_handler)

from tkbuild.agent import TKBuildAgent
from tkbuild.cloud import connectCloudStuff
from tkbuild.job import TKBuildJob, TKWorkstepDef
from tkbuild.project import TKBuildProject
from tkbuild.artifact import TKArtifact

import logging

agent = None

@app.route('/')
def index():

    projs = agent.projects.values()

    return render_template('index.html', projects=projs, active='projects' )

@app.route('/jobs')
def jobs_overview():

    jobs = []
    jobsData = agent.db.collection(u'jobs').get()
    for jobData in jobsData:
        project = agent.projects[ jobData.get('projectId') ]
        job = TKBuildJob.createFromFirebaseDict( project, jobData.id, jobData )
        jobs.append( job )

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

    return render_template('jobs.html', jobs=jobs, projects=agent.projects.keys(),
                           wsstyles=wsstyles, agent=agent, allwsnames = allwsnames,
                           active='jobs')

@app.route('/del_job/<jobkey>' )
def del_job( jobkey ):

    agent.db.collection(u'jobs').document( jobkey ).delete()
    return redirect(url_for('jobs_overview'))

@app.route('/builds')
def builds_overview():

    # Fetch the build artifacts
    artifacts = {}
    artifactsData = agent.db.collection(u'artifacts').get()
    for artifactData in artifactsData:

        print( "ArtifactData is ", artifactData.to_dict() )

        artifact = TKArtifact.createFromFirebaseDict( artifactData.id, artifactData )
        if not artifact.project in artifacts:
            artifacts[ artifact.project ] = []

        artifacts[artifact.project].append( artifact )

    print("All Artifacts", artifacts)

    return render_template('builds.html', projects=agent.projects.values(), artifacts=artifacts, active='builds' )

@app.route('/project/<project_id>' )
def project_overview( project_id ):
    proj = agent.projects.get(project_id)
    if proj == None:
        abort(404, description=f"Project '{project_id}' does not exist.")

    return

@app.route('/project/<project_id>/refresh_repo' )
def project_refresh_repo( project_id ):

    proj = agent.projects.get( project_id )
    if proj == None:
        abort(404, description=f"Project '{project_id}' does not exist.")

    wsdef = proj.getFetchWorkstep()
    agent.updatePristineRepo( proj, wsdef, None )

    return redirect(url_for('project_add_job', project_id=project_id) )


@app.route('/project/<project_id>/add_job', methods=[ 'POST', 'GET'])
def project_add_job( project_id ):

    proj = agent.projects.get( project_id )
    if proj == None:
        abort(404, description=f"Project '{project_id}' does not exist.")

    if request.method == 'POST':
        commit = request.form.get('commit')
        if commit:
            # Submitting, add the project
            addJob = TKBuildJob(proj)
            addJob.commitVer = commit.split()[0]

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

    return render_template( "project_add_job.html", project=proj, commits=commitList, wsnames=wsnames )

@app.route('/add_test_job', methods=[ 'POST'])
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
    agentCfgFile = "/opt/tkbuild/tkbuild_agent.yml"
    makeReadyWebApp( agentCfgFile, False )
    app.run(debug=True, host='0.0.0.0')
