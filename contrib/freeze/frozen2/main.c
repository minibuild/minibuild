#include <Python.h>
#include <stdlib.h>
#include "minibuild_frozen.h"

extern struct _frozen _PyImport_FrozenStdlibModules[];

extern void init_ctypes(void);
extern void init_elementtree(void);
extern void init_hashlib(void);
extern void init_multiprocessing(void);
extern void init_socket(void);
extern void init_ssl(void);
extern void init_sqlite3(void);
extern void initpyexpat(void);
extern void initselect(void);
extern void initunicodedata(void);
extern void initbz2(void);
extern void init_crypt(void);

static struct _inittab extensions[] = {
  {"_ctypes", init_ctypes},
  {"_elementtree", init_elementtree},
  {"_hashlib", init_hashlib},
  {"_multiprocessing", init_multiprocessing},
  {"_socket", init_socket},
  {"_ssl", init_ssl},
  {"_sqlite3", init_sqlite3},
  {"pyexpat", initpyexpat},
  {"select", initselect},
  {"unicodedata", initunicodedata},
  {"bz2", initbz2},
  {"_crypt", init_crypt},
  {NULL, NULL}
};

typedef struct
{
    struct _frozen* Entries;
    size_t EntriesCount;
} TableInfo;

static TableInfo BYTECODE_TABLES[] = {
    {_PyImport_FrozenStdlibModules, 0},
    {_PyImport_FrozenMiniBuild, 0},
    {NULL, 0}
};

static size_t InitTablesSize()
{
    size_t total = 0;
    size_t idx = 0;
    struct _frozen* entry = NULL;
    TableInfo* table = NULL;
    for ( ; BYTECODE_TABLES[idx].Entries; ++idx)
    {
        table = &BYTECODE_TABLES[idx];
        for (entry = &table->Entries[table->EntriesCount]; entry->name; ++entry)
        {
            table->EntriesCount += 1;
        }
        total += table->EntriesCount;
    }
    return total;
}

static void MergeBytecodeTables(struct _frozen* dest)
{
    size_t idx = 0;
    TableInfo* table = NULL;
    for ( ; BYTECODE_TABLES[idx].Entries; ++idx)
    {
        table = &BYTECODE_TABLES[idx];
        memcpy(dest, table->Entries, sizeof(struct _frozen) * table->EntriesCount);
        dest += table->EntriesCount;
    }
}

static int FrozenMain(int argc, char **argv)
{
    char* p;
    int n, sts;
    int unbuffered = 0;

    if ((p = Py_GETENV("PYTHONUNBUFFERED")) && *p != '\0')
        unbuffered = 1;

    if (unbuffered) {
        setbuf(stdin, (char *)NULL);
        setbuf(stdout, (char *)NULL);
        setbuf(stderr, (char *)NULL);
    }
    Py_Initialize();
    PySys_SetArgv(argc, argv);
    n = PyImport_ImportFrozenModule("__main__");
    sts = n > 0 ? 0 : 126;
    if (n == 0)
    {
        printf("%s\n", "BUILDSYS: ERROR: __main__ not frozen");
        fflush(stdout);
    }
    else if (n < 0)
    {
        PyErr_Print();
    }
    Py_Finalize();
    return sts;
}

int main(int argc, char** argv)
{
    int sys_argc = 0;
    char** sys_argv = 0;
    int interpreter = 0;
    int interpreter_args_start = 0;
    int verbose = 0;
    int trace = 0;
    size_t total = 0;
    int ret = 126;
    int i;
    struct _frozen* frozen_modules = NULL;
    for (i = 1; i < argc; ++i)
    {
        if (strcmp(argv[i], "--interpreter") == 0)
        {
            interpreter = 1;
            interpreter_args_start = i + 1;
            break;
        }
        else if (strcmp(argv[i], "--verbose") == 0)
        {
            verbose = 1;
        }
        else if (strcmp(argv[i], "--trace") == 0)
        {
            trace = 1;
        }
    }
    if (interpreter)
    {
        interpreter = 1;
        sys_argc = argc + 1 - interpreter_args_start;
        sys_argv = (char**)malloc(argc * sizeof(char*));
        memset(sys_argv, 0, argc * sizeof(char*));
        sys_argv[0] = argv[0];
        if (sys_argc > 1)
        {
            memcpy(&sys_argv[1], &argv[interpreter_args_start], (sys_argc - 1) * sizeof(char*));
        }
        if (verbose)
        {
#ifdef _WIN32
            putenv("MINIBUILD_VERBOSE=1");
#else
            setenv("MINIBUILD_VERBOSE", "1", 1);
#endif
        }
        else if (trace)
        {
#ifdef _WIN32
            putenv("MINIBUILD_TRACE=1");
#else
            setenv("MINIBUILD_TRACE", "1", 1);
#endif
        }
    }
    total = InitTablesSize();
    frozen_modules = (struct _frozen*)malloc(sizeof(struct _frozen) * (total + 1));
    MergeBytecodeTables(frozen_modules);
    memset(&frozen_modules[total], 0, sizeof(struct _frozen));
    PyImport_FrozenModules = frozen_modules;
    PyImport_ExtendInittab(extensions);
    if (interpreter)
    {
        ret = Py_Main(sys_argc, sys_argv);
    }
    else
    {
        ret = FrozenMain(argc, argv);
    }
    free(frozen_modules);
    free(sys_argv);
    return ret;
}
