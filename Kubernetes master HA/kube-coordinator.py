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


class NodeStatus:
	def __init__(self):
		self.maximum_check_amount = 15 * 60 # Check each second
		self.start = True
		self.etcd_url = "http://127.0.0.1:4001/v2/keys/cloudawan/cloudone/health"
		self.kubeapi_url = "http://127.0.0.1:8080/api/v1/nodes"
		self.h = Http()
		
	# This is used to make sure all services are up and all nodes are ready before start scheduler and controller-manager. Otherwise, the pods are not assigned to those nodes which are under initialization.
	def should_wait_for_all_services_up_and_all_nodes_ready_after_start(self):
		if self.start:
			self.maximum_check_amount -= 1
			if self.maximum_check_amount <= 0:
				print "After maximum check amount, stop checking"
				self.start = False
				return False
			else:
				result = self.is_all_service_up() and self.is_all_node_ready()
				if result:
					print "All services are up and all nodes are ready, stop checking"
					self.start = False
					return False
				else:
					return True
		else:
			return False
	
	# This is used to make sure all services are up before start scheduler and controller-manager. Otherwise, the pods are not assigned to those nodes which are under initialization.
	def should_wait_for_all_services_up_after_start(self):
		if self.start:
			self.maximum_check_amount -= 1
			if self.maximum_check_amount <= 0:
				print "After maximum check amount, stop checking"
				self.start = False
				return False
			else:
				result = self.is_all_service_up()
				if result:
					print "All services are up, stop checking"
					self.start = False
					return False
				else:
					return True
		else:
			return False
	
	def is_all_service_up(self):
		try:
			head, body = self.h.request(self.etcd_url, "GET")
			if head.status != 200:
				print "Fail to get the data from etcd"
				print head
				print body
				return False
			else:
				body_dictionary = json.loads(body)
				node_list = body_dictionary.get("node").get("nodes")
				
				if len(node_list) == 0:
					print "No node in the list"
					return False
				
				for node in node_list:
					ttl = node.get("ttl")
					if ttl < 0:
						# Invalid data
						return False
					
					value = node.get("value")
					value_dictionary = json.loads(value)
					if value_dictionary.get("service").get("flanneld") is False:
						return False
					if value_dictionary.get("flannel").get("ip") is None:
						return False
					if value_dictionary.get("service").get("docker") is False:
						return False
					if value_dictionary.get("docker").get("ip") is None:
						return False
					if value_dictionary.get("service").get("kubelet") is False:
						return False
					if value_dictionary.get("service").get("kube-proxy") is False:
						return False
					if value_dictionary.get("service").get("kube-apiserver") is False:
						return False
					
				print "All services are ready"
				print body_dictionary	
				return True
		except Exception as e:
			print e
			return False
	
	# This is used to make sure all node are ready before start scheduler and controller-manager. Otherwise, the pods are not assigned to those nodes which are under initialization.
	def should_wait_for_all_node_ready_after_start(self):
		if self.start:
			self.maximum_check_amount -= 1
			if self.maximum_check_amount <= 0:
				print "After maximum check amount, stop checking"
				self.start = False
				return False
			else:
				result = self.is_all_node_ready()
				if result:
					print "All nodes are ready, stop checking"
					self.start = False
					return False
				else:
					return True
		else:
			return False
	
	def is_all_node_ready(self):
		try:
			head, body = self.h.request(self.kubeapi_url, "GET")
			if head.status != 200:
				print "Fail to get the data from kubeapi"
				print head
				print body
				return False
			else:
				body_dictionary = json.loads(body)
				node_list = body_dictionary.get("items")
				
				if len(node_list) == 0:
					print "No node in the list"
					return False
				
				for node in node_list:
					ready = False
					condition_list = node.get("status").get("conditions")
					for condition in condition_list:
						if condition.get("type") == "Ready":
							if condition.get("status") == "True":
								ready = True
					if ready is False:
						return False
				print "All nodes are ready"
				print body_dictionary
				return True
		except Exception as e:
			print e
			return False
		


class KubeCoordinator:
	def __init__(self):
		self.check_interval = 1
		self.timeout = 10
		self.waitting_after_accquired = 10
		self.etcd_url = "http://127.0.0.1:4001/v2/keys/cloudawan/master"
		self.ip = self.__get_ip_address("eth0")
		self.h = Http()
		self.time_format = "%Y-%m-%dT%H:%M:%S.%f"
		self.node_status = NodeStatus()

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
			if self.node_status.should_wait_for_all_services_up_and_all_nodes_ready_after_start() is False:
				if self.check():
					self.activate_service_if_not_running("kube-scheduler")
					self.activate_service_if_not_running("kube-controller-manager")
				else:
					self.inactivate_service_if_running("kube-scheduler")
					self.inactivate_service_if_running("kube-controller-manager")
			else:
				print "Wait for all services to be up and all nodes to be ready, remaining retry: " + str(self.node_status.maximum_check_amount)
			time.sleep(self.check_interval)

KubeCoordinator().loop()
