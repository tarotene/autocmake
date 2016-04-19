#!/usr/bin/env python

import os
import sys
import datetime
import ast
import collections

__version__ = 'X.Y.Z'

# we do not use the nicer sys.version_info.major
# for compatibility with Python < 2.7
if sys.version_info[0] > 2:
    from io import StringIO
    import urllib.request

    class URLopener(urllib.request.FancyURLopener):
        def http_error_default(self, url, fp, errcode, errmsg, headers):
            sys.stderr.write("ERROR: could not fetch {0}\n".format(url))
            sys.exit(-1)
else:
    from StringIO import StringIO
    import urllib

    class URLopener(urllib.FancyURLopener):
        def http_error_default(self, url, fp, errcode, errmsg, headers):
            sys.stderr.write("ERROR: could not fetch {0}\n".format(url))
            sys.exit(-1)


AUTOCMAKE_GITHUB_URL = 'https://github.com/coderefinery/autocmake/raw/yaml/'

# ------------------------------------------------------------------------------


def replace(s, d):
    from re import findall
    if isinstance(s, str):
        for var in findall(r"%\(([A-Za-z0-9_]*)\)", s):
            s = s.replace("%({})".format(var), str(d[var]))
    return s


def test_replace():
    assert replace('hey %(foo) ho %(bar)',
                   {'foo': 'hey', 'bar': 'ho'}) == 'hey hey ho ho'

# ------------------------------------------------------------------------------


def interpolate(d, d_map):
    from collections import Mapping, Iterable
    for k, v in d.items():
        if isinstance(v, Mapping):
            d[k] = interpolate(d[k], d_map)
        elif isinstance(v, Iterable) and not isinstance(v, str):
            l = []
            for x in v:
                if isinstance(x, Mapping):
                    l.append(interpolate(x, d_map))
                else:
                    l.append(replace(x, d_map))
            d[k] = l.copy()
        else:
            d[k] = replace(d[k], d_map)
    return d


def test_interpolate():
    d = {'foo': 'hey',
         'bar': 'ho',
         'one': 'hey %(foo) ho %(bar)',
         'two': {'one': 'hey %(foo) ho %(bar)',
                 'two': 'raboof'}}
    d_interpolated = {'foo': 'hey',
                      'bar': 'ho',
                      'one': 'hey hey ho ho',
                      'two': {'one': 'hey hey ho ho',
                              'two': 'raboof'}}
    assert interpolate(d, d) == d_interpolated
    d2 = {'modules': [{'fc': [{'source': '%(url_root)fc_optional.cmake'}]}], 'url_root': 'downloaded/downloaded_'}
    d2_interpolated = {'modules': [{'fc': [{'source': 'downloaded/downloaded_fc_optional.cmake'}]}], 'url_root': 'downloaded/downloaded_'}
    assert interpolate(d2, d2) == d2_interpolated


# ------------------------------------------------------------------------------


def fetch_url(src, dst):
    """
    Fetch file from URL src and save it to dst.
    """
    dirname = os.path.dirname(dst)
    if dirname != '':
        if not os.path.isdir(dirname):
            os.makedirs(dirname)

    opener = URLopener()
    opener.retrieve(src, dst)

# ------------------------------------------------------------------------------


def parse_yaml(stream, override={}):
    import yaml

    try:
        config = yaml.load(stream, yaml.SafeLoader)
    except yaml.YAMLError as exc:
        print(exc)
        sys.exit(-1)

    for k in config:
        if k in override:
            config[k] = override[k]

    config = interpolate(config, config)
    return config

# ------------------------------------------------------------------------------


def print_progress_bar(text, done, total, width):
    """
    Print progress bar.
    """
    n = int(float(width) * float(done) / float(total))
    sys.stdout.write("\r{0} [{1}{2}] ({3}/{4})".format(text, '#' * n, ' ' * (width - n), done, total))
    sys.stdout.flush()

# ------------------------------------------------------------------------------


def align_options(options):
    """
    Indents flags and aligns help texts.
    """
    l = 0
    for opt in options:
        if len(opt[0]) > l:
            l = len(opt[0])
    s = []
    for opt in options:
        s.append('  {0}{1}  {2}'.format(opt[0], ' ' * (l - len(opt[0])), opt[1]))
    return '\n'.join(s)

# ------------------------------------------------------------------------------


