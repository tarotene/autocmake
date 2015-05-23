#!/usr/bin/env python

import os
import sys
import urllib
import shutil
import tempfile
from collections import OrderedDict
from ConfigParser import ConfigParser


AUTOCMAKE_GITHUB_URL = 'https://github.com/scisoft/autocmake'


class URLopener(urllib.FancyURLopener):
    def http_error_default(self, url, fp, errcode, errmsg, headers):
        sys.stderr.write("ERROR: could not fetch %s\n" % url)
        sys.exit(-1)


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


def print_progress_bar(text, done, total, width):
    """
    Print progress bar.
    """
    n = int(float(width)*float(done)/float(total))
    sys.stdout.write("\r%s [%s%s] (%i/%i)" % (text, '#'*n,
                                              ' '*(width-n), done, total))
    sys.stdout.flush()


def align_options(options):
    """
    Indendts flags and aligns help texts.
    """
    l = 0
    for opt in options:
        if len(opt[0]) > l:
            l = len(opt[0])
    s = []
    for opt in options:
        s.append('  %s%s  %s' % (opt[0], ' '*(l - len(opt[0])), opt[1]))
    return '\n'.join(s)


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

    # take care of environment variables
    for section in config.sections():
        if config.has_option(section, 'export'):
            for env in config.get(section, 'export').split('\n'):
                s.append('    command.append(%s)' % env)

    s.append("    command.append('cmake')")

    # take care of cmake definitions
    for section in config.sections():
        if config.has_option(section, 'define'):
            for definition in config.get(section, 'define').split('\n'):
                s.append('    command.append(%s)' % definition)

    s.append("\n    return ' '.join(command)")

    return '\n'.join(s)


def gen_setup(config, relative_path):
    """
    Generate setup.py script.
    """
    s = []
    s.append('#!/usr/bin/env python')
    s.append('\nimport os')
    s.append('import sys')

    s.append("\nsys.path.append('%s')" % os.path.join(relative_path, 'lib'))
    s.append('from config import configure')
    s.append('from docopt import docopt')

    s.append('\n\noptions = """')
    s.append('Usage:')
    s.append('  ./setup.py [options] [<builddir>]')
    s.append('  ./setup.py (-h | --help)')
    s.append('\nOptions:')

    options = []
    for section in config.sections():
        if config.has_option(section, 'docopt'):
            for opt in config.get(section, 'docopt').split('\n'):
                first = opt.split()[0].strip()
                rest = ' '.join(opt.split()[1:]).strip()
                options.append([first, rest])

    options.append(['--show', 'Show CMake command and exit.'])
    options.append(['<builddir>', 'Build directory.'])
    options.append(['-h --help', 'Show this screen.'])

    s.append(align_options(options))

    s.append('"""')

    s.append(gen_cmake_command(config))

    s.append("\n\narguments = docopt(options, argv=None)")
    s.append("\nroot_directory = os.path.dirname(os.path.realpath(__file__))")
    s.append("build_path = arguments['<builddir>']")
    s.append("cmake_command = '%s %s' % (gen_cmake_command(options, arguments), root_directory)")
    s.append("configure(root_directory, build_path, cmake_command, arguments['--show'])")

    return s


def gen_cmakelists(config, relative_path, list_of_modules):
    """
    Generate CMakeLists.txt.
    """
    if not config.has_option('project', 'name'):
        sys.stderr.write("ERROR: you have to specify the project name\n")
        sys.stderr.write("       in autocmake.cfg under [project]\n")
        sys.exit(-1)
    project_name = config.get('project', 'name')

    s = []

    s.append('# set minimum cmake version')
    s.append('cmake_minimum_required(VERSION 2.8 FATAL_ERROR)')

    s.append('\n')
    s.append('project(%s)' % project_name)

    s.append('\n')
    s.append('# do not rebuild if rules (compiler flags) change')
    s.append('set(CMAKE_SKIP_RULE_DEPENDENCY TRUE)')

    s.append('\n')
    s.append('# directory which holds enabled cmake modules')
    s.append('set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH}')
    s.append('    ${PROJECT_SOURCE_DIR}/%s)' % os.path.join(relative_path, 'modules'))

    s.append('\n')
    s.append('# guards against in-source builds and bad build types')
    s.append('if(NOT CMAKE_BUILD_TYPE)')
    s.append('    set(CMAKE_BUILD_TYPE "Debug")')
    s.append('endif()')

    s.append('\n')
    s.append('# python interpreter is required at many')
    s.append('# places during configuration and build')
    s.append('find_package(PythonInterp REQUIRED)')

    s.append('\n')
    s.append('# determine program version from file, example: "14.1"')
    s.append('# the reason why this information is stored')
    s.append('# in a file and not as cmake variable')
    s.append('# is that cmake-unaware programs can')
    s.append('# parse and use it (e.g. Sphinx)')
    s.append('if(EXISTS "${PROJECT_SOURCE_DIR}/VERSION")')
    s.append('    file(READ "${PROJECT_SOURCE_DIR}/VERSION" PROGRAM_VERSION)')
    s.append('    string(STRIP "${PROGRAM_VERSION}" PROGRAM_VERSION)')
    s.append('endif()')

    s.append('\n')
    s.append('# generated cmake files will be written to this path')
    s.append('# only build info is generated')
    s.append('# everything else is static for the user')
    s.append('file(MAKE_DIRECTORY ${PROJECT_BINARY_DIR}/generated_by_cmake)')
    s.append('set(CMAKE_MODULE_PATH')
    s.append('    ${CMAKE_MODULE_PATH}')
    s.append('    ${PROJECT_BINARY_DIR}/generated_by_cmake')
    s.append('    )')

    s.append('\n')
    s.append('# included cmake modules')
    for m in list_of_modules:
        s.append('include(%s)' % os.path.splitext(m)[0])

    return s


