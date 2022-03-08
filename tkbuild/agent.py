#!/usr/bin/env python3
import os, sys, time, re, string
import datetime, pytz
import subprocess
import shutil
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
from tkbuild.agentinfo import TKAgentInfo, AgentStatus

# TKBUILD TODO
#  - Figure out "voting" or transaction based write for firebase to ensure only one agent runs a job
#  - Figure out reliable way to stop/resume build agent on mac

class TKBuildAgentConfig(object):

    def __init__(self, agentConfigFile):
        self.googleCredentialFile = "MISSING"
        self.googleProjectId = "my-projectid-00000"
        self.projectConfigs = []
        logging.info("In TKBuildAgentConfig", agentConfigFile )

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

        # This is our current server status
        self.agentInfo = None



    @classmethod
    def createFromConfig( cls, configData, tkBuildDir ):

        agentCfg = configData.get("build-agent")

        agent = cls()
        agent.name = agentCfg.get( 'name', agent.name )
        agent.desc = agentCfg.get( 'desc', agent.desc )
        agent.agentTags = agentCfg.get( 'tags', [] )

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

    def orderedProjects(self):

        projects = list( self.projects.values() )
        projects.sort( key=lambda pp: pp.sortKey )
        return projects


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


            self.changeEvent.wait( 2.0  ) # TODO: make timeout time an option


            self.changeEvent.clear()

    def updateCurrentStatus(self, status ):

        # TODO don't update if status is unchanged below a timeout

        # If we don't have a ref to our agent info, fetch or create one
        if self.agentInfo is None:
            agents_ref = self.db.collection(u'agents')
            agents = agents_ref.where(u'name', u'==', self.name ).get()

            print("Agents are", agents)
            if (len(agents) > 0):
                agentRef = agents[0].reference
                print(f"Found agent {self.name}")
            else:
                # Create a new agentInfo
                print(f"Did not find agent with name {self.name}, creating new")
                agentRef = self.db.collection(u'agents').document()

            self.agentInfo = TKAgentInfo( self.name, self.desc, agentRef.id )
            self.agentInfo.tags = self.agentTags
        else:
            agentRef = self.db.collection(u'agents').document( self.agentInfo.id )


        agentData = self.agentInfo.toFirebaseDict()
        agentRef.set( agentData )



    def serverUpdate(self):

        logging.info( f"Agent update ... {self.updCount}")
        self.updCount += 1

        print( f" {len(self.jobList)} avail jobs:")

        # Report our status to the server
        self.updateCurrentStatus( AgentStatus.IDLE )

        # Check if there are any obsolete jobs, and delete them
        self.cleanupObsoleteJobs()

        # Check if there are any jobdirs that do not exist in the job list. If so, clean up those job dirs.
        self.cleanupOldJobDirs()

        # Check if there are jobs we can do
        for job in self.jobList:

            proj = self.projects[job.projectId]

            # Ignore jobs with tags we can't match
            if not self.matchTags( job.tags, self.agentInfo.tags ):
                print("Skipping job with tags ", job.tags, "our tags are ", self.agentInfo.tags )
                continue

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

    def cleanupOldProjectJobs(self, proj, projJobExpireDate ):

        print("cleanupOldProjectJobs", proj.projectId, len(self.jobList) )
        for job in self.jobList:
            if (job.projectId==proj.projectId) and (job.timestamp < projJobExpireDate):
                self.db.collection(u'jobs').document(job.jobKey).delete()

    def cleanupObsoleteJobs(self):

        if len(self.jobList)==0:
            return

        for proj in self.projects.values():

            projJobExpireDate = datetime.datetime.now( tz=pytz.UTC ) - datetime.timedelta( minutes=proj.jobDeleteAge )
            print(f"Project {proj.projectId} will expire jobs before {projJobExpireDate}")

            self.cleanupOldProjectJobs( proj, projJobExpireDate )

    def cleanupOldJobDirs(self ):


        # Make a list of the jobkeys we have for easy lookup
        haveJobKeys = set()
        for job in self.jobList:
            haveJobKeys.add( job.jobKey )

        # Look in the project workdir for any jobdirs that
        # match the pattern for a jobdir
        for proj in self.projects.values():

            if (not os.path.exists( proj.workDir)):
                print(f"Workdir for {proj.projectId} does not exist, skipping.")
                continue

            for dir in os.listdir( proj.workDir ):
                dsplit = dir.split( "_" )
                if len (dsplit) != 2:
                    continue
                dirProj, jobKey = dsplit


                if dirProj != proj.projectId:
                    continue

                if len(jobKey) != 20:
                    continue

                # At this point we are pretty sure this is a work dir, and
                # can infer the jobkey from the workdir
                if jobKey in haveJobKeys:
                    print ("Nope this is an active job")
                    continue

                # Also look for other dirs listed in cleanupDirs
                workDir = os.path.join( proj.workDir, dir )
                cleanupDirs = [  workDir ]
                workname = proj.projectId + "_" + jobKey
                for extraDir in proj.cleanupDirs:
                    dir2 = self.replacePathVars2( extraDir, workDir, proj, None, workname )

                    # Make sure there are no unexpanded vars, kind of a hack but
                    if dir2.find("$")==-1:
                        cleanupDirs.append( dir2 )

                for cleanDir in cleanupDirs:
                    if os.path.exists( cleanDir ):
                        logging.info( f"Cleaning up old workdir {cleanDir}" )
                        shutil.rmtree( cleanDir )

    def matchTags(self, jobTags, agentTags):

        # Make sure all of the tags requested in the jobTags are in our agent Tags
        for tag in jobTags:
            if not tag in agentTags:
                return False

        return True

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

    def archiveLog(self, job, wsdef, workstepLog ):
        proj = self.projects[job.projectId]

        # Check that we're configured to publish stuff
        if not proj.bucketName:
            logging.warning("archiveLog: No bucketName set in project, can't archive log.")
            return False

        # Make sure the file exists
        if not os.path.exists(workstepLog):
            logging.warning( f"archiveLog: Workstep log file {workstepLog} does not exist." )
            return False
        else:
            logging.info(f"Archiving {workstepLog} to bucket {proj.bucketName}")
            if self.storage_client is None:
                self.storage_client = google.cloud.storage.Client()

            logFilename = os.path.split(workstepLog)[-1]
            bucket = self.storage_client.bucket(proj.bucketName)
            blobName = os.path.join(proj.projectId, job.jobKey, "logs", logFilename)
            blob = bucket.blob(blobName)
            result = blob.upload_from_filename(workstepLog, content_type="text/plain;charset=UTF-8")

            logArchiveUrl = f"https://{bucket.name}.storage.googleapis.com/{blob.name}"
            logging.info(f"Result of upload is {logArchiveUrl}")


    def replacePathVars(self, origPath, workdirRepoPath, proj, job ):
        return self.replacePathVars2( origPath, workdirRepoPath, proj, job, job.jobDirShort )

    def replacePathVars2(self, origPath, workdirRepoPath, proj, job, workname ):

        vars = {
            "TKBUILD" : self.tkbuildDir,
            "WORKDIR" : workdirRepoPath,
            "PROJWORKDIR" : proj.workDir,
            "WORKNAME": workname,
        }

        if job:
            vars.update( {
                "COMMIT": job.commitVer,
                "VERSION": job.version,
                "BUILDNUM": str(job.buildNum)
            })

        result = origPath
        for varname, value in vars.items():
            varstr = "$" + varname
            if result.find( varstr ) != -1:
                result = result.replace( varstr, value )

        # result = origPath.replace("$TKBUILD", self.tkbuildDir)
        # result = result.replace("$WORKDIR", workdirRepoPath)

        return result

    def publishArtifact( self, proj, job, wsdef, workdirRepoPath ):

        # Check that we're configured to publish stuff
        if not proj.bucketName:
            logging.warning("publishArtifact: No bucketName set in project, can't publish.")
            return False

        # Make sure the file exists
        artifactFile = wsdef.artifact
        artifactFile = self.replacePathVars( artifactFile, workdirRepoPath, proj, job )
        if not os.path.exists( artifactFile ):
            failMsg = f"Artifact file {artifactFile} does not exist."
            logging.warning( failMsg )
            job.lastError = failMsg
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
            artifact = TKArtifact()
            artifact.project = proj.projectId
            artifact.commitVer = job.commitVer
            artifact.jobKey = job.jobKey
            artifact.builtfile = artifactUrl

            # If the artifact has a manifestBundleId, make a manifest for it
            if proj.manifestBundleId:
                artifact.addManifestInfo( proj.manifestAppTitle, proj.manifestBundleId, job.version, job.buildNum, artifactUrl )

                # maybe want to make this more configurable
                manifestName = f"{proj.projectId}_manifest_{job.version}_build_{job.buildNum}.plist"
                manifestBlobName = os.path.join( proj.projectId, job.jobKey, manifestName)
                manifestBlob = bucket.blob( manifestBlobName )
                result = manifestBlob.upload_from_string( artifact.generateManifestFile())

                manifestUrl = f"https://storage.googleapis.com/{bucket.name}/{manifestBlob.name}"
                artifact.manifest['manifestURL'] = manifestUrl
                logging.info( f"Uploaded IOS manifest to {manifestUrl}" )


            pubArtifactRef = self.db.collection(u'artifacts').document()
            pubArtifactRef.set( artifact.toFirebaseDict() )
            logging.info( f"Added artifact with ref {pubArtifactRef.id}")

            return True

    def peekVersion( self, job, versionFile ):

        if not os.path.exists( versionFile ):
            logging.warning( f"Version file {versionFile} does not exist.")
            return

        with open( versionFile ) as fp:
            verLine = fp.readline().strip()

            if verLine:
                job.version = verLine
                logging.info( f"PeekVersion: Version is {job.version}" )


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

                    # Extra magic for 'fetch' and 'build' for now
                    if wsdef.stepname == 'fetch':
                        if not self.workstepFetch( job, wsdef, fpLog ):
                            logging.warning("fetch workstep FAILED.")
                            # The fetch failed for some reason, fail the workstep
                            self.failJob( job, wsdef )
                            break
                        else:
                            logging.info("fetch succeeded, marking as DONE")
                            job.setWorkstepStatus(wsdef.stepname, JobStatus.DONE)
                            self.commitJobChanges(job)

                    elif wsdef.stepname == 'build':
                        job.buildNum = proj.incrementBuildNumber( job.jobKey, self.db )

                    # Common workstep steps
                    logging.info( f"Will do job step {wsdef.stepname}" )
                    workdirRepoPath = os.path.join(proj.workDir, job.jobDirShort)
                    if wsdef.cmd:

                        # Fixme: allow array args or something to handle spaces in args
                        stepCmd = []
                        for stepCmdSplit in wsdef.cmd.split():

                            #print ("SPLIT", stepCmdSplit)

                            # Replace the project dirs
                            stepCmdSplit = self.replacePathVars( stepCmdSplit, workdirRepoPath, proj, job )

                            stepCmd.append( stepCmdSplit )

                        print("step command is ", stepCmd )
                        result, cmdTime = self.echoRunCommand( stepCmd, fpLog, self, job )

                    elif wsdef.stepname != 'fetch':
                        # Fetch might not have a cmd, but other steps probably will
                        logging.warning(f"Workstep {job.projectId}:{wsdef.stepname} has no cmd defined.")
                        result = 0 # treat as done
                        cmdTime = datetime.timedelta(0)

                    if result == 0:
                        # Did succeed?
                        logging.info(f"Workstep {job.projectId}:{wsdef.stepname} completed success.")

                        # If this workstep generates a version number, retrieve it now
                        if wsdef.peekVersion:
                            versionFile = self.replacePathVars( wsdef.peekVersion, workdirRepoPath, proj, job )
                            self.peekVersion( job, versionFile )

                        # And set the status to done
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

                # Workstep finished, archive the log file
                self.archiveLog(job, wsdef, workstepLog)

                # we did one workstep here, so don't keep looking for available ones. We'll
                # get the next one the next time through the loop
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

        # PIPE nonsense does capture_output in py3.6
        #result = subprocess.run( gitCmd, capture_output=True )
        result = subprocess.run( gitCmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT )
        if result.returncode:
            return [ "ERROR in git log" ]
        else:
            commitList = []
            for line in result.stdout.decode("utf-8").split("\n"):
                if line:
                    commitList.append( line )
            return commitList


    def updatePristineRepo( self, proj, wsdef, fpLog ):

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
            return None

        return pristineRepoPath


    # I don't like this workstep being hardcoded in the agent but not sure exactly
    # how I want it to look so I'm putting it here for now.
    def workstepFetch(self, job, wsdef, fpLog ):

        proj = self.projects[job.projectId]

        pristineRepoPath = self.updatePristineRepo( proj, wsdef, fpLog )
        if not pristineRepoPath:
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
        if fpLog:

            fpLog.write( "CMD: " + cmdStr + "\n")
            fpLog.flush()

        logging.info(cmdStr)

        if (self.dryRun):
            return (0, datetime.timedelta(0))

        startTime = datetime.datetime.now()

        # FIXME: handle STDERR separately, but python makes this hard
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT )  # , shell=True)

        while True:
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
                    if fpLog:
                        fpLog.write( "ERROR: "+ line + "\n")
                        fpLog.flush()

                    if job:
                        job.countError( line )

                elif isWarn:
                    logging.warning(line)
                    if fpLog:
                        fpLog.write("WARN: " + line + "\n")
                        fpLog.flush()
                    if job:
                        job.countWarning()

                else:
                    logging.info( line )
                    if fpLog:
                        fpLog.write( line + "\n")
                        fpLog.flush()

                if (isError or isWarn) and (agent and job):
                    agent.commitJobChanges( job )

            # Is the subprocess done?
            if process.poll() is not None:
                break

        endTime = datetime.datetime.now()
        cmdDuration = endTime - startTime

        cmdStatus = f"Finished with retval {process.returncode} time taken {cmdDuration}";
        logging.info( cmdStatus )

        if fpLog:
            fpLog.write( cmdStatus + "\n\n\n" )
            fpLog.flush()

        return (process.returncode, cmdDuration)
