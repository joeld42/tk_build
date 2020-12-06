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
        job = TKBuildJob.createFromFirebaseDict( jobData.id, jobData )
        jobs.append( job )

    proj = agent.projects[ job.projectId ]
    wsnames = []
    for wsdef in proj.workstepDefs:
        wsnames.append( wsdef.stepname )

    wsstyles = { 'done': 'bg-success',
                'todo' : 'bg-secondary',
                'fail' : 'bg-warning text-dark',
                'skip' : 'bg-light text-dark',
                'cancel' : 'bg-warning text-dark',
                'run' : 'bg-info text-dark' }

    return render_template('jobs.html', jobs=jobs, wsnames=wsnames, wsstyles=wsstyles, agent=agent )

@app.route('/add_job', methods=[ 'POST'])
def add_job():

    print("ADD JOB: will add ", request.form.to_dict() )

    commit = request.form.get('commit')
    if commit:
        testJob = TKBuildJob( request.form['project'])
        testJob.commitVer = commit.split()[0]

        # TODO: Get these from project
        testJob.worksteps = {"fetch": request.form.get( "wscheck-fetch", "skip" ),
                             "build": request.form.get( "wscheck-fetch", "skip" ),
                             }

        print(f"Testjob: {testJob}")
        testJobRef = agent.db.collection(u'jobs').document()
        testJobRef.set(testJob.toFirebaseDict())

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
