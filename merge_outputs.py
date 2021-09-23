import glob
import json
import os
import time
from collections import defaultdict

filenames = glob.glob('diff_*.json')
all_data = defaultdict(int)

for filename in filenames:
    with open(filename, 'r') as fd:
        data = json.load(fd)
    for key, value in data.items():
        all_data[key] += value

with open(f'merged_{int(time.time())}.json', 'w') as fd:
    json.dump(all_data, fd)

for filename in filenames:
    os.remove(filename)
