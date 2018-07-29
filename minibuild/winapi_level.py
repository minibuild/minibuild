from .constants import TAG_ARCH_X86, TAG_ARCH_X86_64


WINDOWS_API_LEVELS = (
    '0x0602', # Windows 8
    '0x0601', # Windows 7
    '0x0600', # Windows Vista, Windows Server 2008
    '0x0502', # Windows XP x86_64, Windows Server 2003
    '0x0501', # Windows XP
)

IMPLIED_NTDDI_VALUES = {
    '0x0602': '0x06020000',
    '0x0601': '0x06010000',
    '0x0600': '0x06000000',
    '0x0502': '0x05020100',
    '0x0501': '0x05010200',
}

IMPLIED_WINDOWS_SUBSYSTEM_VALUES = {
    '0x0602': '6.02',
    '0x0601': '6.01',
    '0x0600': '6.00',
    '0x0502': '5.02',
    '0x0501': '5.01',
}

WINDOWS_API_DEFAULT_LEVEL = {
    TAG_ARCH_X86: '0x0501',
    TAG_ARCH_X86_64: '0x0502',
}
