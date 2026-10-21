import json, os

routing_file = 'D:/hermes/data/agent_knowledge/_agent_routing.json'
if os.path.exists(routing_file):
    with open(routing_file) as f:
        routing = json.load(f)
else:
    routing = {'routing': []}

physics_routes = [
    {'domain': 'physics/solid_state', 'agents': ['通量', '算渊'], 'priority': 'P0'},
    {'domain': 'physics/computational', 'agents': ['算渊', '通量'], 'priority': 'P0'},
    {'domain': 'ceramics/sintering', 'agents': ['程实', '伏安'], 'priority': 'P0'},
    {'domain': 'ceramics/mechanical', 'agents': ['构形', '程实'], 'priority': 'P1'},
    {'domain': 'ceramics/dielectric', 'agents': ['伏安', '通量'], 'priority': 'P1'},
    {'domain': 'ceramics/advanced', 'agents': ['程实', '构形'], 'priority': 'P1'},
]
existing = {r['domain'] for r in routing['routing']}
for route in physics_routes:
    if route['domain'] not in existing:
        routing['routing'].append(route)

with open(routing_file, 'w') as f:
    json.dump(routing, f, ensure_ascii=False, indent=2)
print(f'✅ Routing updated: {len(physics_routes)} new routes')
print(f'   Total routes: {len(routing["routing"])}')
