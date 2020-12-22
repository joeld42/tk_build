# tk_build
Tapnik Build Scripts

These are my build scripts for my apps and games.
Probably not useful for general use but you're welcome to try.


Limitations and TODOS
---
1. web app doesn't really work with github/unix permissions stuff very well. 
  Workaround is to checkout the `pristine_repo` manually to authenticate it.
1. Biggest TODO is it can't handle multiple agents right now, it assumes 
  that each agent is the only one that could handle a matching job. This is
  not a high priority for me since I only have one build agent per platform
  so it doesn't come up.

Features
---
1. Lightweight. This is intended for games and apps built by small teams 
   without a lot of build deploy process. It's just one or two steps removed
   from doing a manual build.
1. _"Serverless"_ in that it's using firestore as the only required server. This means
   the web agent doesn't need to be running for builds to work, it's only a convienant way
   to see what's going on. It's a reasonable and supported use case to only
   set up the agent scripts and use webhooks to submit builds.
1. Reuses work. This might be considered a limitation or problem if your goal
   is perfect repeatable builds, but for a medium size game project often 
   checking out assets and dependencies that very rarely change can take
   hours, so a traditional pure clean build is a huge waste of time. (TODO:
   add example of a default-skip `clean` workstep to force a clean build)

Needs better docs, these are mostly notes to myself.

Setup a new agent
---
1. Check out the `tk_build` project somewhere. Install the venv and requirments.
1. Pick a place for builds to happen and config to go. I use `/opt/tkbuild/` but this can be wherever.
1. 