def gen_cmake_command(config):
    """
    Generate CMake command.
    """
    s = []

    s.append("\n\ndef gen_cmake_command(options, arguments):")
    s.append('    """')
    s.append("    Generate CMake command based on options and arguments.")
    s.append('    """')
    s.append("    command = []")

    for env in extract_list(config, 'export'):
        s.append('    command.append({0})'.format(env))

    s.append("    command.append(arguments['--cmake-executable'])")

    for definition in extract_list(config, 'define'):
        s.append('    command.append({0})'.format(definition))

    s.append("    command.append('-DCMAKE_BUILD_TYPE={0}'.format(arguments['--type']))")
    s.append("    command.append('-G \"{0}\"'.format(arguments['--generator']))")
    s.append("    if arguments['--cmake-options'] != \"''\":")
    s.append("        command.append(arguments['--cmake-options'])")
    s.append("    if arguments['--prefix']:")
    s.append("        command.append('-DCMAKE_INSTALL_PREFIX=\"{0}\"'.format(arguments['--prefix']))")

    s.append("\n    return ' '.join(command)")

    return '\n'.join(s)

# ------------------------------------------------------------------------------


def autogenerated_notice():
    current_year = datetime.date.today().year
    year_range = '2015-{0}'.format(current_year)
    s = []
    s.append('# This file is autogenerated by Autocmake v{0} http://autocmake.org'.format(__version__))
    s.append('# Copyright (c) {0} by Radovan Bast, Jonas Juselius, and contributors.'.format(year_range))
    return '\n'.join(s)

# ------------------------------------------------------------------------------


def gen_setup(config, relative_path, setup_script_name):
    """
    Generate setup script.
    """
    s = []
    s.append('#!/usr/bin/env python')
    s.append('\n{0}'.format(autogenerated_notice()))
    s.append('\nimport os')
    s.append('import sys')

    s.append("\nsys.path.insert(0, '{0}')".format(relative_path))

    s.append('from autocmake import configure')
    s.append('from autocmake.external import docopt')

    s.append('\n\noptions = """')
    s.append('Usage:')
    s.append('  ./{0} [options] [<builddir>]'.format(setup_script_name))
    s.append('  ./{0} (-h | --help)'.format(setup_script_name))
    s.append('\nOptions:')

    options = []

    for opt in extract_list(config, 'docopt'):
        first = opt.split()[0].strip()
        rest = ' '.join(opt.split()[1:]).strip()
        options.append([first, rest])

    options.append(['--type=<TYPE>', 'Set the CMake build type (debug, release, or relwithdeb) [default: release].'])
    options.append(['--generator=<STRING>', 'Set the CMake build system generator [default: Unix Makefiles].'])
    options.append(['--show', 'Show CMake command and exit.'])
    options.append(['--cmake-executable=<CMAKE_EXECUTABLE>', 'Set the CMake executable [default: cmake].'])
    options.append(['--cmake-options=<STRING>', "Define options to CMake [default: '']."])
    options.append(['--prefix=<PATH>', 'Set the install path for make install.'])
    options.append(['<builddir>', 'Build directory.'])
    options.append(['-h --help', 'Show this screen.'])

    s.append(align_options(options))

    s.append('"""')

    s.append(gen_cmake_command(config))

    s.append("\n")
    s.append("# parse command line args")
    s.append("try:")
    s.append("    arguments = docopt.docopt(options, argv=None)")
    s.append("except docopt.DocoptExit:")
    s.append(r"    sys.stderr.write('ERROR: bad input to {0}\n'.format(sys.argv[0]))")
    s.append("    sys.stderr.write(options)")
    s.append("    sys.exit(-1)")
    s.append("\n")
    s.append("# use extensions to validate/post-process args")
    s.append("if configure.module_exists('extensions'):")
    s.append("    import extensions")
    s.append("    arguments = extensions.postprocess_args(sys.argv, arguments)")
    s.append("\n")
    s.append("root_directory = os.path.dirname(os.path.realpath(__file__))")
    s.append("\n")
    s.append("build_path = arguments['<builddir>']")
    s.append("\n")
    s.append("# create cmake command")
    s.append("cmake_command = '{0} {1}'.format(gen_cmake_command(options, arguments), root_directory)")
    s.append("\n")
    s.append("# run cmake")
    s.append("configure.configure(root_directory, build_path, cmake_command, arguments['--show'])")

    return s

# ------------------------------------------------------------------------------


