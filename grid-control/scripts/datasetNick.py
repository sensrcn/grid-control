#!/usr/bin/env python
#-#  Copyright 2011-2014 Karlsruhe Institute of Technology
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

from gcSupport import *
from grid_control.datasets import DataProvider, NickNameProducer
from grid_control_cms.provider_dbsv2 import createDBSAPI

usage = '%s [OPTIONS] <DBS dataset path>' % sys.argv[0]
parser = optparse.OptionParser(usage=usage)
parser.add_option('-n', '--nickproducer', dest='nprod', default='SimpleNickNameProducer',
	help='Name of the nickname producer')
(opts, args) = parseOptions(parser)

def main():
	if len(args) == 0:
		print 'Dataset path not specified!'
		sys.exit(0)
	datasetPath = args[0]
	if '*' in datasetPath:
		api = createDBSAPI('')
		pd, sd, dt = (datasetPath.lstrip("/") + "/*/*/*").split("/")[:3]
		toProcess = map(lambda x: x.get("PathList", [])[-1], api.listProcessedDatasets(pd, dt, sd))
	else:
		toProcess = [datasetPath]

	nProd = NickNameProducer.open(opts.nprod, Config().addSections(['dataset']))
	utils.printTabular(
		[(0, 'Nickname'), (1, 'Dataset')],
		map(lambda ds: {0: nProd.getName('', ds, None), 1: ds}, toProcess), 'll')

handleException(main)
