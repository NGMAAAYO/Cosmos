#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "py/builtin.h"
#include "py/compile.h"
#include "py/cstack.h"
#include "py/gc.h"
#include "py/lexer.h"
#include "py/mperrno.h"
#include "py/mpstate.h"
#include "py/nlr.h"
#include "py/obj.h"
#include "py/objexcept.h"
#include "py/objint.h"
#include "py/objstr.h"
#include "py/pystack.h"
#include "py/runtime.h"
#include "py/stackctrl.h"

#define COSMOS_HEAP_BYTES (2 * 1024 * 1024)
#define COSMOS_PYSTACK_BYTES (256 * 1024)
#define COSMOS_INPUT_BYTES (512 * 1024)
#define COSMOS_MAX_FILES (96)
#define COSMOS_MAX_PATH (160)
#define COSMOS_ERROR_BYTES (64)
#define COSMOS_ERROR_MESSAGE_BYTES (256)

typedef struct {
    char name[COSMOS_MAX_PATH];
    uint32_t offset;
    uint32_t length;
} cosmos_file_t;

static uint8_t cosmos_heap[COSMOS_HEAP_BYTES];
static mp_obj_t cosmos_pystack[COSMOS_PYSTACK_BYTES / sizeof(mp_obj_t)];
static uint8_t cosmos_input[COSMOS_INPUT_BYTES];
static cosmos_file_t cosmos_files[COSMOS_MAX_FILES];
static uint32_t cosmos_file_count;
static int64_t cosmos_bytecodes_remaining;
static int32_t cosmos_budget_exhausted;
static int32_t cosmos_last_status;
static char cosmos_error_type[COSMOS_ERROR_BYTES];
static uint32_t cosmos_error_type_length;
static char cosmos_error_message[COSMOS_ERROR_MESSAGE_BYTES];
static uint32_t cosmos_error_message_length;
static uintptr_t cosmos_stack_top;

__attribute__((import_module("cosmos"), import_name("call")))
extern int64_t cosmos_host_call(int32_t opcode, int64_t a, int64_t b, int64_t c);

__attribute__((import_module("cosmos"), import_name("call_float")))
extern double cosmos_host_call_float(int32_t opcode, int64_t a, int64_t b, int64_t c);

static mp_obj_t cosmos_call(size_t n_args, const mp_obj_t *args) {
    int32_t opcode = (int32_t)mp_obj_get_int(args[0]);
    int64_t values[3] = {0, 0, 0};
    for (size_t index = 1; index < n_args; ++index) {
        mp_obj_int_to_bytes(args[index], sizeof(values[index - 1]),
            (byte *)&values[index - 1], false, true, true);
    }
    return mp_obj_new_int_from_ll(cosmos_host_call(opcode, values[0], values[1], values[2]));
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(cosmos_call_obj, 1, 4, cosmos_call);

static mp_obj_t cosmos_call_float(size_t n_args, const mp_obj_t *args) {
    int32_t opcode = (int32_t)mp_obj_get_int(args[0]);
    int64_t values[3] = {0, 0, 0};
    for (size_t index = 1; index < n_args; ++index) {
        mp_obj_int_to_bytes(args[index], sizeof(values[index - 1]),
            (byte *)&values[index - 1], false, true, true);
    }
    return mp_obj_new_float(cosmos_host_call_float(opcode, values[0], values[1], values[2]));
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(cosmos_call_float_obj, 1, 4, cosmos_call_float);

static const mp_rom_map_elem_t cosmos_module_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__cosmos)},
    {MP_ROM_QSTR(MP_QSTR_call), MP_ROM_PTR(&cosmos_call_obj)},
    {MP_ROM_QSTR(MP_QSTR_call_float), MP_ROM_PTR(&cosmos_call_float_obj)},
};
static MP_DEFINE_CONST_DICT(cosmos_module_globals, cosmos_module_globals_table);

const mp_obj_module_t cosmos_module = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&cosmos_module_globals,
};
MP_REGISTER_MODULE(MP_QSTR__cosmos, cosmos_module);

