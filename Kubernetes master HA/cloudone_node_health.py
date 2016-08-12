import socket
import fcntl
import struct
import json
import urllib
import time
import traceback
from datetime import datetime
from datetime import timedelta
from datetime import tzinfo
from subprocess import check_output
from httplib2 import Http


class UTC(tzinfo):
	def utcoffset(self, dt):
		return timedelta(0)
	def tzname(self, dt):
		return "UTC"
	def dst(self, dt):
		return timedelta(0)


class CloudOneNodeHealth:
	# Define host type here. Mark the unused type
	HostTypeKubernetes = "kubernetes"
	HostTypeGlusterfs = "glusterfs"
	HostTypeSLB = "slb"

	def __init__(self):
		self.host_type_list = self.__get_host_type_list_from_attribute()
		self.check_interval = 1
		self.status_ttl_in_second = 10
		# ISO 8601 format: YYYY-MM-DDTHH:MM:SS.mmmmmm+HH:MM
		self.time_format = "%Y-%m-%dT%H:%M:%S.%f%z"
		self.ip = self.__get_ip_address("eth0")
		self.etcd_host_and_port = "http://127.0.0.1:4001"
		self.h = Http(timeout=10)
		# HAProxy slb command file
		self.slb_command_file_path = "/etc/haproxy/haproxy.cfg.command"

	def __get_host_type_list_from_attribute(self):
		host_type_list=[]
		if hasattr(self, "HostTypeKubernetes"):
			host_type_list.append(self.HostTypeKubernetes)
		if hasattr(self, "HostTypeGlusterfs"):
			host_type_list.append(self.HostTypeGlusterfs)
		if hasattr(self, "HostTypeSLB"):
			host_type_list.append(self.HostTypeSLB)
		return host_type_list

	def __get_ip_address(self, ifname):
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		try:
			device = fcntl.ioctl(
				s.fileno(),
				0x8915,  # SIOCGIFADDR
				struct.pack('256s', ifname[:15])
			)
			ip = socket.inet_ntoa(device[20:24])
		except IOError as e:
			ip = None
		s.close()
		return ip

	def __is_service_running(self, name, has_keyword="start/running", has_no_keyword=None, command_list=None):
		try:
			if command_list is None:
				result = check_output(["sudo", "service", name, "status"])
			else:
				result = check_output(command_list)
			if has_no_keyword is not None:
				if has_no_keyword in result:
					return False
				else:
					return True
			if has_keyword in result:
				return True
			else:
				return False
		except Exception as e:
			return False

	def health_check(self):
		try:
			status_dictionary = dict()
			status_dictionary["update_time_stamp"] = datetime.now(UTC()).strftime(self.time_format)
			status_dictionary["host_type_list"] = self.host_type_list
			status_dictionary["service"] = dict()
			
			# Kubernetes
			if hasattr(self, "HostTypeKubernetes"):
				status_dictionary["service"]["flanneld"] = self.__is_service_running("flanneld")
				status_dictionary["service"]["docker"] = self.__is_service_running("docker")
				status_dictionary["service"]["kube-apiserver"] = self.__is_service_running("kube-apiserver")
				status_dictionary["service"]["kube-controller-manager"] = self.__is_service_running("kube-controller-manager")
				status_dictionary["service"]["kube-scheduler"] = self.__is_service_running("kube-scheduler")
				status_dictionary["service"]["kube-proxy"] = self.__is_service_running("kube-proxy")
				status_dictionary["service"]["kubelet"] = self.__is_service_running("kubelet")

				status_dictionary["docker"] = dict()
				status_dictionary["docker"]["ip"] = self.__get_ip_address("docker0")

				status_dictionary["flannel"] = dict()
				status_dictionary["flannel"]["ip"] = self.__get_ip_address("flannel.1")
			# Glusterfs
			if hasattr(self, "HostTypeGlusterfs"):
				status_dictionary["service"]["glusterfs-server"] = self.__is_service_running("glusterfs-server")
			# SLB
			if hasattr(self, "HostTypeSLB"):
				status_dictionary["service"]["haproxy"] = self.__is_service_running("haproxy", has_keyword="running")
				status_dictionary["service"]["keepalived"] = self.__is_service_running("keepalived", has_no_keyword="No such file or directory", command_list=["cat", "/var/run/keepalived.pid"])
				status_dictionary["service"]["cloudone_slb"] = self.__is_service_running("cloudone_slb")
				status_dictionary["slb_daemon"] = dict()
				status_dictionary["slb_daemon"]["last_command_created_time"] = self.__get_latest_slb_command_created_time()

			self.__save_health_status(status_dictionary)
			return status_dictionary
		except Exception as e:
			print e
			traceback.print_stack()
			return None

	def __save_health_status(self, data_dictionary):
		encoded_parameter = urllib.urlencode({
			"value": json.dumps(data_dictionary),
			"ttl": self.status_ttl_in_second
		})
		head, body = self.h.request(self.etcd_host_and_port + "/v2/keys/cloudawan/cloudone/health/" + str(self.ip) + "?" + encoded_parameter, "PUT")
		if head.status != 200 and head.status != 201:
			print "Fail to save health status"
			print data_dictionary
			print head
			print body
		else:
			pass
			#print "Succeed to save health status"
			#print body

	def loop(self):
		while True:
			self.health_check()
			time.sleep(self.check_interval)

	def __get_latest_slb_command_created_time(self):
		try:
			with open(self.slb_command_file_path, "r") as file_read:
				file_content = file_read.read()
			slb_command_dictionary = json.loads(file_content)
			return slb_command_dictionary.get("CreatedTime")
		except Exception as e:
			print e
			traceback.print_stack()
			return None

cloudOneNodeHealth = CloudOneNodeHealth()
cloudOneNodeHealth.loop()
	