def fetch_modules(config, module_directory):
    """
    Fetch modules either from remote URLs or from relative paths
    and save them to module_directory from which they will
    be included in CMakeLists.txt.
    """
    if not os.path.exists(module_directory):
        os.makedirs(module_directory)

    n = len(filter(lambda x: config.has_option(x, 'source'),
                   config.sections()))

    i = 0
    print_progress_bar(text='- fetching modules:', done=0, total=n, width=30)
    list_of_modules = []
    for section in config.sections():
        if config.has_option(section, 'source'):
            for src in config.get(section, 'source').split('\n'):
                module_name = os.path.basename(src)
                list_of_modules.append(module_name)
                dst = os.path.join(module_directory, module_name)
                if 'http' in src:
                    fetch_url(src, dst)
                else:
                    if os.path.exists(src):
                        shutil.copyfile(src, dst)
                    else:
                        sys.stderr.write("ERROR: %s does not exist\n" % src)
                        sys.exit(-1)
            i += 1
            print_progress_bar(
                text='- fetching modules:',
                done=i,
                total=n,
                width=30
            )
    print('')
    return list_of_modules


def main(argv):
    """
    Main function.
    """
    if len(argv) != 2:
        sys.stderr.write("\nYou can bootstrap a project in two steps.\n")
        sys.stderr.write("First step is typically done only once.\n")
        sys.stderr.write("Second step can be repeated many time without re-running the first step.\n\n")
        sys.stderr.write("Step 1:\n")
        sys.stderr.write("Create an example autocmake.cfg and other infrastructure files\n")
        sys.stderr.write("which will be needed to configure and build the project:\n")
        sys.stderr.write("$ %s --init\n\n" % argv[0])
        sys.stderr.write("Step 2:\n")
        sys.stderr.write("Create CMakeLists.txt and setup.py in PROJECT_ROOT:\n")
        sys.stderr.write("$ %s PROJECT_ROOT\n" % argv[0])
        sys.stderr.write("example:\n")
        sys.stderr.write("$ %s ..\n" % argv[0])
        sys.exit(-1)

    if argv[1] == '--init':
        # empty project, create infrastructure files
        if not os.path.isfile('autocmake.cfg'):
            print('- fetching example autocmake.cfg')
            fetch_url(
                src='%s/raw/master/example/autocmake.cfg' % AUTOCMAKE_GITHUB_URL,
                dst='autocmake.cfg'
            )
        print('- fetching lib/config.py')
        fetch_url(
            src='%s/raw/master/lib/config.py' % AUTOCMAKE_GITHUB_URL,
            dst='lib/config.py'
        )
        print('- fetching lib/docopt.py')
        fetch_url(
            src='https://github.com/docopt/docopt/raw/master/docopt.py',
            dst='lib/docopt.py'
        )
        sys.exit(0)

    project_root = argv[1]
    if not os.path.isdir(project_root):
        sys.stderr.write("ERROR: %s is not a directory\n" % project_root)
        sys.exit(-1)

    # read config file
    print('- parsing autocmake.cfg')
    config = ConfigParser(dict_type=OrderedDict)
    config.read('autocmake.cfg')

    # fetch modules from the web or from relative paths
    list_of_modules = fetch_modules(config, module_directory='modules')

    # get relative path from setup.py script to this directory
    relative_path = os.path.relpath(os.path.abspath('.'), project_root)

    # create CMakeLists.txt
    print('- generating CMakeLists.txt')
    s = gen_cmakelists(config, relative_path, list_of_modules)
    with open(os.path.join(project_root, 'CMakeLists.txt'), 'w') as f:
        f.write('%s\n' % '\n'.join(s))

    # create setup.py
    print('- generating setup.py')
    s = gen_setup(config, relative_path)
    with open(os.path.join(project_root, 'setup.py'), 'w') as f:
        f.write('%s\n' % '\n'.join(s))


if __name__ == '__main__':
    main(sys.argv)