void cosmos_vm_hook(void) {
    if (cosmos_bytecodes_remaining <= 0) {
        cosmos_budget_exhausted = 1;
        nlr_jump_abort();
    }
    --cosmos_bytecodes_remaining;
}

mp_obj_t cosmos_builtin_import(size_t n_args, const mp_obj_t *args) {
    const char *name = mp_obj_str_get_str(args[0]);
    bool blocked_builtin = strcmp(name, "sys") == 0
        || strcmp(name, "os") == 0
        || strcmp(name, "gc") == 0
        || strcmp(name, "io") == 0
        || strcmp(name, "micropython") == 0
        || strcmp(name, "uctypes") == 0
        || strcmp(name, "ffi") == 0
        || strcmp(name, "threading") == 0
        || strcmp(name, "_thread") == 0
        || strcmp(name, "subprocess") == 0
        || strcmp(name, "socket") == 0
        || strcmp(name, "ctypes") == 0;
    bool allowed = name[0] == '\0'
        || strcmp(name, "__future__") == 0
        || strcmp(name, "_cosmos") == 0
        || strcmp(name, "math") == 0
        || strcmp(name, "heapq") == 0
        || strcmp(name, "random") == 0
        || strcmp(name, "dataclasses") == 0
        || strcmp(name, "types") == 0
        || strcmp(name, "core") == 0
        || strncmp(name, "core.", 5) == 0
        || strcmp(name, "src") == 0
        || strncmp(name, "src.", 4) == 0
        || (strchr(name, '.') == NULL && !blocked_builtin);
    if (!allowed) {
        mp_raise_msg_varg(
            &mp_type_ImportError,
            MP_ERROR_TEXT("module '%s' is not in the Cosmos whitelist"),
            name);
    }
    return mp_builtin___import___default(n_args, args);
}

static void cosmos_capture_error(void *value) {
    const char *name = cosmos_budget_exhausted || value == NULL
        ? "BudgetExceeded"
        : qstr_str(mp_obj_get_type(MP_OBJ_FROM_PTR(value))->name);
    cosmos_error_type_length = strlen(name);
    if (cosmos_error_type_length >= sizeof(cosmos_error_type)) {
        cosmos_error_type_length = sizeof(cosmos_error_type) - 1;
    }
    memcpy(cosmos_error_type, name, cosmos_error_type_length);
    cosmos_error_type[cosmos_error_type_length] = '\0';

    cosmos_error_message_length = 0;
    if (value != NULL && mp_obj_is_native_exception_instance(MP_OBJ_FROM_PTR(value))) {
        mp_obj_exception_t *exception = value;
        if (exception->args->len > 0 && mp_obj_is_exact_type(exception->args->items[0], &mp_type_str)) {
            mp_obj_str_t *message = MP_OBJ_TO_PTR(exception->args->items[0]);
            cosmos_error_message_length = message->len;
            if (cosmos_error_message_length >= sizeof(cosmos_error_message)) {
                cosmos_error_message_length = sizeof(cosmos_error_message) - 1;
            }
            memcpy(cosmos_error_message, message->data, cosmos_error_message_length);
            cosmos_error_message[cosmos_error_message_length] = '\0';
        }
    }
}

static const cosmos_file_t *cosmos_find_file(const char *name) {
    for (uint32_t index = 0; index < cosmos_file_count; ++index) {
        if (strcmp(cosmos_files[index].name, name) == 0) {
            return &cosmos_files[index];
        }
    }
    return NULL;
}

mp_lexer_t *mp_lexer_new_from_file(qstr filename) {
    const char *name = qstr_str(filename);
    const cosmos_file_t *file = cosmos_find_file(name);
    if (file == NULL) {
        mp_raise_OSError(MP_ENOENT);
    }
    return mp_lexer_new_from_str_len(filename, (const char *)&cosmos_input[file->offset], file->length, 0);
}

