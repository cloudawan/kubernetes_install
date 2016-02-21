import os
import subprocess



os.system("kubectl delete -f private-registry-controller-wth-glusterfs.json")
os.system("kubectl delete -f private-registry-service.json")
os.system("kubectl delete -f glusterfs-endpoints.json")
os.system("kubectl delete -f glusterfs-service.json")



p = subprocess.Popen(['kubectl', 'get', 'pod'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
output, err = p.communicate()
output_line_list = output.split("\n")
for output_line in output_line_list:
    if output_line.startswith("private-registry"):
        os.system("kubectl delete pod " + output_line.split(" ")[0])

