cmake_minimum_required(VERSION 3.16)
project(xrealAirHeadTracker C)

set(CMAKE_C_STANDARD 17)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# ---------------------------------------------------------------------------
# The nrealAirLinuxDriver submodule (left untouched). Found by searching this
# folder's parents, so this project can live anywhere inside the repo.
# ---------------------------------------------------------------------------
set(_default_driver "")
set(_dir "${CMAKE_CURRENT_SOURCE_DIR}")
foreach(_i RANGE 6)
  if(EXISTS "${_dir}/nrealAirLinuxDriver/interface_lib/CMakeLists.txt")
    set(_default_driver "${_dir}/nrealAirLinuxDriver")
    break()
  endif()
  get_filename_component(_dir "${_dir}" DIRECTORY)
endforeach()
set(XREAL_DRIVER_DIR "${_default_driver}" CACHE PATH "Path to the nrealAirLinuxDriver folder")

if(NOT EXISTS "${XREAL_DRIVER_DIR}/interface_lib/CMakeLists.txt")
  message(FATAL_ERROR
    "nrealAirLinuxDriver not found (or its own submodules are missing).\n"
    "Run from the top of your repo:  git submodule update --init --recursive\n"
    "or pass -DXREAL_DRIVER_DIR=/path/to/nrealAirLinuxDriver")
endif()
message(STATUS "Using nrealAirLinuxDriver from: ${XREAL_DRIVER_DIR}")

# Build only the driver's interface library, inside this project's build folder,
# so nothing is ever written into the submodule.
add_subdirectory("${XREAL_DRIVER_DIR}/interface_lib" "${CMAKE_CURRENT_BINARY_DIR}/xreal_interface_lib" EXCLUDE_FROM_ALL)

if(NOT XREAL_AIR_LIBRARY OR NOT XREAL_AIR_INCLUDE_DIR)
  message(FATAL_ERROR "The driver's interface_lib did not provide XREAL_AIR_LIBRARY / XREAL_AIR_INCLUDE_DIR.")
endif()

add_executable(xrealAirHeadTracker head_tracker.c)
target_include_directories(xrealAirHeadTracker BEFORE PRIVATE ${XREAL_AIR_INCLUDE_DIR})
target_link_libraries(xrealAirHeadTracker ${XREAL_AIR_LIBRARY})