mp_import_stat_t mp_import_stat(const char *path) {
    if (cosmos_find_file(path) != NULL) {
        return MP_IMPORT_STAT_FILE;
    }
    size_t length = strlen(path);
    for (uint32_t index = 0; index < cosmos_file_count; ++index) {
        if (strncmp(cosmos_files[index].name, path, length) == 0 && cosmos_files[index].name[length] == '/') {
            return MP_IMPORT_STAT_DIR;
        }
    }
    return MP_IMPORT_STAT_NO_EXIST;
}

void gc_collect(void) {
    uintptr_t stack_pointer = (uintptr_t)&stack_pointer;
    gc_collect_start();
    if (cosmos_stack_top > stack_pointer) {
        gc_collect_root((void **)&stack_pointer, (cosmos_stack_top - stack_pointer) / sizeof(uintptr_t));
    }
    gc_collect_end();
}

void nlr_jump_fail(void *value) {
    __builtin_trap();
}

mp_uint_t mp_hal_stdout_tx_strn(const char *str, size_t len) {
    (void)str;
    return len;
}

void mp_hal_stdout_tx_strn_cooked(const char *str, size_t len) {
    (void)str;
    (void)len;
}

mp_uint_t mp_hal_ticks_ms(void) { return 0; }
mp_uint_t mp_hal_ticks_us(void) { return 0; }
mp_uint_t mp_hal_ticks_cpu(void) { return 0; }

__attribute__((export_name("cosmos_input_ptr")))
uint32_t cosmos_input_ptr(void) {
    return (uint32_t)(uintptr_t)cosmos_input;
}

__attribute__((export_name("cosmos_input_capacity")))
uint32_t cosmos_input_capacity(void) {
    return COSMOS_INPUT_BYTES;
}

__attribute__((export_name("cosmos_heap_ptr")))
uint32_t cosmos_heap_ptr(void) {
    return (uint32_t)(uintptr_t)cosmos_heap;
}

__attribute__((export_name("cosmos_heap_size")))
uint32_t cosmos_heap_size(void) {
    return sizeof(cosmos_heap);
}

__attribute__((export_name("cosmos_state_ptr")))
uint32_t cosmos_state_ptr(void) {
    return (uint32_t)(uintptr_t)&mp_state_ctx;
}

__attribute__((export_name("cosmos_state_size")))
uint32_t cosmos_state_size(void) {
    return sizeof(mp_state_ctx);
}

__attribute__((export_name("cosmos_init")))
int32_t cosmos_init(void) {
    uintptr_t stack_marker = (uintptr_t)&stack_marker;
    cosmos_stack_top = stack_marker;
    mp_cstack_init_with_sp_here(192 * 1024);
    cosmos_file_count = 0;
    cosmos_bytecodes_remaining = INT64_MAX;
    cosmos_budget_exhausted = 0;
    cosmos_last_status = 0;
    cosmos_error_type_length = 0;
    cosmos_error_message_length = 0;
    gc_init(cosmos_heap, cosmos_heap + sizeof(cosmos_heap));
    mp_pystack_init(cosmos_pystack, cosmos_pystack + MP_ARRAY_SIZE(cosmos_pystack));
    mp_init();
    return 0;
}

__attribute__((export_name("cosmos_add_file")))
int32_t cosmos_add_file(uint32_t name_offset, uint32_t name_length, uint32_t source_offset, uint32_t source_length) {
    if (cosmos_file_count >= COSMOS_MAX_FILES || name_length == 0 || name_length >= COSMOS_MAX_PATH) {
        return -1;
    }
    if (name_offset > COSMOS_INPUT_BYTES || name_length > COSMOS_INPUT_BYTES - name_offset) {
        return -1;
    }
    if (source_offset > COSMOS_INPUT_BYTES || source_length > COSMOS_INPUT_BYTES - source_offset) {
        return -1;
    }
    cosmos_file_t *file = &cosmos_files[cosmos_file_count++];
    memcpy(file->name, &cosmos_input[name_offset], name_length);
    file->name[name_length] = '\0';
    file->offset = source_offset;
    file->length = source_length;
    return 0;
}

