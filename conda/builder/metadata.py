import re
import sys
from os.path import isdir, join

from conda.utils import memoized, md5_file
import conda.config as config
from conda.resolve import MatchSpec

from config import CONDA_PY, CONDA_NPY

import yaml



def ns_cfg():
    plat = config.subdir
    py = CONDA_PY
    np = CONDA_NPY
    for x in py, np:
        assert isinstance(x, int), x
    return dict(
        linux = plat.startswith('linux-'),
        linux32 = bool(plat == 'linux-32'),
        linux64 = bool(plat == 'linux-64'),
        armv6 = bool(plat == 'linux-armv6l'),
        osx = plat.startswith('osx-'),
        unix = plat.startswith(('linux-', 'osx-')),
        win = plat.startswith('win-'),
        win32 = bool(plat == 'win-32'),
        win64 = bool(plat == 'win-64'),
        py = py,
        py3k = bool(30 <= py < 40),
        py2k = bool(20 <= py < 30),
        py26 = bool(py == 26),
        py27 = bool(py == 27),
        py33 = bool(py == 33),
        np = np,
    )


sel_pat = re.compile(r'(.+?)\s*\[(.+)\]$')
def select_lines(data, namespace):
    lines = []
    for line in data.splitlines():
        line = line.rstrip()
        m = sel_pat.match(line)
        if m:
            cond = m.group(2)
            if eval(cond, namespace, {}):
                lines.append(m.group(1))
            continue
        lines.append(line)
    return '\n'.join(lines) + '\n'


@memoized
def yamlize(data):
    return yaml.load(data)


def parse(data):
    data = select_lines(data, ns_cfg())
    res = yamlize(data)
    # ensure the result is a dict
    if res is None:
        res = {}
    # ensure those are lists
    for field in ('source/patches',
                  'build/entry_points',
                  'build/features', 'build/track_features',
                  'requirements/build', 'requirements/run',
                  'requirements/conflicts', 'test/requires',
                  'test/files', 'test/commands', 'test/imports'):
        section, key = field.split('/')
        if res.get(section) is None:
            res[section] = {}
        if res[section].get(key, None) is None:
            res[section][key] = []
    # ensure those are strings
    for field in ('package/version',
                  'source/git_tag', 'source/git_branch', 'source/md5'):
        section, key = field.split('/')
        if res.get(section) is None:
            res[section] = {}
        res[section][key] = str(res[section].get(key, ''))
    return res


class MetaData(object):

    def __init__(self, path):
        assert isdir(path)
        self.path = path
        self.meta_path = join(path, 'meta.yaml')
        self.meta = parse(open(self.meta_path).read())

    def get_section(self, section):
        return self.meta.get(section, {})

    def get_value(self, field, default=None):
        section, key = field.split('/')
        return self.get_section(section).get(key, default)

    def name(self):
        res = self.get_value('package/name')
        if not res:
            sys.exit('Error: package/name missing in: %r' % self.meta_path)
        res = str(res)
        if res != res.lower():
            sys.exit('Error: package/name must be lowercase, got: %r' % res)
        return res

    def version(self):
        return self.get_value('package/version')

    def build_number(self):
        return int(self.get_value('build/number', 0))

    def ms_depends(self, typ='run'):
        res = []
        for spec in self.get_value('requirements/' + typ):
            ms = MatchSpec(spec)
            for name, ver in [('python', CONDA_PY), ('numpy', CONDA_NPY)]:
                if ms.name == name:
                    assert ms.strictness == 1
                    ms = MatchSpec('%s %s*' % (name, '.'.join(str(ver))))
            res.append(ms)
        return res

    def build_id(self):
        res = []
        for name, s in (('numpy', 'np'), ('python', 'py')):
            for ms in self.ms_depends():
                if ms.name == name:
                    v = ms.spec.split()[1]
                    res.append(s + v[0] + v[2])
                    break
        if res:
            res.append('_')
        res.append('%d' % self.build_number())
        return ''.join(res)

    def dist(self):
        return '%s-%s-%s' % (self.name(), self.version(), self.build_id())

    def is_app(self):
        return bool(self.get_value('app/entry'))

    def app_meta(self):
        d = {'type': 'app'}
        if self.get_value('app/icon'):
            d['icon'] = '%s.png' % md5_file(join(
                    self.path, self.get_value('app/icon')))

        for field, key in [('app/entry', 'app_entry'),
                           ('app/type', 'app_type'),
                           ('app/cli_opts', 'app_cli_opts'),
                           ('app/summary', 'summary')]:
            value = self.get_value(field)
            if value:
                d[key] = value
        return d

    def info_index(self):
        d = dict(
            name = self.name(),
            version = self.version(),
            build = self.build_id(),
            build_number = self.build_number(),
            platform = config.platform,
            arch = config.arch_name,
            depends = sorted(ms.spec for ms in self.ms_depends())
        )
        if self.is_app():
            d.update(self.app_meta())
        return d


if __name__ == '__main__':
    from pprint import pprint
    from os.path import expanduser

    m = MetaData(expanduser('~/conda-recipes/pycosat'))
    pprint(m.info_index())
