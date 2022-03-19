
#!/bin/bash
if [ ${PWD##*/} = "webhooks" ]
then
gcloud functions deploy civclicker-repo-pushed --region=us-west3 --project=rising-environs-295900
else
echo Need to run this from the webhooks directory.
fi