static int32_t cosmos_execute(uint32_t source_offset, uint32_t source_length) {
    if (source_offset > COSMOS_INPUT_BYTES || source_length > COSMOS_INPUT_BYTES - source_offset) {
        return -1;
    }
    nlr_buf_t nlr;
    if (nlr_push(&nlr) == 0) {
        mp_lexer_t *lexer = mp_lexer_new_from_str_len(
            MP_QSTR__lt_stdin_gt_, (const char *)&cosmos_input[source_offset], source_length, 0);
        qstr source_name = lexer->source_name;
        mp_parse_tree_t parse_tree = mp_parse(lexer, MP_PARSE_FILE_INPUT);
        mp_obj_t function = mp_compile(&parse_tree, source_name, true);
        mp_call_function_0(function);
        nlr_pop();
        cosmos_last_status = 0;
        return 0;
    }
    cosmos_last_status = cosmos_budget_exhausted ? 1 : 2;
    cosmos_capture_error(nlr.ret_val);
    return cosmos_last_status;
}

__attribute__((export_name("cosmos_exec")))
int32_t cosmos_exec(uint32_t source_offset, uint32_t source_length) {
    cosmos_bytecodes_remaining = INT64_MAX;
    cosmos_budget_exhausted = 0;
    return cosmos_execute(source_offset, source_length);
}

static int32_t cosmos_call_global(const char *name, size_t n_args, const mp_obj_t *args, bool abortable) {
    nlr_buf_t nlr;
    if (nlr_push(&nlr) == 0) {
        if (abortable) {
            nlr_set_abort(&nlr);
        }
        mp_obj_t function = mp_load_global(qstr_from_str(name));
        mp_call_function_n_kw(function, n_args, 0, args);
        if (abortable) {
            nlr_set_abort(NULL);
        }
        nlr_pop();
        cosmos_last_status = 0;
        cosmos_error_type_length = 0;
        cosmos_error_message_length = 0;
        return 0;
    }
    if (abortable) {
        nlr_set_abort(NULL);
    }
    cosmos_last_status = cosmos_budget_exhausted ? 1 : 2;
    cosmos_capture_error(nlr.ret_val);
    return cosmos_last_status;
}

__attribute__((export_name("cosmos_create_player")))
int32_t cosmos_create_player(int64_t seed) {
    cosmos_bytecodes_remaining = INT64_MAX;
    cosmos_budget_exhausted = 0;
    mp_obj_t argument = mp_obj_new_int_from_ll(seed);
    return cosmos_call_global("__cosmos_create_player", 1, &argument, false);
}

__attribute__((export_name("cosmos_run")))
int32_t cosmos_run(int64_t bytecode_budget) {
    cosmos_bytecodes_remaining = bytecode_budget;
    cosmos_budget_exhausted = 0;
    return cosmos_call_global("__cosmos_turn", 0, NULL, true);
}

__attribute__((export_name("cosmos_budget_remaining")))
int64_t cosmos_budget_remaining(void) {
    return cosmos_bytecodes_remaining;
}

__attribute__((export_name("cosmos_error_type_ptr")))
uint32_t cosmos_error_type_ptr(void) {
    return (uint32_t)(uintptr_t)cosmos_error_type;
}

__attribute__((export_name("cosmos_error_type_length")))
uint32_t cosmos_error_type_length_get(void) {
    return cosmos_error_type_length;
}

__attribute__((export_name("cosmos_error_message_ptr")))
uint32_t cosmos_error_message_ptr(void) {
    return (uint32_t)(uintptr_t)cosmos_error_message;
}

__attribute__((export_name("cosmos_error_message_length")))
uint32_t cosmos_error_message_length_get(void) {
    return cosmos_error_message_length;
}

__attribute__((export_name("cosmos_deinit")))
void cosmos_deinit(void) {
    mp_deinit();
}
