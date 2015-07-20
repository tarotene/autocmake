#.rst:
#
# Adds optional Fortran support.
# Appends EXTRA_FCFLAGS to CMAKE_Fortran_FLAGS.
# If environment variable FCFLAGS is set, then the FCFLAGS are used
# and no other flags are used or appended.
#
# Variables used::
#
#   EXTRA_FCFLAGS
#   ENABLE_FC_SUPPORT
#
# Variables defined::
#
#   CMAKE_Fortran_MODULE_DIRECTORY (${PROJECT_BINARY_DIR}/include/fortran)
#
# Variables modified::
#
#   CMAKE_Fortran_FLAGS
#
# Variables set::
#
#   ENABLE_FC_SUPPORT
#
# Environment variables used::
#
#   FCFLAGS
#
# Example autocmake.cfg entry::
#
#   [fc]
#   source: https://github.com/scisoft/autocmake/raw/master/modules/fc.cmake
#   docopt: --fc=<FC> Fortran compiler [default: gfortran].
#           --extra-fc-flags=<EXTRA_FCFLAGS> Extra Fortran compiler flags [default: ''].
#           --fc-support=<FC_SUPPORT> Toggle Fortran language support (ON/OFF) [default: ON].
#   export: 'FC=%s' % arguments['--fc']
#   define: '-DEXTRA_FCFLAGS="%s"' % arguments['--extra-fc-flags']
#           '-DENABLE_FC_SUPPORT="%s"' % arguments['--fc-support']

option(ENABLE_FC_SUPPORT "Enable Fortran language support" ON)

if(ENABLE_FC_SUPPORT)
    enable_language(Fortran)

    set(CMAKE_Fortran_MODULE_DIRECTORY ${PROJECT_BINARY_DIR}/include/fortran)

    if(NOT DEFINED CMAKE_Fortran_COMPILER_ID)
        message(FATAL_ERROR "CMAKE_Fortran_COMPILER_ID variable is not defined!")
    endif()

    if(NOT CMAKE_Fortran_COMPILER_WORKS)
        message(FATAL_ERROR "CMAKE_Fortran_COMPILER_WORKS is false!")
    endif()

    if(DEFINED EXTRA_FCFLAGS)
        set(CMAKE_Fortran_FLAGS "${CMAKE_Fortran_FLAGS} ${EXTRA_FCFLAGS}")
    endif()

    if(DEFINED ENV{FCFLAGS})
        message(STATUS "FCFLAGS is set to '$ENV{FCFLAGS}'.")
        set(CMAKE_Fortran_FLAGS "$ENV{FCFLAGS}")
    endif()
else()
    # workaround to avoid unused warning
    if(DEFINED EXTRA_FCFLAGS)
        set(_unused ${EXTRA_FCFLAGS})
        unset(_unused)
    endif()
endif()