def gen_cmakelists(project_name, min_cmake_version, relative_path, modules):
    """
    Generate CMakeLists.txt.
    """
    s = []

    s.append(autogenerated_notice())

    s.append('\n# set minimum cmake version')
    s.append('cmake_minimum_required(VERSION {0} FATAL_ERROR)'.format(min_cmake_version))

    s.append('\n# project name')
    s.append('project({0})'.format(project_name))

    s.append('\n# do not rebuild if rules (compiler flags) change')
    s.append('set(CMAKE_SKIP_RULE_DEPENDENCY TRUE)')

    s.append('\n# if CMAKE_BUILD_TYPE undefined, we set it to Debug')
    s.append('if(NOT CMAKE_BUILD_TYPE)')
    s.append('    set(CMAKE_BUILD_TYPE "Debug")')
    s.append('endif()')

    if len(modules) > 0:
        s.append('\n# directories which hold included cmake modules')

    module_paths = [module.path for module in modules]
    module_paths.append('downloaded')  # this is done to be able to find fetched modules when testing
    module_paths = list(set(module_paths))
    module_paths.sort()  # we do this to always get the same order and to minimize diffs
    for directory in module_paths:
        rel_cmake_module_path = os.path.join(relative_path, directory)
        # on windows cmake corrects this so we have to make it wrong again
        rel_cmake_module_path = rel_cmake_module_path.replace('\\', '/')
        s.append('set(CMAKE_MODULE_PATH ${{CMAKE_MODULE_PATH}} ${{PROJECT_SOURCE_DIR}}/{0})'.format(rel_cmake_module_path))

    if len(modules) > 0:
        s.append('\n# included cmake modules')
    for module in modules:
        s.append('include({0})'.format(os.path.splitext(module.name)[0]))

    return s

# ------------------------------------------------------------------------------


def prepend_or_set(config, section, option, value, defaults):
    """
    If option is already set, then value is prepended.
    If option is not set, then it is created and set to value.
    This is used to prepend options with values which come from the module documentation.
    """
    if value:
        if config.has_option(section, option):
            value += '\n{0}'.format(config.get(section, option, 0, defaults))
        config.set(section, option, value)
    return config

# ------------------------------------------------------------------------------


def extract_list(config, section):
    from collections import Iterable
    l = []
    if 'modules' in config:
        for module in config['modules']:
            for k, v in module.items():
                for x in v:
                    if section in x:
                        if isinstance(x[section], Iterable) and not isinstance(x[section], str):
                            for y in x[section]:
                                l.append(y)
                        else:
                            l.append(x[section])
    return l

# ------------------------------------------------------------------------------


def fetch_modules(config, relative_path):
    """
    Assemble modules which will
    be included in CMakeLists.txt.
    """
    from collections import Iterable

    download_directory = 'downloaded'
    if not os.path.exists(download_directory):
        os.makedirs(download_directory)

    # here we get the list of sources to fetch
    sources = extract_list(config, 'source')

    modules = []
    Module = collections.namedtuple('Module', 'path name')

    warnings = []

    if len(sources) > 0:  # otherwise division by zero in print_progress_bar
        print_progress_bar(text='- assembling modules:', done=0, total=len(sources), width=30)
        for i, src in enumerate(sources):
            module_name = os.path.basename(src)
            if 'http' in src:
                path = download_directory
                name = 'autocmake_{0}'.format(module_name)
                dst = os.path.join(download_directory, 'autocmake_{0}'.format(module_name))
                fetch_url(src, dst)
                file_name = dst
                fetch_dst_directory = download_directory
            else:
                if os.path.exists(src):
                    path = os.path.dirname(src)
                    name = module_name
                    file_name = src
                    fetch_dst_directory = path
                else:
                    sys.stderr.write("ERROR: {0} does not exist\n".format(src))
                    sys.exit(-1)

            # FIXME
          # if config.has_option(section, 'override'):
          #     defaults = ast.literal_eval(config.get(section, 'override'))
          # else:
          #     defaults = {}

            # FIXME
            # we infer config from the module documentation
          # with open(file_name, 'r') as f:
          #     parsed_config = parse_cmake_module(f.read(), defaults)
          #     if parsed_config['warning']:
          #         warnings.append('WARNING from {0}: {1}'.format(module_name, parsed_config['warning']))
          #     config = prepend_or_set(config, section, 'docopt', parsed_config['docopt'], defaults)
          #     config = prepend_or_set(config, section, 'define', parsed_config['define'], defaults)
          #     config = prepend_or_set(config, section, 'export', parsed_config['export'], defaults)
          #     if parsed_config['fetch']:
          #         for src in parsed_config['fetch'].split('\n'):
          #             dst = os.path.join(fetch_dst_directory, os.path.basename(src))
          #             fetch_url(src, dst)

            modules.append(Module(path=path, name=name))
            print_progress_bar(
                text='- assembling modules:',
                done=(i + 1),
                total=len(sources),
                width=30
            )
            # FIXME
          # if config.has_option(section, 'fetch'):
          #     # when we fetch directly from autocmake.yml
          #     # we download into downloaded/
          #     for src in config.get(section, 'fetch').split('\n'):
          #         dst = os.path.join(download_directory, os.path.basename(src))
          #         fetch_url(src, dst)
        print('')

    if warnings != []:
        print('- {0}'.format('\n- '.join(warnings)))

    return modules

