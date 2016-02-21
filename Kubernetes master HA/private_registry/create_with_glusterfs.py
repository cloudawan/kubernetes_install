import json
import os
import time
from httplib2 import Http


# create an glusterfs endpoint
os.system("kubectl create -f glusterfs-endpoints.json")

# create an glusterfs service
os.system("kubectl create -f glusterfs-service.json --validate=false")

# create a replication controller to replicate nodes
os.system("kubectl create -f private-registry-controller-wth-glusterfs.json")

# create a service 
os.system("kubectl create -f private-registry-service.json")


