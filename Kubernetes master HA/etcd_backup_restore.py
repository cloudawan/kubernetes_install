from httplib2 import Http
import json
import urllib
import sys


class EtcdData:
	def __init__(self):
		self.url = "http://127.0.0.1:4001/v2/keys"
		self.h = Http()
		
	def backup(self):
		head, body = self.h.request(self.url+"?recursive=true", "GET")
		with open("backup.json", "w") as file_write:
			file_write.write(body)
		
	def restore(self):
		with open("backup.json", "r") as file_read:
			file_content = file_read.read()
		file_content_dictionary = json.loads(file_content)
		self.__recursive_restore(file_content_dictionary)

	def __recursive_restore(self, dictionary):
		nodes = dictionary.get("nodes")
		
		node = dictionary.get("node")
		if node is not None:
			if nodes is None:
				nodes = []
			nodes.append(node)
				
		if nodes is not None:
			for node in nodes:
				self.__recursive_restore(node)
		else:
			key = dictionary.get("key")
			value = dictionary.get("value")
			if value is not None:
				encoded_parameter = urllib.urlencode({
					"value": value,
				})
				self.h.request(self.url+key+"?"+encoded_parameter, "PUT")
			else:
				encoded_parameter = urllib.urlencode({
					"dir": True,
				})
				self.h.request(self.url+key+"?"+encoded_parameter, "PUT")


etcd_data = EtcdData()
if len(sys.argv)>=2 and sys.argv[1] == "backup":
	etcd_data.backup()
elif len(sys.argv)>=2 and sys.argv[1] == "restore":
	etcd_data.restore()
else:
	print "Either backup or restore"