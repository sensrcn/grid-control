#-#  Copyright 2013-2014 Karlsruhe Institute of Technology
#-#
#-#  Licensed under the Apache License, Version 2.0 (the "License");
#-#  you may not use this file except in compliance with the License.
#-#  You may obtain a copy of the License at
#-#
#-#      http://www.apache.org/licenses/LICENSE-2.0
#-#
#-#  Unless required by applicable law or agreed to in writing, software
#-#  distributed under the License is distributed on an "AS IS" BASIS,
#-#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#-#  See the License for the specific language governing permissions and
#-#  limitations under the License.

from grid_control import QM, utils, UserError, DatasetError, RethrowError, datasets
from grid_control.datasets import DataProvider
from provider_cms import CMSProvider
from webservice_api import *
import os

# required format: <dataset path>[@<instance>][#<block>]
class DBS3Provider(CMSProvider):
	def __init__(self, config, datasetExpr, datasetNick, datasetID = 0):
		CMSProvider.__init__(self, config, datasetExpr, datasetNick, datasetID)
		if self.url != '':
			raise ConfigError('Other DBS instances are not yet supported!')
		self.url = 'https://cmsweb.cern.ch/dbs/prod/global/DBSReader'


	def queryDBSv3(self, api, **params):
		proxyPath = os.environ.get('X509_USER_PROXY', '')
		if not os.path.exists(proxyPath):
			raise UserError('VOMS proxy needed to query DBS3! Environment variable X509_USER_PROXY is "%s"' % proxyPath)
		return readJSON(self.url + '/%s' % api, params, cert = os.environ['X509_USER_PROXY'])


	def getCMSDatasetsImpl(self, datasetPath):
		pd, sd, dt = (datasetPath.lstrip('/') + '/*/*/*').split('/')[:3]
		tmp = self.queryDBSv3('datasets', primary_ds_name = pd, processed_ds_name = sd, data_tier_name = dt)
		return map(lambda x: x['dataset'], tmp)


	def getCMSBlocksImpl(self, datasetPath, getSites):
		return map(lambda b: (b['block_name'], None), self.queryDBSv3('blocks', dataset = datasetPath))


	def getCMSFilesImpl(self, blockPath, onlyValid, queryLumi):
		for fi in self.queryDBSv3('files', block_name = blockPath, detail = True):
			if onlyValid and (fi['is_file_valid'] != 1):
				continue
			yield ({DataProvider.URL: fi['logical_file_name'], DataProvider.NEntries: fi['event_count']}, None)


	def getCMSLumisImpl(self, blockPath):
		result = {}
		for lumiInfo in self.queryDBSv3('filelumis', block_name = blockPath):
			tmp = (int(lumiInfo['run_num']), map(int, lumiInfo['lumi_section_num']))
			result.setdefault(lumiInfo['logical_file_name'], []).append(tmp)
		return result


	def getBlocksInternal(self):
		return self.getGCBlocks(usePhedex = True)