# ------------------------------------------------------------------------------


def main(argv):
    """
    Main function.
    """
    if len(argv) != 2:
        sys.stderr.write("\nYou can update a project in two steps.\n\n")
        sys.stderr.write("Step 1: Update or create infrastructure files\n")
        sys.stderr.write("        which will be needed to configure and build the project:\n")
        sys.stderr.write("        $ {0} --self\n\n".format(argv[0]))
        sys.stderr.write("Step 2: Create CMakeLists.txt and setup script in PROJECT_ROOT:\n")
        sys.stderr.write("        $ {0} <PROJECT_ROOT>\n".format(argv[0]))
        sys.stderr.write("        example:\n")
        sys.stderr.write("        $ {0} ..\n".format(argv[0]))
        sys.exit(-1)

    if argv[1] in ['-h', '--help']:
        print('Usage:')
        print('  python update.py --self         Update this script and fetch or update infrastructure files under autocmake/.')
        print('  python update.py <builddir>     (Re)generate CMakeLists.txt and setup script and fetch or update CMake modules.')
        print('  python update.py (-h | --help)  Show this help text.')
        sys.exit(0)

    if argv[1] == '--self':
        # update self
        if not os.path.isfile('autocmake.yml'):
            print('- fetching example autocmake.yml')
            fetch_url(
                src='{0}example/autocmake.yml'.format(AUTOCMAKE_GITHUB_URL),
                dst='autocmake.yml'
            )
        if not os.path.isfile('.gitignore'):
            print('- creating .gitignore')
            with open('.gitignore', 'w') as f:
                f.write('*.pyc\n')
        for f in ['autocmake/configure.py',
                  'autocmake/external/docopt.py',
                  'autocmake/__init__.py',
                  'update.py']:
            print('- fetching {0}'.format(f))
            fetch_url(
                src='{0}{1}'.format(AUTOCMAKE_GITHUB_URL, f),
                dst='{0}'.format(f)
            )
        sys.exit(0)

    project_root = argv[1]
    if not os.path.isdir(project_root):
        sys.stderr.write("ERROR: {0} is not a directory\n".format(project_root))
        sys.exit(-1)

    # read config file
    print('- parsing autocmake.yml')
    with open('autocmake.yml', 'r') as stream:
        config = parse_yaml(stream)

    if 'name' in config:
        project_name = config['name']
    else:
        sys.stderr.write("ERROR: you have to specify the project name in autocmake.yml\n")
        sys.exit(-1)
    if ' ' in project_name.rstrip():
        sys.stderr.write("ERROR: project name contains a space\n")
        sys.exit(-1)

    if 'min_cmake_version' in config:
        min_cmake_version = config['min_cmake_version']
    else:
        sys.stderr.write("ERROR: you have to specify min_cmake_version in autocmake.yml\n")
        sys.exit(-1)

    if 'setup_script' in config:
        setup_script_name = config['setup_script']
    else:
        setup_script_name = 'setup'

    # get relative path from setup script to this directory
    relative_path = os.path.relpath(os.path.abspath('.'), project_root)

    # fetch modules from the web or from relative paths
    modules = fetch_modules(config, relative_path)

    # create CMakeLists.txt
    print('- generating CMakeLists.txt')
    s = gen_cmakelists(project_name, min_cmake_version, relative_path, modules)
    with open(os.path.join(project_root, 'CMakeLists.txt'), 'w') as f:
        f.write('{0}\n'.format('\n'.join(s)))

    # create setup script
    print('- generating setup script')
    s = gen_setup(config, relative_path, setup_script_name)
    file_path = os.path.join(project_root, setup_script_name)
    with open(file_path, 'w') as f:
        f.write('{0}\n'.format('\n'.join(s)))
    if sys.platform != 'win32':
        make_executable(file_path)

