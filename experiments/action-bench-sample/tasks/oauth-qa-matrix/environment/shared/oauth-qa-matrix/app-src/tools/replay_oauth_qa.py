#!/usr/bin/env python
import json
from linking.replay import write_artifact
print(json.dumps(write_artifact(), indent=2, sort_keys=True))
