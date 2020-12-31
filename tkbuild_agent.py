#!/usr/bin/env python3
import os, sys, time, re

import logging
import argparse

from tkbuild.agent import TKBuildAgent
from tkbuild.cloud import connectCloudStuff

DEFAULT_CONFIG_FILE = "/opt/tkbuild/tkbuild_agent.yml" 

# TODOs to work on with dave:
# - Use google org authentication for bucket files
# - Generate link to jump to log or bucket in cloud console easily from tkbuild_web
# - Embed log view (query log directly?)
# - Tag/search log entries by job/workstep as well as just agent
# - Use google's auth stuff or add a simple password

if __name__=='__main__':

    parser = argparse.ArgumentParser(description='TKBuild build agent script')
    parser.add_argument("--cfg", dest="config",
                    help="config file yml", metavar="FILE",
                    default=DEFAULT_CONFIG_FILE )
    
    args = parser.parse_args()
    agentCfgFile = args.config

    agent = TKBuildAgent.createFromConfigFile( agentCfgFile )

    db = connectCloudStuff( agent, False )
    if not db:
        logging.error("Connecting to cloud stuff failed.")
        sys.exit(1)

    # Run the agent mainloop
    agent.serverMainloop( db )
    logging.info( "Tkbuild agent finished, exiting.")
