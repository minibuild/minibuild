SSP_STUB_SOURCE = '''#include <unistd.h>

__attribute__((visibility ("hidden")))
void *__stack_chk_guard = 0;

static void __attribute__ ((constructor))
__guard_setup (void)
{
  unsigned char *p;
  if (__stack_chk_guard != 0)
    return;
  p = (unsigned char *) &__stack_chk_guard;
  p[sizeof(__stack_chk_guard)-1] = 255;
  p[sizeof(__stack_chk_guard)-2] = '\\n';
  p[0] = 0;
}


__attribute__((visibility ("hidden")))
void __stack_chk_fail (void)
{
  __builtin_trap();
  _exit(127);
}
'''
