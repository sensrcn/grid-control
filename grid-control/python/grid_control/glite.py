from __future__ import generators
import sys, os, time, copy, popen2, tempfile, cStringIO
from grid_control import ConfigError, WMS, Job, utils

try:
	from email.utils import parsedate
except ImportError:
	from email.Utils import parsedate

class Glite(WMS):
	_statusMap = {
		'ready':	Job.READY,
		'waiting':	Job.WAITING,
		'queued':	Job.QUEUED,
		'scheduled':	Job.QUEUED,
		'running':	Job.RUNNING,
		'failed':	Job.FAILED,
		'done':		Job.DONE,
		'aborted':	Job.ABORTED
	}

	def __init__(self, config, module, init):
		WMS.__init__(self, config, module, init)

		self._submitExec = utils.searchPathFind('glite-job-submit')
		self._statusExec = utils.searchPathFind('glite-job-status')
		self._outputExec = utils.searchPathFind('glite-job-output')

		self._configVO = config.getPath('glite', 'config-vo', '')
		if self._configVO != '' and not os.path.exists(self._configVO):
			raise ConfigError("--config-vo file '%s' does not exist." % self._configVO)


	def _escape(value):
		repl = { '\\': r'\\', '\"': r'\"', '\n': r'\n' }
		def replace(char):
			try:
				return repl[char]
			except:
				return char
		return '"' + str.join('', map(replace, value)) + '"'
	_escape = staticmethod(_escape)


	def memberReq(self, member):
		return 'Member(%s, other.GlueHostApplicationSoftwareRunTimeEnvironment)' \
		       % self._escape(member)


	def wallTimeReq(self, wallTime):
		return '(other.GlueCEPolicyMaxWallClockTime >= %d)' \
		       % int((wallTime + 59) / 60)


	def storageReq(self, sites):
		def makeMember(member):
			return "Member(%s, other.GlueCESEBindGroupSEUniqueID)" % self._escape(member)
		if len(sites) == 0:
			return None
		elif len(sites) == 1:
			return makeMember(sites[0])
		else:
			return '(' + str.join(' || ', map(makeMember, sites)) + ')'


	def sitesReq(self, site, neg):
		if neg:
			format = '!RegExp(%s, other.GlueCEUniqueID)'
		else:
			format = 'RegExp(%s, other.GlueCEUniqueID)'

		return format % self._escape(site)


	def makeJDL(self, fp, job):
		contents = {
			'Executable': 'run.sh',
			'Arguments': self.module.getJobArguments(job),
			'InputSandbox': self.sandboxIn,
			'StdOutput': 'stdout.txt',
			'StdError': 'stderr.txt',
			'OutputSandbox': self.sandboxOut,
			'_Requirements': self.formatRequirements(self.module.getRequirements()),
			'VirtualOrganisation': self.config.get('grid', 'vo'),
			'RetryCount': 2
		}

		# JDL parameter formatter
		def jdlRep(value):
			if type(value) in (int, long):
				return str(value)
			elif type(value) in (tuple, list):
				return '{ ' + str.join(', ', map(jdlRep, value)) + ' }'
			else:
				return self._escape(value)

		# write key <-> formatted parameter pairs
		for key, value in contents.items():
			if key[0] == '_':
				key = key[1:]
			else:
				value = jdlRep(value)

			if value != '':
				fp.write("%s = %s;\n" % (key, value))


	def _parseStatus(self, lines):
		cur = None

		def format(data):
			data = copy.copy(data)
			status = data['status'].lower()
			try:
				status = status.split()[0]
			except:
				pass
			data['status'] = self._statusMap[status]
			try:
				data['timestamp'] = int(time.mktime(parsedate(data['timestamp'])))
			except:
				pass
			return data

		for line in lines:
			try:
				key, value = line.split(':', 1)
			except:
				continue
			key = key.strip().lower()
			value = value.strip()

			if key.startswith('status info'):
				key = 'id'
			elif key.startswith('current status'):
				key = 'status'
			elif key.startswith('status reason'):
				key = 'reason'
			elif key.startswith('destination'):
				key = 'dest'
			elif key.startswith('reached') or \
			     key.startswith('submitted'):
				key = 'timestamp'
			else:
				continue

			if key == 'id':
				if cur != None:
					try:
						yield format(cur)
					except:
						pass
				cur = { 'id': value }
			else:
				cur[key] = value

		if cur != None:
			try:
				yield format(cur)
			except:
				pass


	def submitJob(self, id, job):
		try:
			fd, jdl = tempfile.mkstemp('.jdl')
		except AttributeError:	# Python 2.2 has no tempfile.mkstemp
			while True:
				jdl = tempfile.mktemp('.jdl')
				try:
					fd = os.open(jdl, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
				except OSError:
					continue
				break

		log = tempfile.mktemp('.log')

		try:
			data = cStringIO.StringIO()
			self.makeJDL(data, id)
			data = data.getvalue()

			job.set('jdl', data)

			fp = os.fdopen(fd, 'w')
			fp.write(data)
			fp.close()
			# FIXME: error handling

			params = ''
			if self._configVO != '':
				params += ' --config-vo %s' % self._escape(self._configVO)

			proc = popen2.Popen3("%s%s --nomsg --noint --logfile %s %s"
			                     % (self._submitExec, params,
			                        self._escape(log),
			                        self._escape(jdl)), True)

			id = None

			for line in proc.fromchild.readlines():
				line = line.strip()
				if line.startswith('http'):
					id = line
			retCode = proc.wait()

			if retCode != 0:
				#FIXME
				print >> sys.stderr, "WARNING: glite-job-submit failed:"
			elif id == None:
				print >> sys.stderr, "WARNING: glite-job-submit did not yield job id:"

			if id == None:
				for line in open(log, 'r'):
					sys.stderr.write(line)

			# FIXME: glite-job-submit
			return id

		finally:
			try:
				os.unlink(jdl)
			except:
				pass
			try:
				os.unlink(log)
			except:
				pass


	def checkJobs(self, ids):
		if len(ids) == 0:
			return []

		try:
			fd, jobs = tempfile.mkstemp('.jobids')
		except AttributeError:	# Python 2.2 has no tempfile.mkstemp
			while True:
				jobs = tempfile.mktemp('.jobids')
				try:
					fd = os.open(jobs, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
				except OSError:
					continue
				break

		log = tempfile.mktemp('.log')

		result = []

		try:
			fp = os.fdopen(fd, 'w')
			for id in ids:
				fp.write("%s\n" % id)
			fp.close()
			# FIXME: error handling

			proc = popen2.Popen3("%s --noint --logfile %s -i %s"
			                     % (self._statusExec,
			                        self._escape(log),
			                        self._escape(jobs)), True)

			for data in self._parseStatus(proc.fromchild.readlines()):
				id = data['id']
				del data['id']
				status = data['status']
				del data['status']
				result.append((id, status, data))

			retCode = proc.wait()
			if retCode != 0:
				#FIXME
				print >> sys.stderr, "WARNING: glite-job-status failed:"
				for line in open(log, 'r'):
					sys.stderr.write(line)

		finally:
			try:
				os.unlink(jobs)
			except:
				pass
			try:
				os.unlink(log)
			except:
				pass

		return result


	def retrieveJobs(self, ids):
		if len(ids) == 0:
			return []

		try:
			fd, jobs = tempfile.mkstemp('.jobids')
		except AttributeError:	# Python 2.2 has no tempfile.mkstemp
			while True:
				jobs = tempfile.mktemp('.jobids')
				try:
					fd = os.open(jobs, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
				except OSError:
					continue
				break

		log = tempfile.mktemp('.log')

		result = []

		try:
			fp = os.fdopen(fd, 'w')
			for id in ids:
				fp.write("%s\n" % id)
			fp.close()
			# FIXME: error handling

			proc = popen2.Popen3("%s --noint --logfile %s -i %s --dir %s"
			                     % (self._outputExec,
			                        self._escape(log),
			                        self._escape(jobs),
			                        self._escape(self._outputPath)),
			                        True)

			for data in proc.fromchild.readlines():
				# FIXME: moep
				pass

			retCode = proc.wait()
			if retCode != 0:
				#FIXME
				print >> sys.stderr, "WARNING: glite-job-output failed:"
				for line in open(log, 'r'):
					sys.stderr.write(line)

		finally:
			try:
				os.unlink(jobs)
			except:
				pass
			try:
				os.unlink(log)
			except:
				pass

		return result
