if(NOT DEFINED ENV{FCFLAGS})
    if(CMAKE_Fortran_COMPILER_ID MATCHES GNU)
        set(CMAKE_Fortran_FLAGS "${CMAKE_Fortran_FLAGS} -Wall -Wextra")
        set(CMAKE_Fortran_FLAGS_RELEASE "-O3 -funroll-all-loops")
        set(CMAKE_Fortran_FLAGS_DEBUG "-O0 -g -fbacktrace")
    endif()
endif()
