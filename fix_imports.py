import os
import glob
mapping = {
    'adapter': 'core.adapter',
    'artifacts': 'core.artifacts',
    'cli': 'core.cli',
    'config': 'core.config',
    'converter': 'core.converter',
    'corpus': 'core.corpus',
    'epidoc': 'core.epidoc',
    'geo': 'core.geo',
    'normalizer': 'core.normalizer',
    'prosopography': 'core.prosopography',
    'statistics': 'core.statistics',
    'validator': 'core.validator',
    'classifier': 'ml.classifier',
    'cltk_module': 'ml.cltk_module',
    'neural': 'ml.neural'
}
for f in glob.glob('tests/*.py'):
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    for old, new in mapping.items():
        content = content.replace(f'from openetruscan.{old}', f'from openetruscan.{new}')
        content = content.replace(f'import openetruscan.{old}', f'import openetruscan.{new}')
    with open(f, 'w', encoding='utf-8') as file:
        file.write(content)
print("Finished replacements")
