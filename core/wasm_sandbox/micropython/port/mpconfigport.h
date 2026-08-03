#pragma once

#include <alloca.h>
#include <stdint.h>

// A compact but normal Python language surface.  Operating-system modules are
// intentionally not compiled; player imports are served by the read-only VFS.
#define MICROPY_CONFIG_ROM_LEVEL (MICROPY_CONFIG_ROM_LEVEL_EXTRA_FEATURES)
#define MICROPY_ENABLE_COMPILER (1)
#define MICROPY_ENABLE_EXTERNAL_IMPORT (1)
#define MICROPY_ENABLE_GC (1)
#define MICROPY_ENABLE_PYSTACK (1)
#define MICROPY_ENABLE_VM_ABORT (1)
#define MICROPY_STACK_CHECK (1)
#define MICROPY_FULL_CHECKS (1)
#define MICROPY_FLOAT_IMPL (MICROPY_FLOAT_IMPL_DOUBLE)
#define MICROPY_LONGINT_IMPL (MICROPY_LONGINT_IMPL_MPZ)
#define MICROPY_PY_HEAPQ (1)
#define MICROPY_PY_RANDOM (1)
#define MICROPY_PY_RANDOM_EXTRA_FUNCS (1)
#define MICROPY_PY_OS (0)
#define MICROPY_PY_IO (0)
#define MICROPY_PY_GC (0)
#define MICROPY_PY_SYS_STDFILES (0)
#define MICROPY_PY_SYS_ATEXIT (0)
#define MICROPY_PY_SYS_SETTRACE (0)
#define MICROPY_PY_SYS_GETSIZEOF (0)
#define MICROPY_PY_SYS_EXC_INFO (0)
#define MICROPY_PY_BUILTINS_OPEN (0)
#define MICROPY_PY_BUILTINS_EXECFILE (0)
#define MICROPY_PY_BUILTINS_COMPILE (0)
#define MICROPY_PY_BUILTINS_EXEC (0)
#define MICROPY_PY_BUILTINS_EVAL (0)
#define MICROPY_PY_BUILTINS_MEMORYVIEW (0)
#define MICROPY_PY_BUILTINS_BYTEARRAY (0)
#define MICROPY_PY_BUILTINS_BYTES (0)
#define MICROPY_PY_BUILTINS_HELP (0)
#define MICROPY_PY_MICROPYTHON (0)
#define MICROPY_PY_UCTYPES (0)
#define MICROPY_PY_FFI (0)
#define MICROPY_PY_BUILTINS_NOTIMPLEMENTED (0)
#define MICROPY_PY_BUILTINS_INPUT (0)

#define MICROPY_ALLOC_PATH_MAX (192)
#define MICROPY_ALLOC_PARSE_CHUNK_INIT (64)
#define MICROPY_QSTR_BYTES_IN_HASH (1)

typedef long mp_off_t;
#define MP_SSIZE_MAX INTPTR_MAX

#define MICROPY_HW_BOARD_NAME "cosmos-sandbox"
#define MICROPY_HW_MCU_NAME "wasm32"

void cosmos_vm_hook(void);
#define MICROPY_VM_HOOK_DISPATCH cosmos_vm_hook();

#define mp_builtin___import__ cosmos_builtin_import

#define MP_STATE_PORT MP_STATE_VM
