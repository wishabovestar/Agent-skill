import json
d=json.load(open('_fetch2_0928.json',encoding='utf-8'))
for k,v in d.items():
    print('='*30,k,len(v))
    print(v[:2400])
    print()
