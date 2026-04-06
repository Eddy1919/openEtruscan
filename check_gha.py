import urllib.request
import json
req = urllib.request.Request('https://api.github.com/repos/Eddy1919/openEtruscan/actions/runs', headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        for run in data.get('workflow_runs', [])[:5]:
            print(f"{run['name']} - {run['status']} - {run['conclusion']} - {run['html_url']}")
except Exception as e:
    print(e)
