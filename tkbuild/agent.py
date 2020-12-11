#!/usr/bin/env python3
import os, sys, time, re
import datetime
import subprocess
from enum import Enum

import platform
import threading

import yaml

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore


import google.cloud.storage
import google.cloud.logging
import logging

from tkbuild.job import TKBuildJob, TKWorkstepDef, JobStatus
from tkbuild.project import TKBuildProject
from tkbuild.artifact import TKArtifact

class TKBuildAgentConfig(object):

    def __init__(self, agentConfigFile):
        self.googleCredentialFile = "MISSING"
        self.googleProjectId = "my-projectid-00000"
        self.projectConfigs = []

        print("Initializing build agent from config ", agentConfigFile)
        if not os.path.exists(agentConfigFile):
            print("WARN: agent config file doesn't exist or can't be read:", agentConfigFile)
        else:
            with open(agentConfigFile) as fpconfig:
                docs = yaml.full_load(fpconfig)

                agentCfg = docs.get("build-agent")
                print( agentCfg['name'] )
                print( agentCfg['desc'] )

                for projectCfgDoc in docs['projects']:
                    projectCfgData = projectCfgDoc['project']

                    project = TKBuildProject.createFromConfig( projectCfgData )


# An agent is a script that runs builds on a worker machine. One agent
# may have multiple projects
class TKBuildAgent(object):

    def __init__(self ):
        self.name = "unnamed-build-agent"
        self.desc = "TkBuild Build Agent"
        self.tkbuildDir = "/tmp/tkbuild/"
        self.googleCredentialFile = "MISSING"
        self.googleProjectId = "my-projectid-00000"
        self.dryRun = False
        self.projects = {}
        self.platform = platform.system() # e.g. "Darwin"
        self.serverDone = False
        self.updCount = 0 # mostly for debugging
        self.storage_client = None

        self.db = None
        self.jobList = [] # Will be populated from the jobs callback

        # Set when something has changed and the worker should
        # run an update
        self.changeEvent = threading.Event()

        # This is the currently running job.
        self.currentJob = None

    @classmethod
    def createFromConfig( cls, configData, tkBuildDir ):

        agentCfg = configData.get("build-agent")

        agent = cls()
        agent.name = agentCfg.get( 'name', agent.name )
        agent.desc = agentCfg.get( 'desc', agent.desc )

        agent.tkbuildDir = tkBuildDir

        gcloudConfig = agentCfg.get('gcloud', {} )
        agent.googleCredentialFile = gcloudConfig.get( 'credfile', agent.googleCredentialFile )
        agent.googleProjectId = gcloudConfig.get( 'project-id', agent.googleProjectId  )

        for projectCfgDoc in configData.get('projects'):
            projectCfgData = projectCfgDoc['project']
            project = TKBuildProject.createFromConfig( projectCfgData )

            if project:
                agent.projects[project.projectId] = project

        return agent

    def commitJobChanges( self, job):

        job_ref = self.jobs_ref.document( job.jobKey )

        jobData = job.toFirebaseDict()
        job_ref.set( jobData )


    def updateJobsList(self, jobs_ref ):

        newJobsList = []
        for jobRef in jobs_ref:
            proj = self.projects[ jobRef.get('projectId') ]
            job = TKBuildJob.createFromFirebaseDict( proj, jobRef.id, jobRef )
            newJobsList.append( job )

            # TODO; wrap log_struct with something that can log to console too
            #self.logger.log_struct({ 'jobkey' : job.jobKey, 'worksteps' : job.worksteps } )

        self.jobList = newJobsList
        logging.info( f"Updated jobs list (length {len(self.jobList)}).")


    def onJobsListChanged( self, jobs, changes, read_time):
        #print( "On jobslist changed: ", jobs )
        logging.info( "Job list changed:")
        self.updateJobsList( jobs )

        # alert the main build that we might need to do some work
        self.changeEvent.set()

    @classmethod
    def createFromConfigFile(cls, agentConfigFile ):

        # Use where the agent Cfg is located as the default for the build dir
        defaultTkBuildDir = os.path.split( agentConfigFile )[0]

        if not os.path.exists(agentConfigFile):
            logging.warning("WARN: agent config file doesn't exist or can't be read:", agentConfigFile)
        else:
            with open(agentConfigFile) as fpconfig:
                configData = yaml.full_load(fpconfig)
                return cls.createFromConfig( configData, defaultTkBuildDir )

    def serverMainloop(self, db ):

        self.db = db

        # Set the jobs changed callback
        self.jobs_ref = db.collection(u'jobs')
        query_watch = self.jobs_ref.on_snapshot( self.onJobsListChanged )

        #self.updateJobsList(jobs_ref.get() )
        # for doc in jobs_ref.get():
        #     print(f'{doc.id} => {doc.to_dict()}')

        # Make some test jobs
        # testJob = TKBuildJob("testrepo")
        # testJob.commitVer = "f5c86435acd0af16561eeaaa74225d4b93829115"
        # testJob.worksteps = {"fetch": JobStatus.TODO,
        #                      "build": JobStatus.TODO }

        # testJob = TKBuildJob("tkwordlist")
        # testJob.commitVer = "05350960499b752bc13dd56144d6be8632ad82ca"
        # testJob.worksteps = {"fetch": JobStatus.TODO,
        #                      "build": JobStatus.TODO}
        #
        # print(f"Testjob: {testJob}")
        # testJobRef = db.collection(u'jobs').document()
        # testJobRef.set(testJob.toFirebaseDict())

        # Run the mainloop
        while not self.serverDone:

            print("update ...")
            self.serverUpdate()

            self.changeEvent.wait( 1.0  ) # TODO: make timeout time an option
            self.changeEvent.clear()

    def serverUpdate(self):

        logging.info( f"Agent update ... {self.updCount}")
        self.updCount += 1

        logging.info( f" {len(self.jobList)} avail jobs:")

        # Check if there are any jobdirs that do not exist in the job list. If so, clean up those job dirs.
        for job in self.jobList:
            logging.info( f"JOB: {job.jobKey} steps: {job.worksteps} ")

            proj = self.projects[job.projectId]

            # Ignore jobs marked "RUN" ... this might be running on another node (todo) but
            # probably is just stale because firebase updates are not instant.
            if JobStatus.RUN in job.worksteps.values():
                logging.warning("Job is marked RUN?? but we're not running it.")
                #sys.exit(1)
                continue

            # If the job has work left to do
            if job.hasWorkRemaining( proj.workstepNames ):
                print("job ", job, "has work left...")
                self.currentJob = job
                break
            else:
                print( "No work remains", job, job.worksteps )


        # Did we find a job to run?
        if self.currentJob == None:
            logging.info("No matching jobs found to run.")
        else:
            # run the job
            self.runNextJobStep( self.currentJob )

            # clear the current job
            self.currentJob = None

        # Check if there are any jobs with todo worksteps that match the project and platform for this agent.
        #  (todo: sort/priority for these) If so:
        #     - Change workstep status to “running”
        #     - Do the workstep (call $PROJECT_DIR/workdir/$REPO_NAME/tkbuild workstep)
        #     - Change the workstep status to “Completed” or “Failed”

    def failJob(self, job, wsdefFailed ):

        logging.error( f"Job {job.jobKey}:{wsdefFailed.stepname} failed.")

        # Go through the worksteps until we find the one that failed.
        # Mark it as failed, and any subsequent ones as cancelled
        proj = self.projects[job.projectId]
        foundFailedStep = False
        for wsdef in proj.workstepDefs:
            if not foundFailedStep and wsdef.stepname == wsdefFailed.stepname:
                foundFailedStep = True
                job.setWorkstepStatus( wsdef.stepname, JobStatus.FAIL )
            elif foundFailedStep and job.worksteps[ wsdef.stepname ] == JobStatus.TODO:
                job.setWorkstepStatus(wsdef.stepname, JobStatus.CANCEL)

        self.commitJobChanges( job )

    def replacePathVars(self, origPath, workdirRepoPath ):

        result = origPath.replace("$TKBUILD", self.tkbuildDir)
        result = result.replace("$WORKDIR", workdirRepoPath)

        return result

    def publishArtifact( self, proj, job, wsdef, workdirRepoPath ):

        # Check that we're configured to publish stuff
        if not proj.bucketName:
            logging.warning("publishArtifact: No bucketName set in project, can't publish.")
            return False

        # Make sure the file exists
        artifactFile = wsdef.artifact
        artifactFile = self.replacePathVars( artifactFile, workdirRepoPath )
        if not os.path.exists( artifactFile ):
            logging.warning( f"Artifact file {artifactFile} does not exist.")
            return False
        else:
            logging.info( f"Publishing {artifactFile} to bucket {proj.bucketName}")
            if self.storage_client is None:
                self.storage_client = google.cloud.storage.Client()

            artifactFileName = os.path.split( artifactFile )[-1]
            bucket = self.storage_client.bucket( proj.bucketName )
            blobName = os.path.join( proj.projectId, job.jobKey, artifactFileName)
            blob = bucket.blob( blobName )
            result = blob.upload_from_filename( artifactFile )

            artifactUrl = f"https://storage.googleapis.com/{bucket.name}/{blob.name}"
            logging.info( f"Result of upload is {artifactUrl}")

            # Make an artifact entry in the DB
            artifact = TKArtifact( proj )
            artifact.commitVer = job.commitVer
            artifact.jobKey = job.jobKey
            artifact.builtfile = artifactUrl

            pubArtifactRef = self.db.collection(u'artifacts').document()
            pubArtifactRef.set( artifact.toFirebaseDict() )
            logging.info( f"Added artifact with ref {pubArtifactRef.id}")

            return True

    def runNextJobStep(self, job ):

        logging.info("Run next job step....")
        # Go through the worksteps defined for this project and
        # do the next one that needs to be done for this job
        proj = self.projects[ job.projectId ]
        for wsdef in proj.workstepDefs:
            if ((wsdef.stepname in job.worksteps) and
                    (job.worksteps[wsdef.stepname] == JobStatus.TODO)):

                # Mark this workstep as running
                job.setWorkstepStatus(wsdef.stepname, JobStatus.RUN)
                self.commitJobChanges( job )

                # Open a logfile for this workstep
                workstepLog = os.path.join( proj.workDir, "logs", job.jobDirShort + "_" + wsdef.stepname )
                logPath = os.path.split( workstepLog )[0]
                os.makedirs( logPath, exist_ok=True )

                with open( workstepLog, "wt") as fpLog:
                    fpLog.write( f"WORKSTEP: {wsdef.stepname}\n" )

                    # Treat 'fetch' specially for now
                    if wsdef.stepname == 'fetch':
                        if not self.workstepFetch( job, wsdef, fpLog ):
                            logging.warning("fetch workstep FAILED.")
                            # The fetch failed for some reason, fail the workstep
                            self.failJob( job, wsdef )
                        else:
                            logging.info("fetch succeeded, marking as DONE")
                            job.setWorkstepStatus(wsdef.stepname, JobStatus.DONE)
                            self.commitJobChanges(job)

                        break
                    else:
                        # Regular workstep
                        logging.info( f"Will do job step {wsdef.stepname}" )
                        workdirRepoPath = os.path.join(proj.workDir, job.jobDirShort)
                        if wsdef.cmd:

                            # Fixme: allow array args or something to handle spaces in args
                            stepCmd = []
                            for stepCmdSplit in wsdef.cmd.split():

                                # Replace the project dirs
                                stepCmdSplit = self.replacePathVars( stepCmdSplit, workdirRepoPath )

                                stepCmd.append( stepCmdSplit )

                            result, cmdTime = self.echoRunCommand( stepCmd, fpLog, self, job )
                        else:
                            logging.warning(f"Workstep {job.projectId}:{wsdef.stepname} has no cmd defined.")
                            result = 0 # treat as done
                            cmdTime = datetime.timedelta(0)

                        if result == 0:
                            # Did succeed?
                            logging.info(f"Workstep {job.projectId}:{wsdef.stepname} completed success.")
                            job.setWorkstepStatus(wsdef.stepname, JobStatus.DONE )
                            self.commitJobChanges(job)

                            # If this workstep made an artifact that should get published, do so
                            logging.info( f"wsdef artifact is {wsdef.artifact}")
                            if wsdef.artifact:
                                if not self.publishArtifact( proj, job, wsdef, workdirRepoPath ):
                                    self.failJob( job, wsdef )

                        else:
                            # Step failed, fail the whole job :_(
                            self.failJob( job, wsdef )

                        break

    def makePristineRepoPath(self, proj ):
        pristineRepoPath = os.path.join(proj.projectDir, proj.projectId + "_pristine")
        return pristineRepoPath

    def getRecentCommits(self, proj ):
        pristineRepoPath = self.makePristineRepoPath( proj)
        if not os.path.exists(pristineRepoPath):
            # Don't implicitly pull the repo here
            return []

        gitCmd = ["git",
                  "-C",  pristineRepoPath,
                  "log", "--oneline", "--no-decorate", "-n","20"
                  ]
        print( "gitCmd is ", gitCmd )
        result = subprocess.run( gitCmd, capture_output=True )
        if result.returncode:
            return [ "ERROR in git log" ]
        else:
            commitList = []
            for line in result.stdout.decode("utf-8").split("\n"):
                if line:
                    commitList.append( line )
            return commitList


    # I don't like this workstep being hardcoded in the agent but not sure exactly
    # how I want it to look so I'm putting it here for now.
    def workstepFetch(self, job, wsdef, fpLog ):

        proj = self.projects[job.projectId]

        # see if the "pristine repo" exists
        pristineRepoPath = self.makePristineRepoPath( proj )
        if not os.path.exists( pristineRepoPath ):
            logging.info(f"Cloning pristine repo {pristineRepoPath}")
            gitCmd = [ "git", "clone", wsdef.repoUrl, pristineRepoPath ]

            retVal, cmdTime = self.echoRunCommand( gitCmd, fpLog )
        else:
            logging.info(f"Pristine repo exists at {pristineRepoPath}")

        # Bring the pristine repo up to date with remote main
        gitPullCmd = [ "git", "-C", pristineRepoPath,
                       "pull" ]
        retVal, cmdTime = self.echoRunCommand(gitPullCmd, fpLog )
        if retVal:
            return False

        # Now clone the pristine repo into the work dir
        workdirRepoPath = os.path.join( proj.workDir, job.jobDirShort )
        if os.path.exists( workdirRepoPath ):
            # Might make this a fatal error later, or nuke and re-copy this dir, but for
            # now we'll allow this to make debugging easier.
            logging.warning( f"Workdir repo {workdirRepoPath} already exists, using that.")
        else:
            gitCloneCommand = [ "git", "clone", pristineRepoPath, workdirRepoPath ]
            retVal, cmdTime = self.echoRunCommand(gitCloneCommand, fpLog)
            if retVal:
                return False

        # Now bring the workdir copy of the repo up to date with what we're
        # trying to build
        gitCheckoutCommand = [ "git", "-C", workdirRepoPath,
                               "checkout", job.commitVer ]
        retVal, cmdTime = self.echoRunCommand( gitCheckoutCommand, fpLog )
        if retVal:
            return False

        return True

    def _runCommandInternal( self, process):
        while True:
            line = process.stdout.readline().rstrip()
            if not line:
                break
            yield line

    def echoRunCommand( self, command, fpLog, agent = None, job = None ):

        """returns ( returnValue, timeTaken) """
        cmdStr = " ".join(command)
        fpLog.write( "CMD: " + cmdStr + "\n")
        fpLog.flush()

        logging.info(cmdStr)

        if (self.dryRun):
            return (0, datetime.timedelta(0))

        startTime = datetime.datetime.now()

        # FIXME: handle STDERR separately, but python makes this hard
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT )  # , shell=True)

        for linebytes in self._runCommandInternal(process):

            line = linebytes.decode("utf-8")

            isError = False
            isWarn = False

            # FIXME: Better parsing here, also make it tool-aware
            if line.find( "fatal:") >= 0 or line.find( "error:" ) >= 0:
                isError = True
            elif line.find("warning:") >= 0:
                isWarn = True

            if isError:
                logging.error(line)
                fpLog.write( "ERROR: "+ line + "\n")
                fpLog.flush()

                if job:
                    job.countError()

            elif isWarn:
                logging.warning(line)
                fpLog.write("WARN: " + line + "\n")
                fpLog.flush()
                if job:
                    job.countWarning()

            else:
                logging.info( line )
                fpLog.write( line + "\n")
                fpLog.flush()

            if (isError or isWarn) and (agent and job):
                agent.commitJobChanges( job )

        process.wait()

        endTime = datetime.datetime.now()
        cmdDuration = endTime - startTime

        cmdStatus = f"Finished with retval {process.returncode} time taken {cmdDuration}";
        logging.info( cmdStatus )

        fpLog.write( cmdStatus + "\n\n\n" )
        fpLog.flush()

        return (process.returncode, cmdDuration)
