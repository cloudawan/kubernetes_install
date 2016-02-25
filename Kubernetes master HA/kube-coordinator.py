from httplib2 import Http
from datetime import datetime
import json
import time
import socket
import urllib
import socket
import fcntl
import struct
from subprocess import check_output


class KubeletStatus:
	def __init__(self):
		self.start = True
		self.etcd_url = "http://127.0.0.1:4001/v2/keys/cloudawan/cloudone/health"
		self.h = Http()
	
	# This is used to make sure all kubelet are up before start scheduler and controller-manager. Otherwise, the pods are not assigned to those nodes which are under initialization.
	def should_wait_for_all_kubelet_up_after_start(self):
		if self.start:
			result = self.is_all_up()
			if result:
				self.start = False
				return False
			else:
				return True
		else:
			return False
	
	def is_all_up(self):
		try:
			head, body = self.h.request(self.etcd_url, "GET")
			if head.status != 200:
				print "Fail to set self as selected master"
				print head
				print body
				return False
			else:
				body_dictionary = json.loads(body)
				node_list = body_dictionary.get("node").get("nodes")
				for node in node_list:
					value = node.get("value")
					value_dictionary = json.loads(value)
					if value_dictionary.get("service").get("kubelet") is False:
						return False
				return True
		except Exception as e:
			print e
			return False


class KubeCoordinator:
	def __init__(self):
		self.check_interval = 1
		self.timeout = 5
		self.waitting_after_accquired = 5
		self.etcd_url = "http://127.0.0.1:4001/v2/keys/cloudawan/master"
		self.ip = self.__get_ip_address("eth0")
		self.h = Http()
		self.time_format = "%Y-%m-%dT%H:%M:%S.%f"
		self.kubelet_status = KubeletStatus()

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

	def __set_self_as_selected_master(self, first_time_stamp=None):
		try:
			last_time_stamp = datetime.now().strftime(self.time_format)
			if first_time_stamp is None:
				first_time_stamp = last_time_stamp
			data = {
				"first_time_stamp": first_time_stamp,
				"last_time_stamp": last_time_stamp,
				"ip": self.ip,
			}
			encoded_parameter = urllib.urlencode({
				"value": json.dumps(data),
			})
			head, body = self.h.request(self.etcd_url + "?" + encoded_parameter, "PUT")
			if head.status != 200 and head.status != 201:
				print "Fail to set self as selected master"
				print head
				print body
			else:
				pass
				#print "Succeed to set self as selected master"
				#print body
		except Exception as e:
			print e
			
	def activate_service_if_not_running(self, name):
		result = check_output(["sudo", "service", name, "status"])
		if "start/running" not in result:
			# Activate if not running
			check_output(["sudo", "service", name, "restart"])
			print "Activate " + name
			
	def inactivate_service_if_running(self, name):
		result = check_output(["sudo", "service", name, "status"])
		if "start/running" in result:
			# Inactivate if running
			check_output(["sudo", "service", name, "stop"])
			print "Inactivate " + name
		
	def check(self):
		try:
			head, body = self.h.request(self.etcd_url, "GET")
			if head.status == 200:
				body_dictionary = json.loads(body)
				value_dictionary = json.loads(body_dictionary.get("node").get("value"))
				last_time = datetime.strptime(value_dictionary.get("last_time_stamp"), self.time_format)
				now = datetime.now()
				if (now - last_time).total_seconds() > self.timeout:
					# Every candidate could try to acquire if timeout
					self.__set_self_as_selected_master()
					return False
				else:
					ip = value_dictionary.get("ip")
					if ip == self.ip:
						# Acquired so renew timestamp
						first_time_stamp = value_dictionary.get("first_time_stamp")
						self.__set_self_as_selected_master(first_time_stamp)
						# Activate after acquiring more than defined time_format
						first_time = datetime.strptime(first_time_stamp, self.time_format)
						if (last_time-first_time).total_seconds() > self.waitting_after_accquired:
							# Check if activated
							return True
					return False
			elif head.status == 404:
				# Every candidate could try to acquire if no data yet
				self.__set_self_as_selected_master()
				return False
		except Exception as e:
			print e
			return False

	def loop(self):
		while True:
			# This is used to make sure all kubelet are up before start scheduler and controller-manager. Otherwise, the pods are not assigned to those nodes which are under initialization.
			if self.kubelet_status.should_wait_for_all_kubelet_up_after_start() is False:
				if self.check():
					self.activate_service_if_not_running("kube-scheduler")
					self.activate_service_if_not_running("kube-controller-manager")
				else:
					self.inactivate_service_if_running("kube-scheduler")
					self.inactivate_service_if_running("kube-controller-manager")
			time.sleep(self.check_interval)

KubeCoordinator().loop()