# ------------------------------------------------------------------------------


# http://stackoverflow.com/a/30463972
def make_executable(path):
    mode = os.stat(path).st_mode
    mode |= (mode & 0o444) >> 2    # copy R bits to X
    os.chmod(path, mode)

# ------------------------------------------------------------------------------


def parse_cmake_module(s_in, override={}):
    from collections import Mapping, Iterable

    parsed_config = collections.defaultdict(lambda: None)

    if 'autocmake.yml configuration::' not in s_in:
        return parsed_config

    s_out = []
    is_rst_line = False
    for line in s_in.split('\n'):
        if is_rst_line:
            if len(line) > 0:
                if line[0] != '#':
                    is_rst_line = False
            else:
                is_rst_line = False
        if is_rst_line:
            s_out.append(line[2:])
        if '#.rst:' in line:
            is_rst_line = True

    autocmake_entry = '\n'.join(s_out).split('autocmake.yml configuration::')[1]
    autocmake_entry = autocmake_entry.replace('\n  ', '\n')

    buf = StringIO(autocmake_entry)
    config = parse_yaml(buf, override)

    for k, v in config.items():
        if isinstance(v, Iterable) and not isinstance(v, str):
            parsed_config[k] = [x for x in config[k]]
        else:
            parsed_config[k] = [config[k]]

    return parsed_config

# ------------------------------------------------------------------------------


def test_parse_cmake_module():

    s = r'''#.rst:
#
# Foo ...
#
# autocmake.yml configuration::
#
#   docopt:
#     - "--cxx=<CXX> C++ compiler [default: g++]."
#     - "--extra-cxx-flags=<EXTRA_CXXFLAGS> Extra C++ compiler flags [default: '']."
#   export: "'CXX={0}'.format(arguments['--cxx'])"
#   define: "'-DEXTRA_CXXFLAGS=\"{0}\"'.format(arguments['--extra-cxx-flags'])"

enable_language(CXX)

if(NOT DEFINED CMAKE_C_COMPILER_ID)
    message(FATAL_ERROR "CMAKE_C_COMPILER_ID variable is not defined!")
endif()'''

    parsed_config = parse_cmake_module(s)
    assert parsed_config['docopt'] == ["--cxx=<CXX> C++ compiler [default: g++].", "--extra-cxx-flags=<EXTRA_CXXFLAGS> Extra C++ compiler flags [default: '']."]


def test_parse_cmake_module_no_key():

    s = '''#.rst:
#
# Foo ...
#
# Bar ...

enable_language(CXX)

if(NOT DEFINED CMAKE_C_COMPILER_ID)
    message(FATAL_ERROR "CMAKE_C_COMPILER_ID variable is not defined!")
endif()'''

    parsed_config = parse_cmake_module(s)
    assert parsed_config['docopt'] is None


def test_parse_cmake_module_interpolate():

    s = r'''#.rst:
#
# Foo ...
#
# autocmake.yml configuration::
#
#   major: 1
#   minor: 2
#   patch: 3
#   a: v%(major)
#   b: v%(minor)
#   c: v%(patch)

enable_language(CXX)'''

    parsed_config = parse_cmake_module(s)
    assert parsed_config['a'] == ['v1']
    assert parsed_config['b'] == ['v2']
    assert parsed_config['c'] == ['v3']


def test_parse_cmake_module_override():

    s = r'''#.rst:
#
# Foo ...
#
# autocmake.yml configuration::
#
#   major: 1
#   minor: 2
#   patch: 3
#   a: v%(major)
#   b: v%(minor)
#   c: v%(patch)

enable_language(CXX)'''

    d = {'minor': 4}
    parsed_config = parse_cmake_module(s, d)
    assert parsed_config['a'] == ['v1']
    assert parsed_config['b'] == ['v4']
    assert parsed_config['c'] == ['v3']

# ------------------------------------------------------------------------------


if __name__ == '__main__':
    main(sys.argv)
