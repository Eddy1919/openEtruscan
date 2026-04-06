import os
import requests

cities = [
    ("volterrae", "https://upload.wikimedia.org/wikipedia/commons/thumb/c/ca/Tuscany_Volterra.jpg/800px-Tuscany_Volterra.jpg"),
    ("tarquinii", "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b5/Tarquinia-panorama.jpg/800px-Tarquinia-panorama.jpg"),
    ("caere", "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ae/Banditaccia_02.jpg/800px-Banditaccia_02.jpg"),
    ("veii", "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a9/Scavi_di_Veio.jpg/800px-Scavi_di_Veio.jpg"),
    ("vulci", "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ac/Vulci_-_Castello_dell%27Abbadia.jpg/800px-Vulci_-_Castello_dell%27Abbadia.jpg"),
    ("vetulonia", "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7b/Vetulonia_Mura_Ciclopiche_01.jpg/800px-Vetulonia_Mura_Ciclopiche_01.jpg"),
    ("clusium", "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Chiusi_panorama.jpg/800px-Chiusi_panorama.jpg"),
    ("perusia", "https://upload.wikimedia.org/wikipedia/commons/thumb/a/af/Perugia_arco_etrusco.jpg/800px-Perugia_arco_etrusco.jpg"),
    ("cortona", "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Panoramica_Cortona%2C_Italia.jpg/800px-Panoramica_Cortona%2C_Italia.jpg"),
    ("arretium", "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/Arezzo_-_Piazza_Grande.jpg/800px-Arezzo_-_Piazza_Grande.jpg"),
    ("faesulae", "https://upload.wikimedia.org/wikipedia/commons/thumb/0/07/Fiesole_-_Teatro_Romano_04.jpg/800px-Fiesole_-_Teatro_Romano_04.jpg"),
    ("populonia", "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e3/Populonia.jpg/800px-Populonia.jpg")
]

out_dir = r"c:\Users\edpan\openEtruscan\frontend\public\images\cities"
os.makedirs(out_dir, exist_ok=True)

headers = {"User-Agent": "OpenEtruscan/1.0 (https://github.com/edpan/openetruscan)"}

for id, url in cities:
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        with open(os.path.join(out_dir, f"{id}.jpg"), "wb") as f:
            f.write(r.content)
        print(f"[{id}] downloaded successfully.")
    else:
        print(f"[{id}] failed with status {r.status_code}")
