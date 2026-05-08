import json, os, zipfile, shutil

EXT_DIR = '/ext/ai_assistant'
DIST_DIR = os.path.join(EXT_DIR, 'dist')

with open(os.path.join(EXT_DIR, 'extension.json')) as f:
    ext = json.load(f)

ext_id = ext['publisher'] + '.' + ext['name']
version = ext['version']

fe_dist = os.path.join(EXT_DIR, 'frontend', 'dist')
remote_entry = None
for fn in os.listdir(fe_dist):
    if fn.startswith('remoteEntry') and fn.endswith('.js'):
        remote_entry = fn
        break

if not remote_entry:
    raise RuntimeError('No remoteEntry found')

manifest = {
    'id': ext_id,
    'publisher': ext['publisher'],
    'name': ext['name'],
    'version': version,
    'displayName': ext.get('displayName', ''),
    'license': ext.get('license', ''),
    'permissions': ext.get('permissions', []),
    'frontend': {
        'contributions': ext.get('frontend', {}).get('contributions', {}),
        'moduleFederation': ext.get('frontend', {}).get('moduleFederation', {}),
        'remoteEntry': remote_entry,
        'moduleFederationName': ext.get('frontend', {}).get('moduleFederation', {}).get('name', ''),
    },
    'backend': {
        'entryPoints': ext.get('backend', {}).get('entryPoints', []),
        'entrypoint': ext.get('backend', {}).get('entryPoints', [''])[0],
        'dependencies': ext.get('backend', {}).get('dependencies', {}),
    },
}

os.makedirs(DIST_DIR, exist_ok=True)

manifest_path = os.path.join(DIST_DIR, 'manifest.json')
with open(manifest_path, 'w') as f:
    json.dump(manifest, f, indent=2)
print('Wrote ' + manifest_path)

# Archive expects: frontend/dist/<files> and backend/src/<files>
fe_out = os.path.join(DIST_DIR, 'frontend', 'dist')
if os.path.exists(os.path.join(DIST_DIR, 'frontend')):
    shutil.rmtree(os.path.join(DIST_DIR, 'frontend'))
os.makedirs(os.path.join(DIST_DIR, 'frontend'), exist_ok=True)
shutil.copytree(fe_dist, fe_out)
print('Copied frontend dist -> ' + fe_out)

be_out = os.path.join(DIST_DIR, 'backend', 'src')
if os.path.exists(os.path.join(DIST_DIR, 'backend')):
    shutil.rmtree(os.path.join(DIST_DIR, 'backend'))
os.makedirs(os.path.join(DIST_DIR, 'backend'), exist_ok=True)
be_src = os.path.join(EXT_DIR, 'backend', 'src')
shutil.copytree(be_src, be_out)
print('Copied backend src -> ' + be_out)

supx_name = ext_id + '-' + version + '.supx'
supx_path = os.path.join(DIST_DIR, supx_name)
with zipfile.ZipFile(supx_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.write(manifest_path, arcname='manifest.json')
    for root, dirs, files in os.walk(fe_out):
        for fn in files:
            full = os.path.join(root, fn)
            arcname = os.path.relpath(full, DIST_DIR)
            zf.write(full, arcname=arcname)
    for root, dirs, files in os.walk(be_out):
        for fn in files:
            full = os.path.join(root, fn)
            arcname = os.path.relpath(full, DIST_DIR)
            zf.write(full, arcname=arcname)

print('Created ' + supx_path)
print('Size: ' + str(os.path.getsize(supx_path)) + ' bytes')
