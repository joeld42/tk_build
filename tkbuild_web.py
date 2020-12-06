# flask_web/app.py
import os, sys

from flask import Flask, render_template, redirect, url_for, request
app = Flask(__name__,
            template_folder="./webapp/templates",
            static_folder="./webapp/static")

from tkbuild.agent import TKBuildAgent
from tkbuild.cloud import connectCloudStuff
from tkbuild.job import TKBuildJob, TKWorkstepDef
from tkbuild.project import TKBuildProject

import logging

agent = None

@app.route('/')
def hello_world():
    return render_template('base.html')

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

    return render_template('jobs.html', jobs=jobs, wsstyles=wsstyles, agent=agent, allwsnames = allwsnames )

@app.route('/del_job/<jobkey>' )
def del_job( jobkey ):

    agent.db.collection(u'jobs').document( jobkey ).delete()
    return redirect(url_for('jobs_overview'))

@app.route('/add_job', methods=[ 'POST'])
def add_job():

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

        print(f"AddJob: {addJob}")
        testJobRef = agent.db.collection(u'jobs').document()
        testJobRef.set(addJob.toFirebaseDict())

    return redirect(url_for('jobs_overview'))

if __name__ == '__main__':

    # TODO get this from environment or args
    agentCfgFile = "/opt/tkbuild/tkbuild_agent.yml"
    agent = TKBuildAgent.createFromConfigFile(agentCfgFile)

    db = connectCloudStuff(agent)
    if not db:
        logging.error("Connecting to cloud stuff failed.")
        sys.exit(1)

    agent.db = db
    logging.info("Tkbuild web ready.")

    app.run(debug=True, host='0.0.0.0')
